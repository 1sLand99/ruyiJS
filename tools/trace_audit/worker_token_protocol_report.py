"""Publish the protocol-only Worker token baseline."""
import argparse
import hashlib
import json
from pathlib import Path

from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('folder', type=Path)
    args = parser.parse_args(); folder = args.folder.resolve()
    roundtrip = json.loads((folder / 'roundtrip-final.json').read_text('utf-8'))
    tests = json.loads((ROOT / 'artifacts/worker-token-20261024/rollback-result.json').read_text('utf-8'))
    result = {'schema': 'local.worker-token-protocol-report.v1', 'roundtrip': roundtrip,
              'protocol_tests': 7, 'production_pipe_changed': False,
              'production_worker_regression': tests['full_tests'],
              'sources': {name: digest(ROOT / name) for name in (
                  'tools/trace_audit/worker_token_protocol.py', 'tools/trace_audit/worker_token_roundtrip.py',
                  'tests/test_worker_token_protocol.py')},
              'full_goal_complete': False}
    result['passed'] = roundtrip['passed'] and tests['full_tests']['passed']
    (folder / 'validation.json').write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps({'passed': result['passed'], 'messages': roundtrip['messages_checked'],
                      'protocol_tests': 7, 'full_goal_complete': False}))
    return int(not result['passed'])


if __name__ == '__main__': raise SystemExit(main())
