"""Capture actual native RNG state and compare generated values across realms."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from tools.firefox_parity.browser import Firefox
from .rng_fixture import Fixture,RESOURCES
from .verify_rng import validate


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def records(folder):
    result=[]
    for path in (folder/'domtrace').glob('*.jsonl'):
        with path.open('rb') as stream:
            for number,line in enumerate(stream,1):
                if b'"realm_rng"' not in line and b'"rng_trace_gap"' not in line:continue
                row=json.loads(line);result.append({'file':path.name,'line':number,**row})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--firefox',type=Path,default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    report={'firefox_sha256':digest(args.firefox),'xul_sha256':digest(args.firefox.with_name('xul.dll')),
            'fixtures':{k:hashlib.sha256(v[1].encode()).hexdigest() for k,v in RESOURCES.items()},'modes':{}}
    with Fixture() as fixture:
        for mode in ('off','on','seeded-off','seeded-on','gate'):
            folder=output/mode;folder.mkdir();env={}
            if mode in ('on','seeded-on','gate'):
                env={'MOZ_DOM_TRACE':'1','MOZ_DOM_TRACE_FILE':str(folder/'run.jsonl'),
                     'MOZ_DOM_TRACE_OPERATORS':'0','MOZ_DOM_RNG_TRACE_URL':'/rng-'}
            if mode.startswith('seeded'):
                env.update(MOZ_DOM_API_OVERRIDE='1',MOZ_DOM_API_MATH_RANDOM='seeded:12345')
            gate=folder/'gate'
            if mode=='gate':env.update(MOZ_DOM_TRACE_GATE=str(gate),MOZ_DOM_TRACE_GATE_POLL_MS='20')
            with Firefox(args.firefox,folder/'profile',extra_environment=env) as browser:
                browser.navigate(fixture.origin+('/gate' if mode=='gate' else '/'))
                if mode=='gate':
                    gate.write_text('open','utf-8');time.sleep(.2)
                    browser.evaluate("(()=>{const s=document.createElement('script');s.src='/rng-gate-second.js';document.head.appendChild(s);return null})()")
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    done=browser.evaluate('!!result.done' if mode=='gate' else 'workerResult!==null')
                    if done:break
                    time.sleep(.05)
                if not done:raise TimeoutError('RNG fixture did not finish')
                expression='[result]' if mode=='gate' else '[result,...Array.from(document.querySelectorAll("iframe"),f=>f.contentWindow.result),workerResult]'
                values=browser.evaluate('JSON.stringify('+expression+')');values=json.loads(values)
            report['modes'][mode]={'outputs':values,'records':records(folder),'settings':env}
            (output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
            print(json.dumps({'mode':mode,'realms':len(values),'records':len(report['modes'][mode]['records'])}),flush=True)
    report['validation']=validate(report)
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report['validation'],indent=2))


if __name__=='__main__':main()
