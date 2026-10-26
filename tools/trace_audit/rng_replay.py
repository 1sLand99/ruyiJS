"""Replay captured Firefox RNG streams in separate original ruyijs realms."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from .rng_probe import digest
from .verify_rng import validate

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / 'tests'))
from ruyijs import Context
from iframe_client import CClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.capture.read_text('utf-8'))
    validate(source)
    result = {'schema': 'rng.stream-replay.v1', 'capture_sha256': digest(args.capture),
        'shell_sha256': digest(ROOT / 'dist/js.exe'),
        'c_dll_sha256': digest(ROOT / 'dist/ruyijs_client.dll'), 'checks': [],
        'scope': 'Each stream runs in a fresh initial realm; no child scheduling or business replay.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for mode in ('on', 'seeded-on', 'gate'):
        data = source['modes'][mode]
        phase = 'script-entry' if mode == 'gate' else 'initial'
        rows = [r for r in data['records'] if r['phase'] == phase and r['available']]
        expected = [(o['first'] if mode != 'gate' else []) + o['values'] for o in data['outputs']]
        for adapter in ('Python', 'C'):
            matched = set()
            for row in rows:
                client = Context(shell=ROOT / 'dist/js.exe') if adapter == 'Python' else CClient()
                count = 20000 if mode == 'gate' else 20008
                try:
                    if adapter == 'Python':
                        client.configure_random(row['state0'], row['state1'])
                    else:
                        client.call('configure_random', state0=row['state0'], state1=row['state1'])
                    values = client.eval('(() => {const a=[]; for(let i=0;i<' + str(count)
                                         + ';i++) a.push(Math.random()); return a})()')
                    candidates = [n for n, value in enumerate(expected) if n not in matched and values == value]
                    assert candidates, (adapter, mode, row['realm_id'])
                    matched.add(candidates[0])
                    surface = client.eval("[typeof configure_random,typeof setRNGState,Math.random.toString()]")
                    assert surface[:2] == ['undefined', 'undefined'] and '[native code]' in surface[2], surface
                    result['checks'].append({'adapter': adapter, 'mode': mode,
                        'process_instance_id': row['process_instance_id'], 'realm_id': row['realm_id'],
                        'phase': phase, 'values_checked': count,
                        'values_sha256': hashlib.sha256(json.dumps(values).encode()).hexdigest()})
                finally:
                    client.close()
            assert len(matched) == len(expected)
    result['passed'] = True
    args.output.write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps({'checks': len(result['checks']),
                      'values_checked': sum(r['values_checked'] for r in result['checks']), 'passed': True}))


if __name__ == '__main__':
    main()
