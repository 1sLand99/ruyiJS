"""Build a hash-indexed evidence summary for the completed RNG experiments."""
import argparse
import json
from pathlib import Path

from .rng_probe import digest
from .verify_rng import validate
from .verify_object_snapshots import verify

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/rng-trace-20261024/validation.json')
    parser.add_argument('--reference', type=Path, default=Path('D:/cf-turnstile-scrapingcourse'))
    parser.add_argument('--firefox-source', type=Path, default=Path('D:/firefox/src/firefox'))
    args = parser.parse_args()
    evidence = ROOT / 'artifacts/rng-trace-20261024'

    def read(path):
        return json.loads(path.read_text('utf-8'))

    capture = read(evidence / 'seeded-corrected/result.json')
    rng = validate(capture)
    replay = read(evidence / 'stream-replay.json')
    edges = read(evidence / 'edges-script-entry/result.json')
    snapshot_report = read(evidence / 'object-regression/result.json')
    snapshots = verify(snapshot_report)
    tests = read(evidence / 'python-tests-result.json')
    assert replay['passed'] and edges['validation']['passed'] and tests['passed']
    assert len(replay['checks']) == 18 and len(rng['checks']) == 9
    assert tests['returncode'] == 0
    assert capture['xul_sha256'] == edges['xul_sha256'] == snapshot_report['xul_sha256']
    live = read(args.reference / 'work/firefox-rng-capture-20261024/result.json')
    coverage = read(args.reference / 'work/firefox-rng-capture-20261024/coverage.json')
    off = read(args.reference / 'work/firefox-baseline-rng-20261024/result.json')
    node = read(args.reference / 'work/verified-login-5.json')
    assert live['passed'] and off['passed'] and not node['passed']
    assert live['xul_sha256'] == capture['xul_sha256']
    assert live['samples'][-1]['products'] == off['samples'][-1]['products'] == 12
    manifest = {'schema': 'rng.validation.v1', 'full_goal_complete': False,
        'rng': rng, 'stream_replay': {'checks': len(replay['checks']),
            'values': sum(row['values_checked'] for row in replay['checks']), 'scope': replay['scope']},
        'edges': edges['validation'], 'snapshots': snapshots, 'tests': tests,
        'live': {'trace_off_seconds': off['elapsed_seconds'], 'trace_on_seconds': live['elapsed_seconds'],
            'products_each': 12, 'realms': len(coverage['realms']),
            'rng_records': coverage['record_types']['realm_rng'], 'rng_gaps': len(coverage['gaps']),
            'core_bytes': sum(row['bytes'] for row in coverage['files']),
            'node_post_status': node['stages'][-1]['status'], 'node_passed': node['passed']},
        'binaries': {}, 'sources': {}, 'reports': {},
        'limitations': ['No full historical page or business replay.',
            'No paired overhead estimate or universal page indistinguishability.',
            'No forced GC/address reuse or simultaneous realm capacity test.',
            'Script association is not an initializing callsite or document declaration.']}

    def entry(path):
        return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path)}

    for name, path in {'firefox': args.firefox_source / 'obj-jscall-check/dist/bin/firefox.exe',
                       'xul': args.firefox_source / 'obj-jscall-check/dist/bin/xul.dll',
                       'shell': ROOT / 'dist/js.exe', 'c_dll': ROOT / 'dist/ruyijs_client.dll'}.items():
        manifest['binaries'][name] = entry(path)
    assert manifest['binaries']['xul']['sha256'] == capture['xul_sha256']
    assert manifest['binaries']['shell']['sha256'] == replay['shell_sha256']
    assert manifest['binaries']['c_dll']['sha256'] == replay['c_dll_sha256']
    sources = [ROOT / 'tools/trace_audit' / (name + '.py') for name in
               ('rng_fixture', 'rng_probe', 'verify_rng', 'rng_replay', 'rng_edges',
                'rng_capture_report', 'rng_evidence')]
    sources += [ROOT / 'tests/test_rng_verifier.py', ROOT / 'docs/TRACE_REPLAY_20261024.md']
    sources += [args.reference / name for name in ('run.ps1', 'browser_baseline.py',
        'summarize_experiment.py', 'REPRODUCTION_AND_PAPER_20261024.md', 'PAPER_DRAFT_20261024.md')]
    sources += [args.firefox_source / name for name in ('dom/bindings/domtrace/RngTraceRegistry.h',
        'dom/bindings/domtrace/RngTraceLog.h', 'dom/bindings/domtrace/RNG_TRACE_20261024.md',
        'dom/bindings/domtrace/README.md', 'js/src/builtin/Math.cpp', 'js/src/vm/Interpreter.cpp',
        'js/src/vm/Realm.cpp')]
    for path in sources:
        manifest['sources'][str(path)] = entry(path)
    reports = [evidence / name for name in ('seeded-corrected/result.json', 'stream-replay.json',
        'edges-script-entry/result.json', 'object-regression/result.json', 'python-tests-result.json',
        'python-tests-clean.log', 'probe/result.json', 'exact-values/result.json', 'edges/result.json')]
    reports += [args.reference / 'work' / name for name in ('verified-login-5.json',
        'firefox-baseline-rng-20261024/result.json', 'firefox-rng-capture-20261024/result.json',
        'firefox-rng-capture-20261024/coverage.json', 'experiment-summary.json')]
    for path in reports:
        manifest['reports'][str(path)] = entry(path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    print(json.dumps({'source_files': len(sources), 'reports': len(reports), 'tests': tests['tests'],
        'stream_values': manifest['stream_replay']['values'], 'full_goal_complete': False}))


if __name__ == '__main__':
    main()
