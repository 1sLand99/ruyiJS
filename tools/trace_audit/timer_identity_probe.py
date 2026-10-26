"""Capture bounded native Window timer identities with real Firefox controls."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from tools.firefox_parity.browser import Firefox
from .async_evidence import load_rows
from .async_mapping_probe import EXPECTED
from .timer_identity_fixture import Fixture, RESOURCES
from .timer_lifecycle import prove_timers
from .rng_probe import digest


def wait(browser, expression):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        if browser.evaluate(expression): return
        time.sleep(.02)
    raise TimeoutError('timer fixture did not complete')


def inject(browser, path):
    browser.evaluate("(()=>{const s=document.createElement('script');s.src=" + json.dumps(path) +
                     ";document.head.appendChild(s);return null})()")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    firefox = Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe')
    report = {'schema': 'local.timer-identity.v1', 'cases': [], 'xul_sha256': digest(firefox.with_name('xul.dll')),
              'sources': {path: hashlib.sha256(body).hexdigest() for path, (_, body) in RESOURCES.items()},
              'full_goal_complete': False}
    with Fixture() as fixture:
        for name in ('off', 'default', 'core', 'calls', 'edges', 'cap', 'gate'):
            folder = output / name; folder.mkdir()
            env = {} if name == 'off' else {'MOZ_DOM_TRACE': '1', 'MOZ_DOM_TRACE_FILE': str(folder / 'run.jsonl'),
                                            'MOZ_DOM_TRACE_OPERATORS': '0'}
            if name not in ('off', 'default'): env['MOZ_DOM_TRACE_TIMERS'] = '1'
            if name == 'calls': env.update(MOZ_DOM_JSCALL_TRACE='1', MOZ_DOM_JSCALL_SCRIPT_URL='/async-', MOZ_DOM_JSCALL_LIMIT='0')
            if name == 'cap': env['MOZ_DOM_TRACE_TIMER_LIMIT'] = '3'
            gate = folder / 'gate'
            if name == 'gate': env.update(MOZ_DOM_TRACE_GATE=str(gate), MOZ_DOM_TRACE_GATE_POLL_MS='20')
            with Firefox(firefox, folder / 'profile', extra_environment=env) as browser:
                browser.navigate(fixture.origin + ('/edges' if name == 'edges' else '/gate' if name == 'gate' else '/mapping'))
                if name == 'edges':
                    inject(browser, '/async-timer-start.js'); wait(browser, 'timerProof.done'); page = browser.evaluate('timerProof')
                    if page['errors'] or page['handles'] != [1, 1] or 'retired-ran' in page['events']:
                        raise ValueError('timer edge behavior differs')
                    if sorted(page['events']) != sorted(['a', 'b', 'tick-1', 'tick-2', 'tick-3', 'string', 'end']):
                        raise ValueError('timer edge events differ')
                elif name == 'gate':
                    inject(browser, '/async-gate-closed.js'); wait(browser, 'gateProof.events.length===1')
                    gate.write_text('open', 'utf-8'); time.sleep(.2)
                    inject(browser, '/async-gate-open.js'); wait(browser, 'gateProof.events.length===2')
                    page = browser.evaluate('gateProof')
                    if page['events'] != ['closed', 'open']: raise ValueError('gate page differs')
                else:
                    wait(browser, 'mappingProof.done'); page = browser.evaluate('mappingProof')
                    if page['errors'] or page['events'] != EXPECTED: raise ValueError('mapping page differs')
            rows, sources = load_rows(folder)
            events = [r for r in rows if r['type'] == 'timer_lifecycle']
            gaps = [r for r in rows if r['type'] == 'timer_trace_gap']
            case = {'name': name, 'page': page, 'settings': env, 'sources': sources}
            if name in ('off', 'default'):
                if events or gaps: raise ValueError('disabled timer trace emitted records')
            elif name == 'cap':
                if len(events) != 3 or len(gaps) != 1 or gaps[0]['limit'] != 3:
                    raise ValueError('timer cap not bounded')
                try: prove_timers(rows)
                except ValueError as error:
                    if str(error) != 'timer event budget gap': raise
                else: raise ValueError('incomplete trace accepted')
                case['bounded_events'] = len(events); case['gaps'] = gaps
            else:
                case['proof'] = prove_timers(rows)
                if name in ('core', 'calls') and case['proof']['phases'] != {'register': 5, 'cancel': 1, 'fire': 4, 'finish': 4}:
                    raise ValueError('sibling timer identities incomplete')
                if name == 'gate' and ({r['session'] for r in events} != {1} or case['proof']['registrations'] != 1):
                    raise ValueError('gate leaked or lost timer identity')
            report['cases'].append(case)
            (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
            print(json.dumps({'case': name, 'events': len(events), 'passed': True}), flush=True)


if __name__ == '__main__': main()
