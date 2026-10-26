"""Capture concurrent equal-payload local messages through real isolated frame sites."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from tools.firefox_parity.browser import Firefox
from .concurrent_fixture import Fixture, HOSTS, SCRIPT_RESOURCES
from .rng_probe import digest


def await_page(browser,expression):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        if browser.evaluate(expression):return
        time.sleep(.02)
    raise TimeoutError('concurrent local fixture did not reach expected phase')


def validate_page(page):
    if not page['done'] or page['errors'] or sorted(page['ready'])!=[0,1]:
        raise ValueError('concurrent page result invalid')
    if page['sent']!=[8,8] or page['received']!=[8,8]:raise ValueError('missing/extra page response')
    if len(page['order'])!=36:raise ValueError('page marker total differs')
    for index in (0,1):
        for phase in ('send','receive'):
            expected=[f'parent:{phase}:{index}:{n}' for n in range(1,9)]
            if [s for s in page['order'] if s.startswith(f'parent:{phase}:{index}:')]!=expected:
                raise ValueError('per-source FIFO order differs')
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=2)
    args=parser.parse_args()
    if not 1<=args.rounds<=4:parser.error('rounds must be 1..4')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    executable=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe')
    report={'schema':'local.concurrent-message.v1','rounds':args.rounds,'cases':[],
        'firefox_sha256':digest(executable),'xul_sha256':digest(executable.with_name('xul.dll')),
        'script_hashes':{name:hashlib.sha256(value).hexdigest() for name,value in SCRIPT_RESOURCES.items()},
        'limits':['Local distinct-site frames and their workers; no third-party target.',
            'Every request/response in a direction has identical data; identity must come from trace.',
            'Inter-branch arrival order may vary and is not treated as a required total order.']}
    with Fixture() as fixture:
        report['origins']=fixture.origins
        for repetition in range(args.rounds):
            for mode in ('off','core','calls'):
                folder=output/f'{repetition}-{mode}';folder.mkdir()
                env={} if mode=='off' else {'MOZ_DOM_TRACE':'1','MOZ_DOM_TRACE_FILE':str(folder/'run.jsonl'),
                    'MOZ_DOM_TRACE_OPERATORS':'0'}
                if mode=='calls':env.update(MOZ_DOM_JSCALL_TRACE='1',MOZ_DOM_JSCALL_SCRIPT_URL='/async-concurrent-',
                    MOZ_DOM_JSCALL_DETAIL_SCRIPT_URL='/async-concurrent-',MOZ_DOM_JSCALL_LIMIT='0')
                prefs={'network.dns.localDomains':','.join(HOSTS),'fission.autostart':True}
                with Firefox(executable,folder/'profile',prefs=prefs,extra_environment=env,
                             extra_args=('--remote-allow-system-access',)) as browser:
                    browser.command('Marionette:SetContext',{'value':'chrome'})
                    try: fission=browser.evaluate('Services.appinfo.fissionAutostart')
                    finally:browser.command('Marionette:SetContext',{'value':'content'})
                    if fission is not True:raise ValueError('Fission not active')
                    browser.navigate(fixture.origins[0]+'/')
                    await_page(browser,'concurrentProof.ready.length===2')
                    browser.evaluate("(()=>{const s=document.createElement('script');s.src='/async-concurrent-start.js';document.head.appendChild(s);return null})()")
                    await_page(browser,'concurrentProof.done || concurrentProof.errors.length>0')
                    page=browser.evaluate('concurrentProof');validate_page(page)
                report['cases'].append({'round':repetition,'mode':mode,'folder':folder.name,
                    'settings':env,'prefs':prefs,'fission_active':fission,'page':page})
                (output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
                print(json.dumps({'round':repetition,'mode':mode,'received':page['received'],'passed':True}),flush=True)


if __name__=='__main__':main()
