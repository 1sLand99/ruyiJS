"""Paired trace-off/calls/detail measurements using identical local page code."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time

from tools.firefox_parity.browser import Firefox
from .fixture import Fixture, HTML, SCRIPT

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context


def environment(mode, folder):
    if mode == 'off':
        return {}
    result = {'MOZ_DOM_TRACE': '1', 'MOZ_DOM_TRACE_FILE': str(folder / 'run.jsonl'),
              'MOZ_DOM_JSCALL_TRACE': '1', 'MOZ_DOM_JSCALL_SCRIPT_URL': 'web',
              'MOZ_DOM_JSCALL_LIMIT': '0'}
    if mode == 'detail':
        result.update({'MOZ_DOM_JSCALL_DETAIL_SCRIPT_URL': 'web',
                       'MOZ_DOM_JSCALL_MAX_VALUE_BYTES': '131072',
                       'MOZ_DOM_TRACE_MAX_STRING_CHARS': '8192',
                       'MOZ_DOM_ABSENT_PROBE': '1', 'MOZ_DOM_IFACE_PROBE': '1',
                       'MOZ_DOM_HOST_MUTATION': '1', 'MOZ_DOM_ENV_INVENTORY': '1',
                       'MOZ_DOM_HTTP_PACKET_TRACE': '1',
                       'MOZ_DOM_HTTP_PACKET_TRACE_DIR': str(folder / 'http_packet'),
                       'MOZ_DOM_HTTP_PACKET_TRACE_MAX_PENDING': '1024'})
    return result


def capture(browser, iterations):
    surface = browser.evaluate('traceBench.surface()')
    browser.evaluate('traceBench.benchmark(200000)')
    samples = [browser.evaluate(f'traceBench.benchmark({iterations})') for _ in range(5)]
    browser.evaluate('(window.chainResult = null, traceBench.chain().then(x => window.chainResult = x), null)')
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        chain = browser.evaluate('window.chainResult')
        if chain is not None:
            return {'surface': surface, 'samples': samples, 'chain': chain}
        time.sleep(.01)
    raise TimeoutError('local chain did not settle')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--iterations', type=int, default=2000000)
    parser.add_argument('--firefox', type=Path, default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'ruyijs.trace-benchmark.v1', 'rounds': [],
              'firefox_sha256': hashlib.sha256(args.firefox.read_bytes()).hexdigest(),
              'shell_sha256': hashlib.sha256((ROOT / 'dist/js.exe').read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(SCRIPT).hexdigest(),
              'iterations': args.iterations,
              'expected_benchmark_invocations_per_process': 6,
              'expected_leaf_invocations_per_process': 200000 + 5 * args.iterations,
              'expected_bytes_invocations_per_process': 6 * 20000,
              'limitations': ['Headless Marionette loopback workload, not the target site.',
                              'Trace-off is the same instrumented Firefox build, not an upstream binary.',
                              'Surface equality covers only the explicitly returned probe fields.',
                              'Short samples are affected by clock precision; raw samples are retained.']}
    rng = random.Random(20261024)
    with Fixture() as fixture:
        for number in range(args.rounds):
            modes = ['off', 'calls', 'detail']
            rng.shuffle(modes)
            for mode in modes:
                folder = output / f'{number}-{mode}'
                folder.mkdir()
                env = environment(mode, folder)
                with Firefox(args.firefox, folder / 'profile', extra_environment=env) as browser:
                    browser.navigate(fixture.url)
                    result = capture(browser, args.iterations)
                result.update({'round': number, 'mode': mode, 'settings': env})
                report['rounds'].append(result)
                (output / 'results.json').write_text(json.dumps(report, indent=2), 'utf-8')
                print(json.dumps({'round': number, 'mode': mode, 'samples': result['samples']}), flush=True)
        with Context(shell=ROOT / 'dist/js.exe', timeout=30) as context:
            context.configure_clock('logical', epoch_ms=1700000000000)
            context.put_resource(fixture.url + 'workload.js', SCRIPT,
                                 headers=[['Content-Type', 'application/javascript']])
            context.load_page(fixture.url, HTML)
            surface = context.eval('traceBench.surface()')
            context.eval('window.chainResult = null; traceBench.chain().then(x => window.chainResult = x); undefined')
            context.advance(20)
            report['ruyijs_fixture'] = {'surface': surface, 'chain': context.eval('chainResult'),
                                       'net_log': context.net_log()}
    reference = next(r for r in report['rounds'] if r['mode'] == 'off')
    report['capture_surface_equal'] = all(r['surface'] == reference['surface'] for r in report['rounds'])
    report['capture_chain_equal'] = all(r['chain'] == reference['chain'] for r in report['rounds'])
    report['ruyijs_chain_equal'] = report['ruyijs_fixture']['chain'] == reference['chain']
    medians = {mode: {metric: statistics.median(s[metric] for r in report['rounds'] if r['mode'] == mode for s in r['samples'])
                     for metric in ('js_ms', 'dom_ms', 'values_ms')} for mode in ('off', 'calls', 'detail')}
    report['median_ms'] = medians
    report['ratio_to_off'] = {mode: {k: v / medians['off'][k] if medians['off'][k] else None
                                   for k, v in values.items()} for mode, values in medians.items()}
    (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps({k: report[k] for k in ('capture_surface_equal', 'capture_chain_equal', 'ruyijs_chain_equal', 'ratio_to_off')}, indent=2))


if __name__ == '__main__':
    main()
