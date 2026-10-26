"""Compare navigation observer delivery against native Firefox on loaded frames."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
import time

from tools.firefox_parity.browser import Firefox
from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context

SCRIPT = (ROOT / 'tests/navigation_observer_fixture.js').read_text('utf-8')
FRAME = '<!doctype html><script>' + SCRIPT + '</script>'
HTML = FRAME + '<iframe src="/frame"></iframe>'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (FRAME if self.path == '/frame' else HTML).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_):
        pass


def expressions():
    return {'main': 'window', 'frame': 'document.querySelector("iframe").contentWindow'}


def capture(evaluate):
    return {key: json.loads(evaluate('JSON.stringify(' + value + '.navResult)'))
            for key, value in expressions().items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-parity', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    executable = Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe')
    report = {'firefox_sha256': digest(executable), 'xul_sha256': digest(executable.with_name('xul.dll')),
              'shell_sha256': digest(ROOT / 'dist/js.exe'), 'fixture_sha256': digest(ROOT / 'tests/navigation_observer_fixture.js')}
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    try:
        with Firefox(executable, args.output / 'profile') as browser:
            browser.navigate(origin + '/')
            for window in expressions().values():
                browser.evaluate(window + '.startLateNavigationObserver()')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                data = capture(browser.evaluate)
                if all(r['late'] for r in data.values()):
                    break
                time.sleep(.05)
            report['firefox'] = data
        with Context(shell=ROOT / 'dist/js.exe') as context:
            context.configure_clock('logical', epoch_ms=1700000000000)
            context.put_resource(origin + '/frame', FRAME, headers=[['Content-Type', 'text/html']])
            context.load_page(origin + '/', HTML)
            context.advance(10)
            for window in expressions().values():
                context.eval(window + '.startLateNavigationObserver()')
            context.advance(10)
            report['ruyijs'] = capture(context.eval)
        report['parity'] = {key: report['firefox'][key] == report['ruyijs'][key] for key in expressions()}
        report['limitations'] = ['Times differ across real and logical clocks; compare lifecycle and identity.']
        (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
        print(json.dumps({'parity': report['parity'], 'descriptors': report['firefox']['main']['observeDescriptor']}, indent=2))
        if args.require_parity:
            assert all(report['parity'].values())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == '__main__':
    main()
