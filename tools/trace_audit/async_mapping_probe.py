"""Measure callback registration ambiguity and deferred Promise causality locally."""
import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import time

from tools.firefox_parity.browser import Firefox
from .async_contract import marker_groups
from .async_evidence import analyze, context_key, load_rows
from .rng_probe import digest

SCRIPT = Path(__file__).with_name('async_mapping.js')
EXPECTED = ['start', 'registered', 'timer-a', 'timer-b', 'resolve-before', 'resolve-after', 'reaction', 'finish']


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        script = self.path == '/async-mapping.js'
        body = SCRIPT.read_bytes() if script else b'<!doctype html><script src="/async-mapping.js"></script>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/javascript' if script else 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *_): pass


def inspect(rows):
    proof = analyze(rows)
    if proof['gaps'] or any(proof['writer_losses'].values()):
        raise ValueError('mapping capture has causal gaps or writer loss')
    registrations = [r for r in rows if r['type'] == 'call' and r.get('member') == 'setTimeout']
    schedules = [r for r in rows if r['type'] == 'async_schedule' and r['async_cause'] == 'set_timeout']
    joins = []
    for schedule in schedules:
        candidates = [r for r in registrations if context_key(r) == context_key(schedule, 'parent_execution_context_id')
                      and r.get('origin_call_id') == schedule.get('async_parent_call_id')]
        joins.append({'async_context_id': schedule['async_context_id'], 'schedule_line': schedule['file_line'],
                      'candidate_registration_lines': [r['file_line'] for r in candidates],
                      'candidate_public_handles': [r['return'] for r in candidates]})
    groups = marker_groups(rows)
    reaction = next(r for r in rows if r['type'] == 'async_schedule' and r['async_cause'] == 'promise_reaction')
    parent = context_key(reaction, 'parent_execution_context_id')
    parent_markers = [r['args'][1] for r in rows if r['type'] == 'call' and r.get('member') == 'setAttribute'
                      and (r.get('args') or [None])[0] == 'data-causal-proof' and context_key(r) == parent]
    return {'proof': proof, 'groups': groups, 'timer_join_candidates': joins,
            'registrations': len(registrations), 'observed_timer_schedules': len(schedules),
            'promise_parent_context': list(parent), 'promise_parent_markers': parent_markers,
            'unique_identity_fields_in_timer_schedules': sorted(set().union(*(set(r) for r in schedules))),
            'schedule_resumes': dict(Counter(str(r['async_context_id']) for r in rows if r['type'] == 'async_resume'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    firefox = Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe')
    report = {'schema': 'local.async-mapping-probe.v1', 'cases': [], 'script_sha256': digest(SCRIPT),
              'xul_sha256': digest(firefox.with_name('xul.dll')), 'full_goal_complete': False}
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        for mode in ('off', 'core', 'calls'):
            folder = output / mode; folder.mkdir()
            env = {} if mode == 'off' else {'MOZ_DOM_TRACE': '1', 'MOZ_DOM_TRACE_FILE': str(folder / 'run.jsonl'),
                                           'MOZ_DOM_TRACE_OPERATORS': '0'}
            if mode == 'calls':
                env.update(MOZ_DOM_JSCALL_TRACE='1', MOZ_DOM_JSCALL_SCRIPT_URL='/async-', MOZ_DOM_JSCALL_LIMIT='0')
            with Firefox(firefox, folder / 'profile', extra_environment=env) as browser:
                browser.navigate(f'http://127.0.0.1:{server.server_port}/')
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    page = browser.evaluate('mappingProof')
                    if page['done'] or page['errors']: break
                    time.sleep(.02)
                if not page['done'] or page['errors'] or page['events'] != EXPECTED:
                    raise ValueError('mapping fixture page differs')
            case = {'mode': mode, 'page': page}
            if mode != 'off':
                rows, sources = load_rows(folder)
                case.update(inspect(rows)); case['sources'] = sources
            report['cases'].append(case)
            (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
            print(json.dumps({'mode': mode, 'passed': True,
                              'timer_candidate_counts': [len(r['candidate_registration_lines']) for r in case.get('timer_join_candidates', [])],
                              'promise_parent_markers': case.get('promise_parent_markers')}), flush=True)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__': main()
