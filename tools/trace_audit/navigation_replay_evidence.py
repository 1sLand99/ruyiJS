"""Validate the measured-navigation replay experiment and bind its artifacts."""
import argparse
import json
from pathlib import Path
import re
import shutil

from .rng_probe import digest
from .navigation_observer_evidence import challenge_posts, prefix
from .boundary_diff import read, diff

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/navigation-replay-20261024')
    args = parser.parse_args()
    out = args.output.resolve()
    load = lambda path: json.loads(path.read_text('utf-8'))
    inputs = load(out/'inputs.json')
    assert not inputs['rejected'] and len(inputs['documents']) == 1
    assert len(inputs['documents'][0]['fields']) == 6
    source = Path(inputs['source']['file'])
    assert digest(source) == inputs['source']['sha256']
    before = load(ROOT/'artifacts/navigation-observer-20261024/replay/result.json')
    disabled = load(out/'without-navigation/result.json')
    replay = load(out/'replay/result.json')
    diagnostic = load(out/'diagnostic/result.json')
    tests = load(out/'all-tests-result.json')
    count = int(re.search(r'Ran (\d+) tests', (out/'all-tests.log').read_text('utf-8'))[1])
    assert tests['passed'] and tests['returncode'] == 0 and tests['tests'] == count
    oracle = load(out/'oracle/result.json')
    creep = load(out/'creepjs.json')
    examples = load(out/'example-entrypoints.json')
    assert all(oracle['parity'].values()) and creep['ok']
    assert all(r['exit_code'] == 0 for r in examples)
    assert replay['navigation_binding'] == diagnostic['navigation_binding']
    assert all(row['bound'] and row['fields'] == 6 for row in replay['navigation_binding'])
    posts, diag_posts = challenge_posts(replay), challenge_posts(diagnostic)
    previous_posts, off_posts = challenge_posts(before), challenge_posts(disabled)
    assert len(posts) == len(diag_posts) == len(previous_posts) == len(off_posts) == 3
    assert all(a['body_sha256'] == b['body_sha256'] for a,b in zip(posts,diag_posts))
    assert all(a['body_sha256'] == b['body_sha256'] for a,b in zip(previous_posts,off_posts))
    paths = list(out.glob('diagnostic-*.jsonl'))
    assert len(paths) == 1
    reference, url = prefix(source)
    current, _ = prefix(paths[0])
    boundary = diff(read(source,reference['stop_line'],url),read(paths[0],current['stop_line'],url))
    assert boundary['counts']['compared_values'] == 342
    assert not any(d['key'][1].startswith('Performance') for d in boundary['differences'])
    shell = digest(ROOT/'dist/js.exe')
    assert shell == replay['shell_sha256'] == disabled['shell_sha256'] == diagnostic['shell_sha256'] == oracle['shell_sha256']
    build = load(ROOT/'artifacts/build-runtime.json')
    assert build['status'] == 'built' and build['sha256'] == shell
    shutil.copy2(ROOT/'artifacts/build-runtime.json',out/'build-runtime.json')
    sources = ['src/domain/execution_scheduling/navigation_replay.h',
        'src/domain/execution_scheduling/navigation_timing.h','src/execution_scheduling/realm.h',
        'src/execution_scheduling/state.h','src/execution_scheduling/navigation_replay.cpp',
        'src/execution_scheduling/performance_resource.cpp','src/execution_scheduling/performance_legacy.cpp',
        'src/runtime/navigation_replay.h','src/runtime/navigation_replay.cpp','src/runtime/scheduling_control.cpp']
    built_inputs = {r['path'].replace('\\','/').lower():r['sha256'] for r in build['inputs']}
    for name in sources:
        assert digest(ROOT/name) == built_inputs[str(ROOT/name).replace('\\','/').lower()], name
    sources += ['python/ruyijs/_scheduling.py','tools/trace_audit/replay_probe.py',
        'tools/trace_audit/navigation_inputs.py','tools/trace_audit/navigation_replay_evidence.py',
        'tests/test_navigation_inputs.py','tests/test_navigation_replay.py',
        'ARCHITECTURE.md','docs/owners/PERFORMANCE.md','docs/TRACE_REPLAY_20261024.md']
    result = {'schema':'navigation-replay.validation.v1','full_goal_complete':False,
        'shell_sha256':shell,'client_sha256':digest(ROOT/'dist/ruyijs_client.dll'),
        'oracle':oracle['parity'],'tests':tests,'creepjs_ok':creep['ok'],'examples':len(examples),
        'navigation_inputs':inputs['documents'],'binding':replay['navigation_binding'],
        'boundary':boundary,'disabled_preserves_challenge_bodies':True,
        'diagnostic_challenge_bodies_equal':True,'challenge_posts':posts,
        'sources':{name:digest(ROOT/name) for name in sources},
        'limitations':['Partial navigation measurements; unobserved fields and task timing remain unresolved.',
            'loadEventEnd is derived from navigation duration semantics and applied at real completion.',
            '342 primitive matches do not cover the full page; 5852 reference keys remain unmatched.']}
    reports = ['inputs.json','replay/result.json','without-navigation/result.json','diagnostic/result.json',
        'oracle/result.json','all-tests.log','all-tests-result.json','creepjs.json','example-entrypoints.json',
        'build.log','build-runtime.json']
    result['reports'] = {name:digest(out/name) for name in reports}
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps({'tests':count,'navigation_fields':6,'boundary':boundary['counts'],
        'post_bytes':[row['body_bytes'] for row in posts],'full_goal_complete':False}))


if __name__ == '__main__': main()
