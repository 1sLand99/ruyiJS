"""Bind RTC order corrections to native browser, production runtime and trace evidence."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shutil

from .rng_probe import digest
from .navigation_observer_evidence import challenge_posts, prefix
from .boundary_diff import read, diff
from .rtc_observations import scan

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/rtc-order-20261024')
    args=parser.parse_args();out=args.output.resolve()
    load=lambda p:json.loads(p.read_text('utf-8'))
    oracle=load(out/'after/result.json');before=load(out/'before/result.json')
    assert len(oracle['parity'])==7 and all(oracle['parity'].values())
    assert not any(before['parity'].values())
    tests=load(out/'all-tests-final-result.json')
    count=int(re.search(r'Ran (\d+) tests',(out/'all-tests-final.log').read_text('utf-8'))[1])
    assert tests['passed'] and tests['returncode']==0 and tests['tests']==count
    creep=load(out/'creepjs.json');examples=load(out/'example-entrypoints.json')
    assert creep['ok'] and all(row['exit_code']==0 for row in examples)
    reentrant=load(out/'reentrant/validation.json');assert all(reentrant.values())
    reference=load(out/'reference-rtc.json');current=load(out/'replay-rtc.json')
    assert not reference['anomalies'] and not current['anomalies']
    assert reference['phases']=={'before_first_send':{'host':20},'after_first_send':{'srflx':10,'empty':3,'null':1}}
    assert current['phases']=={'before_first_send':{'host':20,'empty':3,'null':1},'after_first_send':{}}
    replay=load(out/'replay/result.json');diagnostic=load(out/'diagnostic/result.json')
    prior=load(ROOT/'artifacts/navigation-replay-20261024/replay/result.json')
    posts=challenge_posts(replay);traced=challenge_posts(diagnostic);old=challenge_posts(prior)
    assert len(posts)==len(traced)==len(old)==3
    assert all(a['body_sha256']==b['body_sha256']==c['body_sha256'] for a,b,c in zip(posts,traced,old))
    ablation=load(out/'candidate-content-ablation/result.json')
    ablation_trace=load(out/'candidate-content-diagnostic/result.json')
    assert all(a['body_sha256']==b['body_sha256']==c['body_sha256'] for a,b,c in
               zip(posts,challenge_posts(ablation),challenge_posts(ablation_trace)))
    content_paths=list(out.glob('candidate-content-*.jsonl'));assert len(content_paths)==1
    content=scan(content_paths[0])
    candidate_texts=lambda rows:[row['candidate']['fields']['candidate'] for row in rows
                                if row['before_first_send'] and row['category']=='host']
    assert candidate_texts(content['events'])==candidate_texts(reference['events'])
    assert len(candidate_texts(content['events']))==20
    source=Path(reference['source']);assert digest(source)==reference['sha256']
    trace=Path(current['source']);assert digest(trace)==current['sha256']
    ref_prefix,url=prefix(source);new_prefix,_=prefix(trace)
    comparison=diff(read(source,ref_prefix['stop_line'],url),read(trace,new_prefix['stop_line'],url))
    shell=digest(ROOT/'dist/js.exe');assert shell==oracle['shell_sha256']==replay['shell_sha256']==diagnostic['shell_sha256']
    build=load(ROOT/'artifacts/build-runtime.json');assert build['status']=='built' and build['sha256']==shell
    shutil.copy2(ROOT/'artifacts/build-runtime.json',out/'build-runtime.json')
    sources=list(load(out/'source-before/manifest.json'))
    patch=[]
    for name in sources:
        a=(out/'source-before'/name).read_text('utf-8').splitlines(keepends=True)
        b=(ROOT/name).read_text('utf-8').splitlines(keepends=True)
        patch.extend(difflib.unified_diff(a,b,fromfile='before/'+name,tofile='after/'+name))
    name='src/web_rtc/ice_sections.h';sources.append(name)
    patch.extend(difflib.unified_diff([],(ROOT/name).read_text('utf-8').splitlines(keepends=True),fromfile='/dev/null',tofile='after/'+name))
    (out/'implementation.diff').write_text(''.join(patch),'utf-8')
    built={row['path'].replace('\\','/').lower():row['sha256'] for row in build['inputs']}
    for name in sources:assert digest(ROOT/name)==built[str(ROOT/name).replace('\\','/').lower()],name
    sources+=['ARCHITECTURE.md','docs/owners/WEB_RTC.md','docs/TRACE_REPLAY_20261024.md',
        'tests/rtc_gathering_fixture.js','tests/test_rtc_gathering.py','tests/test_rtc_observations.py',
        'tools/trace_audit/rtc_gathering_probe.py','tools/trace_audit/rtc_observations.py',
        'tools/trace_audit/rtc_order_evidence.py','tools/trace_audit/replay_probe.py']
    result={'schema':'rtc-order.validation.v1','full_goal_complete':False,'shell_sha256':shell,
        'client_sha256':digest(ROOT/'dist/ruyijs_client.dll'),'oracle':oracle['parity'],'tests':tests,
        'creepjs_ok':creep['ok'],'examples':len(examples),'reentrant':reentrant,
        'observed_phases':{'reference':reference['phases'],'replay':current['phases']},
        'reference_missing_metadata_events':sum(bool(row.get('missing_fields')) for row in reference['events']),
        'challenge_bodies_preserved':True,'diagnostic_bodies_equal':True,'challenge_posts':posts,
        'candidate_content_ablation':{'observed_host_texts_equal':20,'body_hashes_unchanged':True,
            'scope':'Existing process-wide profile; mid/index/ufrag and event timing are not restored.'},
        'boundary_diff':comparison,'sources':{name:digest(ROOT/name) for name in sources},
        'limitations':['No server-reflexive network inputs or recorded delivery deadlines restored.',
            'Old getter evidence lacks mid/index/ufrag; timestamps are observation times.',
            'Correct event order with unchanged request bodies does not prove business closure.']}
    files=['before/result.json','after/result.json','all-tests-final-result.json','all-tests-final.log',
        'creepjs.json','example-entrypoints.json','reference-rtc.json','replay-rtc.json',
        'replay/result.json','diagnostic/result.json','build.log','build-runtime.json',
        'implementation.diff','reentrant/result.json','reentrant/validation.json',
        'candidate-content-ablation/result.json','candidate-content-diagnostic/result.json',
        'candidate-content-inputs.json']
    result['reports']={name:digest(out/name) for name in files}
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps({'tests':count,'oracle_cases':7,'post_bytes':[row['body_bytes'] for row in posts],
        'body_hashes_preserved':True,'boundary':comparison['counts'],'full_goal_complete':False}))


if __name__=='__main__':main()
