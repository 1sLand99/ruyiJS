"""Capture an explicit local asynchronous chain without replacing browser APIs."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from tools.firefox_parity.browser import Firefox
from .async_fixture import Fixture, RESOURCES
from .rng_probe import digest

EXPECTED = ['start','microtask','promise','timeout','before-dispatch','listener','after-dispatch',
    'self-receive','port-receive','frame-receive','worker-receive','interval-1','interval-2','interval-3','complete']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=2)
    parser.add_argument('--firefox',type=Path,default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    args=parser.parse_args()
    if not 1<=args.rounds<=5:parser.error('rounds must be 1..5')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    report={'schema':'local.async-probe.v1','rounds':args.rounds,'cases':[],
        'firefox_sha256':digest(args.firefox),'xul_sha256':digest(args.firefox.with_name('xul.dll')),
        'fixture_hashes':{url:hashlib.sha256(body).hexdigest() for url,(_,body) in RESOURCES.items()},
        'expected_page_order':EXPECTED,
        'limits':['Explicit local markers are part of the fixture, not hidden production instrumentation.',
            'A serial fixture does not prove ordering of independent asynchronous tasks.',
            'No opcode or third-party challenge execution in this experiment.']}
    with Fixture() as fixture:
        report['fixture_origin']=fixture.origin
        for repetition in range(args.rounds):
            for mode in ('off','core','calls'):
                folder=output/f'{repetition}-{mode}';folder.mkdir()
                env={} if mode=='off' else {'MOZ_DOM_TRACE':'1','MOZ_DOM_TRACE_FILE':str(folder/'run.jsonl'),
                    'MOZ_DOM_TRACE_OPERATORS':'0'}
                if mode=='calls':env.update(MOZ_DOM_JSCALL_TRACE='1',MOZ_DOM_JSCALL_SCRIPT_URL='/async-',
                    MOZ_DOM_JSCALL_DETAIL_SCRIPT_URL='/async-',MOZ_DOM_JSCALL_LIMIT='0')
                with Firefox(args.firefox,folder/'profile',extra_environment=env) as browser:
                    browser.navigate(fixture.origin+'/')
                    browser.evaluate("(()=>{const s=document.createElement('script');s.src='/async-start.js';document.head.appendChild(s);return null})()")
                    deadline=time.monotonic()+8
                    while time.monotonic()<deadline:
                        result=browser.evaluate('asyncProof')
                        if result['done'] or result['errors']:break
                        time.sleep(.02)
                    if result['events']!=EXPECTED or not result['done'] or result['errors'] or result['intervalCount']!=3:
                        raise ValueError('local page chain differs: '+json.dumps(result))
                report['cases'].append({'round':repetition,'mode':mode,'settings':env,'page':result,
                                        'folder':folder.name})
                (output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
                print(json.dumps({'round':repetition,'mode':mode,'events':len(result['events']),'passed':True}),flush=True)


if __name__=='__main__':main()
