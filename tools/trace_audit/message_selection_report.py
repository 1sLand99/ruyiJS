"""Publish same-process Window message selection evidence."""
import argparse
import difflib
import json
from pathlib import Path

from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    folder = args.folder.resolve()
    tests = json.loads((folder / 'all-tests-result.json').read_text('utf-8'))
    regressions = json.loads((folder / 'regressions.json').read_text('utf-8'))
    build = json.loads((folder / 'build-final2-result.json').read_text('utf-8'))
    relink = json.loads((folder / 'relink-client-result.json').read_text('utf-8'))
    if not tests['passed'] or any(r['returncode'] for r in regressions) or build['returncode'] or relink['returncode']:
        raise ValueError('message validation incomplete')
    runtime = {'shell_sha256': digest(ROOT / 'dist/js.exe'), 'client_sha256': digest(ROOT / 'dist/ruyijs_client.dll')}
    source_names = ['src/execution_scheduling/tasks.cpp', 'src/execution_scheduling/timer_selection.cpp',
        'src/runtime/message_selection.cpp', 'src/runtime/scheduling_control.cpp', 'src/runtime/window_message_ports.cpp',
        'src/browser_environment/window_messaging.cpp', 'src/browser_environment/environment_view.cpp',
        'src/browser_environment/environment.h', 'src/execution_scheduling/state.h', 'src/execution_scheduling/realm.h',
        'python/ruyijs/_scheduling.py', 'tests/test_message_selection.py']
    sources = {name: digest(ROOT / name) for name in source_names}
    lines = ['# Window message identity selection in ruyijs', '',
        'This experiment adds an opt-in host selection path for same-process Window',
        'postMessage tasks. WindowMessaging remains responsible for cloning, origin',
        'checks and MessageEvent delivery; Scheduling owns the task queue and invokes',
        'the existing trampoline. Default postMessage behavior is unchanged.', '',
        '## Recorded identity', '',
        'At the original send boundary, the message task stores source and target',
        'installed-global realm positions, a source-local sequence, message kind and',
        'the existing internal task ID. The payload is never used as an identity key.',
        'A separate message sequence is maintained by the Window environment owner.', '',
        '| Host action | Validation |', '|---|---|',
        '| `configure_message_replay(true)` | Boolean and pre-freeze configuration |',
        '| `pending_messages()` | Live message tasks with task, source/target realm, sequence, kind, due time |',
        '| `run_message(...)` | All metadata, due logical time, target lifetime and pending work checked before Claim |', '',
        '## Local result', '',
        'The fixture creates two same-origin frames and sends the same string `same`',
        'to both. Python and the actual C DLL each select both messages; changing',
        'source, target, sequence, kind or task identity fails without consuming a task.',
        'The normal unconfigured context still delivers a default postMessage through advance.', '',
        f"The full suite ran {tests['tests']} tests with no failures. Existing local",
        'synchronous trace replay and async runtime parity both passed after the message change.', '',
        '## Scope boundary', '',
        'This is same-process WindowMessaging only. Dedicated Worker and cross-process relay',
        'tasks have separate Scheduling owners/processes and are not selected by this interface.',
        'Their trace IDs remain statically verifiable through the concurrent proof. A future',
        'relay must carry the token through the Worker owner, not match equal payloads or time.', '',
        'No opcode logging was needed for this identity gap. Opcode data would not supply the',
        'missing cross-owner message token. This run contains no new performance claim or',
        'original webpage replay.', '', '## Reproduce', '', '```powershell',
        'Set-Location D:\\BaiduNetdiskDownload\\ivv8\\ivv8\\ruyijs',
        'python -B tools/build.py --jobs 12 --toolchain-bin C:/Users/Administrator/.mozbuild/clang/bin',
        'python -B -m unittest discover -s tests -p test_message_selection.py -v',
        'python -B -m unittest discover -s tests -v', '```', '', '## Identity', '',
        'shell: `'+runtime['shell_sha256']+'`.', 'C DLL: `'+runtime['client_sha256']+'`.',
        'Evidence directory: `artifacts/message-selection-20261024/`.', '']
    (folder / 'MESSAGE_SELECTION.md').write_text('\n'.join(lines), 'utf-8')
    diff = []
    for name in source_names:
        before = folder / 'before' / name
        diff.extend(difflib.unified_diff(before.read_text('utf-8').splitlines(True) if before.exists() else [],
                    (ROOT / name).read_text('utf-8').splitlines(True), fromfile='before/'+name, tofile='after/'+name))
    (folder / 'implementation.diff').write_text(''.join(diff), 'utf-8')
    manifest = {'schema': 'local.message-selection-report.v1', 'tests': tests, 'runtime': runtime,
        'sources': sources, 'scope': 'Same-process WindowMessaging only; Worker/cross-process relay excluded.',
        'full_goal_complete': False}
    (folder / 'validation.json').write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    print(json.dumps({'published': True, 'tests': tests['tests'], 'runtime': runtime}))


if __name__ == '__main__': main()
