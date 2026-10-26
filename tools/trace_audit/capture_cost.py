"""Measure local trace cost together with actual call coverage and behavior."""
import argparse
import json
from pathlib import Path
import random
import statistics

from tools.firefox_parity.browser import Firefox
from .fixture import Fixture, SCRIPT
from .rng_probe import digest
from .process_sample import ProcessSample
from .binary import CALL, header
from .jsonlines import dictionary
from .cost_summary import summarize


def settings(mode, folder):
    if mode == 'off': return {}
    env = {'MOZ_DOM_TRACE': '1', 'MOZ_DOM_TRACE_FILE': str(folder/'run.jsonl'),
           'MOZ_DOM_TRACE_OPERATORS': '0'}
    if mode in ('calls', 'detail'):
        env.update(MOZ_DOM_JSCALL_TRACE='1', MOZ_DOM_JSCALL_SCRIPT_URL='/workload.js',
                   MOZ_DOM_JSCALL_LIMIT='0')
    if mode == 'detail':
        env['MOZ_DOM_JSCALL_DETAIL_SCRIPT_URL'] = '/workload.js'
    return env


def evidence(folder):
    result = {'trace_bytes': 0, 'call_records': 0, 'leaf_records': 0,
              'bytes_records': 0, 'detail_bytes': 0, 'stats': [], 'dict_errors': []}
    for directory in ('domtrace', 'jscall', 'descriptor', 'event', 'eval', 'exception',
                      'storage', 'cookie', 'wasm'):
        base = folder/directory
        if base.exists():
            result['trace_bytes'] += sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
    for path in (folder/'jscall').glob('*.dict.jsonl'):
        functions, stats, errors = dictionary(path)
        result['dict_errors'].extend(errors)
        if stats: result['stats'].append(stats)
        binary = path.with_name(path.name.removesuffix('.dict.jsonl')+'.bin')
        with binary.open('rb') as stream:
            header(stream, b'JSCT', CALL.size)
            while block := stream.read(CALL.size*16384):
                if len(block) % CALL.size: raise ValueError('partial call record')
                for call, parent, function, duration, depth, argc, flags, entry, _ in CALL.iter_unpack(block):
                    result['call_records'] += 1
                    name = functions.get(function, {}).get('name')
                    if name == 'leaf': result['leaf_records'] += 1
                    if name == 'bytes': result['bytes_records'] += 1
    for path in (folder/'jscall').glob('*.detail.bin'):
        result['detail_bytes'] += path.stat().st_size
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--iterations', type=int, default=10000000)
    parser.add_argument('--firefox', type=Path,
        default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    args = parser.parse_args()
    if not 2 <= args.rounds <= 30 or not 1 <= args.samples <= 20 or not 100000 <= args.iterations <= 50000000:
        parser.error('bounded rounds/samples/iterations required')
    output = args.output.resolve();output.mkdir(parents=True, exist_ok=False)
    import hashlib
    report = {'schema': 'local.capture-cost.v1', 'firefox_sha256': digest(args.firefox),
        'xul_sha256': digest(args.firefox.with_name('xul.dll')),
        'workload_sha256': hashlib.sha256(SCRIPT).hexdigest(),
        'rounds': args.rounds, 'samples_per_run': args.samples, 'iterations': args.iterations,
        'seed': 20261024, 'runs': [],
        'known_calls_per_process': {'leaf': 200000 + args.samples * args.iterations,
                                   'bytes': 20000 * (1 + args.samples)},
        'limits': ['Same instrumented Firefox binary with switches changed; not an upstream baseline.',
            'Local fixed workload, fresh profile per mode, no inference about a remote page.',
            'Host wall/CPU includes Marionette and 25ms process sampling; page clocks are quantized.',
            'Working sets are summed across processes and can double count shared memory.',
            'Exited process CPU between samples and memory spikes may be missed.',
            'Low overhead with sparse call coverage does not prove full trace performance.']}
    rng = random.Random(report['seed'])
    with Fixture() as fixture:
        for repetition in range(args.rounds):
            order = ['off', 'core', 'calls', 'detail'];rng.shuffle(order)
            for mode in order:
                folder = output/f'{repetition}-{mode}';folder.mkdir()
                env = settings(mode, folder)
                with Firefox(args.firefox, folder/'profile', extra_environment=env) as browser:
                    browser.navigate(fixture.url)
                    surface = browser.evaluate('traceBench.surface()')
                    browser.evaluate('traceBench.benchmark(200000)')
                    samples = []
                    for _ in range(args.samples):
                        with ProcessSample(browser.process.pid) as measure:
                            page = browser.evaluate(f'traceBench.benchmark({args.iterations})')
                        samples.append({'page': page, 'process': measure.result})
                row = {'round': repetition, 'mode': mode, 'order': order, 'surface': surface,
                       'settings': env, 'samples': samples, 'capture': evidence(folder)}
                report['runs'].append(row)
                (output/'results.json').write_text(json.dumps(report, indent=2)+'\n','utf-8')
                print(json.dumps({'round': repetition, 'mode': mode,
                    'median_wall_ms': statistics.median(s['process']['wall_ms'] for s in samples),
                    'trace_bytes': row['capture']['trace_bytes'],
                    'recorded_leaf': row['capture']['leaf_records']}), flush=True)
    report['summary'] = summarize(report)
    (output/'results.json').write_text(json.dumps(report, indent=2)+'\n','utf-8')
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__': main()
