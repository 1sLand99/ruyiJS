"""Randomized same-build cost of optional timer lifecycle records on loopback."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

from tools.firefox_parity.browser import Firefox
from .async_evidence import load_rows
from .rng_probe import digest
from .timer_identity_fixture import Fixture, RESOURCES
from .timer_identity_probe import inject, wait


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    firefox = Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe')
    report = {'schema': 'local.timer-identity-cost.v1', 'runs': [], 'rounds': 3, 'samples_per_run': 3,
              'registrations_per_run': 6200, 'xul_sha256': digest(firefox.with_name('xul.dll')),
              'source_hashes': {k: hashlib.sha256(v[1]).hexdigest() for k, v in RESOURCES.items()},
              'limitations': ['Same instrumented build, not upstream uninstrumented baseline.',
                             'Fixed register/cancel workload; no callback or whole-page cost estimate.',
                             'Page timers are quantized; three rounds; background load not isolated.']}
    rng = random.Random(20261024)
    with Fixture() as fixture:
        for repetition in range(3):
            order = ['off', 'core', 'timers']; rng.shuffle(order)
            for mode in order:
                folder = output / f'{repetition}-{mode}'; folder.mkdir()
                env = {} if mode == 'off' else {'MOZ_DOM_TRACE': '1', 'MOZ_DOM_TRACE_FILE': str(folder / 'run.jsonl'),
                                                'MOZ_DOM_TRACE_OPERATORS': '0'}
                if mode == 'timers': env['MOZ_DOM_TRACE_TIMERS'] = '1'
                with Firefox(firefox, folder / 'profile', extra_environment=env) as browser:
                    browser.navigate(fixture.origin + '/bench')
                    start = time.perf_counter()
                    inject(browser, '/async-timer-cost.js'); wait(browser, 'Boolean(window.benchResult)')
                    elapsed = (time.perf_counter() - start) * 1000
                    page = browser.evaluate('benchResult')
                if page['warmup']['checksum'] != 19900 or any(s['checksum'] != 1999000 or s['count'] != 2000 for s in page['samples']):
                    raise ValueError('timer workload output differs')
                rows, sources = load_rows(folder)
                timer_rows = [r for r in rows if r['type'] == 'timer_lifecycle']
                phases = dict(Counter(r['phase'] for r in timer_rows))
                if any(r['type'] == 'timer_trace_gap' for r in rows): raise ValueError('cost run saturated timer cap')
                if mode == 'timers' and phases != {'register': 6200, 'cancel': 6200}:
                    raise ValueError('cost lacks actual timer coverage')
                if mode != 'timers' and timer_rows: raise ValueError('disabled timer cost emitted events')
                stats = [r for r in rows if r['type'] == 'domtrace_writer_stats']
                fields = ('dropped_full', 'dropped_contention', 'dropped_oom', 'dropped_oversize', 'dropped_writer_failed', 'io_errors')
                if mode != 'off' and (not stats or any(r.get(k, 0) for r in stats for k in fields)):
                    raise ValueError('cost writer incomplete')
                row = {'round': repetition, 'mode': mode, 'order': order, 'page': page, 'host_ms': elapsed,
                       'phases': phases, 'sources': sources, 'core_bytes': sum(s['bytes'] for s in sources),
                       'timer_line_bytes': sum(len(json.dumps(r)) for r in timer_rows)}
                report['runs'].append(row)
                (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
                print(json.dumps({'round': repetition, 'mode': mode,
                                  'page_median_ms': statistics.median(s['ms'] for s in page['samples']),
                                  'events': len(timer_rows)}), flush=True)
    medians = {(r['round'], r['mode']): statistics.median(s['ms'] for s in r['page']['samples']) for r in report['runs']}
    report['paired_timer_vs_core'] = [medians[n, 'timers'] / medians[n, 'core'] for n in range(3)]
    report['paired_core_vs_off'] = [medians[n, 'core'] / medians[n, 'off'] for n in range(3)]
    report['page_medians_ms'] = {mode: statistics.median(s['ms'] for r in report['runs'] if r['mode'] == mode for s in r['page']['samples'])
                               for mode in ('off', 'core', 'timers')}
    report['full_goal_complete'] = False
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps({k: report[k] for k in ('page_medians_ms', 'paired_timer_vs_core', 'paired_core_vs_off')}))


if __name__ == '__main__': main()
