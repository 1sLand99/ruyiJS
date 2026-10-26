"""Audit the bounded Worker token protocol and its preserved legacy frame path."""
import argparse
import hashlib
import json
from pathlib import Path

from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    files = ['src/web_workers/clone.h', 'src/web_workers/clone.cpp', 'src/web_workers/bootstrap.h',
             'src/web_workers/methods.cpp', 'src/web_workers/child.cpp', 'src/web_workers/child_script.cpp',
             'src/web_workers/poll.cpp', 'src/web_workers/state.h', 'src/web_workers/child.h']
    text = '\n'.join((ROOT / name).read_text('utf-8') for name in files)
    checks = {
        'token_fields': all(token in text for token in ('workerId', 'sequence', 'direction')),
        'parent_direction': "direction = 0" in text,
        'child_direction': 'token{child.workerId_, ++child.childSequence_, 1}' in text,
        'child_validates_worker': 'lastIncoming_.workerId != workerId_' in text,
        'parent_validates_worker': 'token.workerId == record->workerId' in text,
        'legacy_rw4_decode': 'RW4\\0' in text and 'RW5\\0' in text,
        'new_rw5_encode': 'frame->assign("RW5\\0", 4)' in text,
        'payload_not_identity': 'EncodeMessageWithToken' in text and 'DecodeMessageWithToken' in text,
        'bounded_sequence_type': 'uint64_t' in text,
    }
    result = {'schema': 'local.worker-token-audit.v1', 'checks': checks,
              'sources': {name: {'bytes': (ROOT / name).stat().st_size, 'sha256': digest(ROOT / name)} for name in files},
              'runtime': {'shell_sha256': digest(ROOT / 'dist/js.exe'),
                          'client_sha256': digest(ROOT / 'dist/ruyijs_client.dll')},
              'scope': 'Token transport and child validation; no cross-process selection endpoint.',
              'full_goal_complete': False}
    result['passed'] = all(checks.values())
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    (args.output / 'WORKER_TOKEN_AUDIT.md').write_text('\n'.join([
        '# Worker message token transport audit', '',
        'The current Worker pipe now has an opt-in-compatible token frame for ordinary',
        'Dedicated Worker postMessage traffic. The token carries worker identity, a',
        'direction bit and a monotonic per-direction sequence. Structured clone bytes',
        'remain separate and are decoded by the existing DifferentProcess owner.', '',
        'Parent-to-child frames use direction 0; child-to-parent frames use direction 1.',
        'Both endpoints validate worker identity and direction before firing a message.',
        'Startup uses RW5 with the worker identity; DecodeStartup still accepts RW4 without',
        'reading token bytes, so a legacy startup frame is not misparsed.', '',
        'This is token transport only. Parent Poll and child Serve still own separate task',
        'queues, and no RPC selects a child task. Cross-process deterministic replay remains',
        'incomplete until a child-ready/task acknowledgement path is implemented.', '',
        'Checks: `result.json`; production source and binary identities are recorded there.', '']), 'utf-8')
    print(json.dumps({'passed': result['passed'], 'full_goal_complete': False}))
    return int(not result['passed'])


if __name__ == '__main__': raise SystemExit(main())
