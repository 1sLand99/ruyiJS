"""Verify opt-in real Worker token transport without changing default behavior."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context


@contextmanager
def token_environment(enabled):
    previous = os.environ.get('RUYIJS_WORKER_TOKEN')
    if enabled: os.environ['RUYIJS_WORKER_TOKEN'] = '1'
    else: os.environ.pop('RUYIJS_WORKER_TOKEN', None)
    try: yield
    finally:
        if previous is None: os.environ.pop('RUYIJS_WORKER_TOKEN', None)
        else: os.environ['RUYIJS_WORKER_TOKEN'] = previous


def run(enabled):
    with token_environment(enabled):
        context = Context(shell=ROOT / 'dist/js.exe', timeout=15)
        try:
            context.configure_clock('logical', epoch_ms=1700000000000)
            context.put_resource('http://worker-token.test/worker.js',
                "const first=setTimeout(()=>{},60000),second=setInterval(()=>{},60000);clearInterval(first);clearTimeout(second);postMessage([first,second])",
                headers=[['Content-Type', 'application/javascript']])
            context.load_page('http://worker-token.test/',
                '<!doctype html><script>window.result=null;window.errors=[];'
                "window.worker=new Worker('/worker.js');worker.onmessage=e=>result=e.data;"
                'worker.onerror=e=>errors.push(e.message);</script>')
            page = None
            for _ in range(80):
                context.advance(10)
                page = context.eval('[result, errors]')
                if page[0] is not None or page[1]: break
                time.sleep(.01)
            return {'enabled': enabled, 'page': page, 'passed': page == [[1, 2], []]}
        finally: context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'local.worker-token-runtime.v1', 'runs': [run(False), run(True)],
              'production_default_unchanged': True, 'full_goal_complete': False}
    report['passed'] = all(row['passed'] for row in report['runs'])
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps(report)); return int(not report['passed'])


if __name__ == '__main__': raise SystemExit(main())
