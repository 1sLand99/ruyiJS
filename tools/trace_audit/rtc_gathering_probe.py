"""Compare RTC section order and ICE completion events to actual Firefox."""
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
sys.path.insert(0, str(ROOT/'python'))
from ruyijs import Context

SCRIPT = ROOT/'tests/rtc_gathering_fixture.js'
HTML = '<!doctype html><script>' + SCRIPT.read_text('utf-8') + '</script>'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_): pass


def comparable(results):
    summary = {key: {name: value[name] for name in
            ('sections','mids','bundle','events','ends','setLocalResolved','done')}
            for key,value in results.items()}
    for key, value in results.items():
        order = list(dict.fromkeys((row['mid'], row['index']) for row in value['candidates']))
        summary[key]['candidate_section_order'] = order
        summary[key]['candidate_identity_valid'] = bool(value['candidates']) and all(
            all(row[field] is True for field in ('sameObject','prototype','eventPrototype','trusted','target','ufrag'))
            for row in value['candidates'])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-parity', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    executable = Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe')
    report = {'firefox_sha256':digest(executable),'xul_sha256':digest(executable.with_name('xul.dll')),
              'shell_sha256':digest(ROOT/'dist/js.exe'),'fixture_sha256':digest(SCRIPT)}
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = Thread(target=server.serve_forever,daemon=True);thread.start()
    origin = f'http://127.0.0.1:{server.server_port}/'
    try:
        with Firefox(executable,args.output/'profile') as browser:
            browser.navigate(origin);browser.evaluate('startRtcCases()')
            deadline = time.monotonic()+20
            while time.monotonic()<deadline:
                result=json.loads(browser.evaluate('JSON.stringify(rtcResults)'))
                if result and all(value['done'] for value in result.values()):break
                time.sleep(.05)
            report['firefox']=result
            browser.evaluate('rtcPeers.forEach(peer=>peer.close())')
        with Context(shell=ROOT/'dist/js.exe') as context:
            context.configure_clock('logical',epoch_ms=1700000000000)
            context.load_page(origin,HTML);context.eval('startRtcCases()')
            context.advance(2000)
            report['ruyijs']=context.eval('rtcResults')
            context.eval('rtcPeers.forEach(peer=>peer.close())')
        a,b=comparable(report['firefox']),comparable(report['ruyijs'])
        report['parity']={key:a[key]==b[key] for key in a}
        (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
        print(json.dumps({'parity':report['parity'],
            'firefox_events':{key:value['events'] for key,value in a.items()}},indent=2))
        if args.require_parity:assert all(report['parity'].values())
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':main()
