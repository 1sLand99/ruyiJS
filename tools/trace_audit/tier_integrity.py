"""Prove parent/value integrity of existing local tier experiment captures."""
import argparse
import json
from pathlib import Path

from .local_call_index import CallIndex
from .tier_value_proof import prove
from .tier_summary import summarize
from .rng_probe import digest

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    original=json.loads(args.report.read_text('utf-8'));summarize(original)
    if digest(ROOT/'tools/trace_audit/tier_workload.js')!=original['workload_sha256']:
        raise ValueError('fixture source differs from experiment')
    args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((args.report.parent.parent/'validation.json').read_text('utf-8'))
    known={entry['path'].replace('\\','/'):entry for entry in manifest['raw_evidence_files']}
    result={'schema':'local.tier-integrity.v1','runs':[],'experiment_sha256':digest(args.report),
        'workload_sha256':original['workload_sha256'],
        'expected':original['known_calls'],'full_goal_complete':False,
        'limitations':['Normal JIT call records are a sparse observed graph, not a complete direct stack.',
            'Even absent gap flags are not a universal proof of direct-call ancestry.',
            'This proof uses the exact published synchronous fixture and is not a generic replay verifier.']}
    for run in original['runs']:
        if run['mode']!='detail':continue
        folder=args.report.parent/f"{run['round']}-{run['tier']}-{run['mode']}"/'jscall'
        selected=[]
        for path in folder.glob('*.detail.bin'):
            binary=path.with_name(path.name.removesuffix('.detail.bin')+'.bin')
            dictionary=path.with_name(path.name.removesuffix('.detail.bin')+'.dict.jsonl')
            sources={}
            for source in (path,binary,dictionary):
                key=source.relative_to(args.report.parent.parent).as_posix()
                entry=known[key]
                if source.stat().st_size!=entry['bytes'] or digest(source)!=entry['sha256']:
                    raise ValueError('original local capture changed: '+key)
                sources[key]=entry['sha256']
            expected_runs=[{'arguments':[original['warmup'],original['byte_calls']],
                            'checksum':run['warmup']['checksum']}]
            expected_runs += [{'arguments':[original['iterations'],original['byte_calls']],
                               'checksum':sample['checksum']} for sample in run['samples']]
            with CallIndex(binary,dictionary) as index:
                if any(not f.get('url','').endswith('/tier-workload.js') for f in index.functions.values()):
                    raise ValueError('capture contains a different source')
                proof=prove(index,path,expected_runs,complete=run['tier']=='interpreter')
                row={'round':run['round'],'tier':run['tier'],'pid':index.pid,'sources':sources,
                    'functions':dict(index.counts),'caller_jit_gaps':index.gaps,
                    'edges':[{'parent':p,'child':c,'count':n} for (p,c),n in sorted(index.edges.items())],**proof}
            selected.append(row)
        if len(selected)!=1:raise ValueError('expected exactly one detailed fixture process')
        result['runs'].extend(selected)
        (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
        print(json.dumps({k:selected[0][k] for k in ('round','tier','completed_calls','leaf_returns','run_checksums')}),flush=True)
    if len(result['runs'])!=original['rounds']*2:raise ValueError('incomplete integrity cases')
    result['verified']=True
    result['total_leaf_returns']=sum(row['leaf_returns'] for row in result['runs'])
    result['total_numeric_returns']=sum(row['numeric_returns'] for row in result['runs'])
    sources=['local_call_index.py','tier_oracle.py','tier_value_proof.py','tier_integrity.py','tier_summary.py']
    result['sources']={name:digest(Path(__file__).with_name(name)) for name in sources}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps({'verified':True,'leaf_returns':result['total_leaf_returns'],
                      'numeric_returns':result['total_numeric_returns']}))


if __name__=='__main__':main()
