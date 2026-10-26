"""Compare the explicit local async fixture's behavior through Python and C entrypoints."""
import argparse
import json
from pathlib import Path
import sys
import time

from .async_fixture import Fixture,RESOURCES,HTML
from .async_probe import EXPECTED
from .rng_probe import digest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'));sys.path.insert(0,str(ROOT/'tests'))
from ruyijs import Context
from iframe_client import CClient


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    report={'schema':'local.async-runtime-parity.v1','shell_sha256':digest(ROOT/'dist/js.exe'),
        'client_sha256':digest(ROOT/'dist/ruyijs_client.dll'),'cases':[],
        'scope':'Executes unchanged local fixture; does not consume or replay captured browser task scheduling.'}
    with Fixture() as fixture:
        for adapter in ('Python','C'):
            client=Context(shell=ROOT/'dist/js.exe',timeout=20) if adapter=='Python' else CClient()
            try:
                client.configure_clock('logical',epoch_ms=1700000000000)
                for path,(mime,body) in RESOURCES.items():
                    client.put_resource(fixture.origin+path,body.decode('utf-8'),headers=[['Content-Type',mime]])
                client.load_page(fixture.origin+'/',HTML.decode('utf-8'))
                client.eval("(()=>{const s=document.createElement('script');s.src='/async-start.js';document.head.appendChild(s);return null})()")
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    client.advance(20)
                    page=client.eval('asyncProof')
                    if page['done'] or page['errors']:break
                    time.sleep(.02)
                passed=page['events']==EXPECTED and page['done'] and not page['errors'] and page['intervalCount']==3
                report['cases'].append({'adapter':adapter,'page':page,'passed':passed})
            except Exception as error:
                report['cases'].append({'adapter':adapter,'passed':False,'error':str(error)})
            finally:client.close()
            (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    report['passed']=all(row['passed'] for row in report['cases'])
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
