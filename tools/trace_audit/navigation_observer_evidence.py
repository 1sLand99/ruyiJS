"""Bind the navigation observer fix to source, binaries and original-trace evidence."""
import argparse
import difflib
import json
from pathlib import Path

from .boundary_diff import read, diff
from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]


def prefix(path):
    navigation, callbacks, url = [], [], None
    with path.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if row.get('type') == 'script_root' and row.get('phase') == 'start' and url is None:
                url = row['url']
            if row.get('interface') == 'XMLHttpRequest' and row.get('member') == 'send':
                return {'file': str(path), 'stop_line': number, 'navigation': navigation,
                        'callbacks': callbacks}, url
            if row.get('interface') == 'PerformanceObserverEntryList' and row.get('member') == 'getEntries':
                callbacks.append({'line': number, 'seq': row.get('seq')})
            if row.get('interface') in ('PerformanceEntry', 'PerformanceResourceTiming'):
                if row.get('type') != 'get':
                    continue
                navigation.append({'line': number, 'seq': row.get('seq'), 'member': row['member'],
                    'value': row.get('value') if row.get('member') != 'get name' else '<document URL>',
                    'receiver': row.get('thisObj')})
    raise ValueError('no XHR send boundary: ' + str(path))


def challenge_posts(report):
    return [row for row in report['requests'] if row['method'] == 'POST'
            and row['host'] == 'challenges.cloudflare.com' and row.get('recorded_candidates')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/navigation-observer-20261024')
    parser.add_argument('--capture', type=Path, default=Path('D:/firefox/src/firefox/dom/bindings/domtrace/runs/jscall-detail-desktop-20261024-023506'))
    args = parser.parse_args()
    out = args.output.resolve()
    load = lambda path: json.loads(path.read_text('utf-8'))
    reference, url = prefix(args.capture / 'domtrace/trace_process_58620.jsonl')
    before, _ = prefix(ROOT / 'artifacts/timer-handles-20261024/final-diagnostic-29324.jsonl')
    diagnostics = list(out.glob('diagnostic-*.jsonl'))
    assert len(diagnostics) == 1
    after, _ = prefix(diagnostics[0])
    assert len(reference['callbacks']) == len(after['callbacks']) == 1 and not before['callbacks']
    comparison = diff(read(Path(reference['file']), reference['stop_line'], url),
                      read(diagnostics[0], after['stop_line'], url))
    oracle = load(out / 'after-descriptor/result.json')
    tests = load(out / 'all-tests-final-result.json')
    creep = load(out / 'creepjs.json')
    examples = load(out / 'example-entrypoints.json')
    replay = load(out / 'replay/result.json')
    diagnosed = load(out / 'diagnostic/result.json')
    earlier = load(ROOT / 'artifacts/timer-handles-20261024/final-replay/result.json')
    assert all(oracle['parity'].values()) and tests['passed'] and creep['ok']
    assert all(r['exit_code'] == 0 for r in examples)
    assert replay['status'] == diagnosed['status'] == 'probe_finished'
    posts, traced = challenge_posts(replay), challenge_posts(diagnosed)
    assert len(posts) == len(traced) == 3
    assert all(a['body_sha256'] == b['body_sha256'] for a, b in zip(posts, traced))
    sources = list(load(out / 'source-before/manifest.json'))
    patch = []
    for name in sources:
        old = (out / 'source-before' / name).read_text('utf-8').splitlines(keepends=True)
        new = (ROOT / name).read_text('utf-8').splitlines(keepends=True)
        patch.extend(difflib.unified_diff(old, new, fromfile='before/' + name, tofile='after/' + name))
    (out / 'implementation.diff').write_text(''.join(patch), 'utf-8')
    sources += ['ARCHITECTURE.md', 'docs/owners/PERFORMANCE.md', 'docs/TRACE_REPLAY_20261024.md',
        'tests/navigation_observer_fixture.js', 'tests/test_navigation_observer.py',
        'tools/trace_audit/navigation_observer_probe.py', 'tools/trace_audit/navigation_observer_evidence.py']
    manifest = {'schema': 'navigation-observer.validation.v1', 'full_goal_complete': False,
        'binaries': {name: digest(ROOT / 'dist' / name) for name in ('js.exe', 'ruyijs_client.dll')},
        'oracle': oracle['parity'], 'tests': tests, 'creepjs_ok': creep['ok'],
        'example_entrypoints': len(examples), 'observed_chain': {'reference': reference, 'before': before, 'after': after},
        'boundary_diff': comparison, 'challenge_posts_before': challenge_posts(earlier),
        'challenge_posts_after': posts, 'diagnostic_body_hashes_equal': True,
        'sources': {name: digest(ROOT / name) for name in sources},
        'limitations': ['Recorded navigation times and byte sizes are not restored.',
            'Local observer parity does not establish full page or business replay.',
            'Encrypted body prefix length is not a monotonic correctness score.']}
    assert manifest['binaries']['js.exe'] == oracle['shell_sha256'] == replay['shell_sha256']
    files = ['before/result.json', 'after-descriptor/result.json', 'all-tests-final-result.json',
        'all-tests-final.log', 'build.log', 'replay/result.json', 'diagnostic/result.json',
        'creepjs.json', 'example-entrypoints.json', 'implementation.diff', 'source-before/manifest.json']
    manifest['reports'] = {name: digest(out / name) for name in files}
    (out / 'validation.json').write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    print(json.dumps({'tests': tests['tests'], 'oracle': oracle['parity'],
        'restored_navigation_callbacks': len(after['callbacks']), 'boundary_counts': comparison['counts'],
        'post_bytes': [p['body_bytes'] for p in posts], 'full_goal_complete': False}))


if __name__ == '__main__':
    main()
