"""Exercise recurring timer declarations after an unobserved first callback."""
import argparse
from collections import Counter
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import time

from tools.firefox_parity.browser import Firefox

SCRIPT = '''window.intervalProbe = {quiet:0, visible:0, timeout:false, promise:false};
const quiet = setInterval(() => {
  intervalProbe.quiet++;
  if (intervalProbe.quiet === 1) return;
  fetch('/quiet?tick=' + intervalProbe.quiet);
  if (intervalProbe.quiet === 3) clearInterval(quiet);
}, 35);
const visible = setInterval(() => {
  intervalProbe.visible++;
  fetch('/visible?tick=' + intervalProbe.visible);
  if (intervalProbe.visible === 2) clearInterval(visible);
}, 45);
const cancelled = setInterval(() => { throw new Error('cancelled interval ran'); }, 500);
clearInterval(cancelled);
setTimeout(() => { intervalProbe.timeout = true; fetch('/timeout'); }, 20);
Promise.resolve().then(() => { intervalProbe.promise = true; fetch('/promise'); });
'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            body, mime = b'<!doctype html><script src="/interval.js"></script>', 'text/html'
        elif self.path == '/interval.js':
            body, mime = SCRIPT.encode(), 'text/javascript'
        else:
            body, mime = b'ok', 'text/plain'
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def inspect(folder):
    schedules, resumes = {}, []
    for path in (folder / 'domtrace').glob('*.jsonl'):
        with path.open(encoding='utf-8') as stream:
            for number, line in enumerate(stream, 1):
                row = json.loads(line)
                if row.get('type') == 'async_schedule':
                    key = (row['pid'], row['session'], row['async_context_id'])
                    schedules.setdefault(key, []).append({'file': path.name, 'line': number, **row})
                elif row.get('type') == 'async_resume':
                    resumes.append({'file': path.name, 'line': number, **row})
    missing = [r for r in resumes if (r['pid'], r['schedule_session'], r['async_context_id']) not in schedules]
    return {'schedule_causes': dict(Counter(r['async_cause'] for group in schedules.values() for r in group)),
            'resume_causes': dict(Counter(r['async_cause'] for r in resumes)),
            'missing_schedule': missing,
            'duplicate_schedule_ids': sum(len(group) > 1 for group in schedules.values()),
            'schedules': [row for group in schedules.values() for row in group], 'resumes': resumes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trace-off', action='store_true')
    parser.add_argument('--firefox', type=Path, default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {'firefox_sha256': hashlib.sha256(args.firefox.read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(SCRIPT.encode()).hexdigest()}
    library = args.firefox.with_name('xul.dll')
    with library.open('rb') as stream:
        report['xul_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    environment = {'MOZ_DOM_TRACE': '1', 'MOZ_DOM_TRACE_FILE': str(folder / 'run.jsonl'),
                   'MOZ_DOM_JSCALL_TRACE': '1', 'MOZ_DOM_JSCALL_SCRIPT_URL': 'web',
                   'MOZ_DOM_TRACE_OPERATORS': '0'}
    if args.trace_off:
        environment = {}
    report['settings'] = environment
    try:
        with Firefox(args.firefox, folder / 'profile', extra_environment=environment) as browser:
            browser.navigate(f'http://127.0.0.1:{server.server_port}/')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                value = browser.evaluate('intervalProbe')
                if value['quiet'] == 3 and value['visible'] == 2 and value['timeout'] and value['promise']:
                    break
                time.sleep(.05)
            report['page_result'] = value
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    report.update(inspect(folder))
    (folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps({k: report[k] for k in ('page_result', 'schedule_causes', 'resume_causes', 'duplicate_schedule_ids')}, indent=2))
    print('missing_schedule:', len(report['missing_schedule']))


if __name__ == '__main__':
    main()
