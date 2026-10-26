"""Validate native RNG evidence against all observed local-fixture outputs."""
import argparse
import json
from pathlib import Path
import re

from .random_state import next_value


def advance(state, count):
    a, b = state
    values = []
    for _ in range(count):
        a, b, value = next_value(a, b)
        values.append(value)
    return (a, b), values


def validate(report):
    checks = []
    for mode in ('on', 'seeded-on', 'gate'):
        data = report['modes'][mode]
        outputs = data['outputs']
        expected_realms = 1 if mode == 'gate' else 4
        assert len(outputs) == expected_realms, (mode, 'missing page outputs')
        groups = {}
        for row in data['records']:
            assert row['type'] == 'realm_rng', ('capture gap', row)
            assert row['schema'] == 'realm_rng.v1'
            assert row['algorithm'] == 'xorshift128plus-low53'
            assert row['process_instance_id'] and row['realm_id'] > 0
            assert row['phase'] in ('initial', 'script-entry')
            assert type(row['available']) is bool
            assert not row['script_url_truncated']
            assert all(re.fullmatch('[0-9a-f]{16}', row[key]) for key in ('state0', 'state1'))
            if row['available']:
                assert int(row['state0'], 16) or int(row['state1'], 16)
            else:
                assert row['phase'] == 'script-entry'
            identity = row['process_instance_id'], row['realm_id']
            groups.setdefault(identity, []).append(row)
        assert len(groups) == expected_realms, (mode, 'missing or merged realms')
        matched = set()
        for identity, group in groups.items():
            initials = [r for r in group if r['phase'] == 'initial']
            checkpoints = [r for r in group if r['phase'] == 'script-entry'
                           and r['available'] and 'second.js' in r['script_url']]
            assert len(checkpoints) == 1, (identity, 'ambiguous/missing checkpoint')
            checkpoint = checkpoints[0]
            state = tuple(int(checkpoint[key], 16) for key in ('state0', 'state1'))
            _, values = advance(state, 20000)
            candidates = [(n, o) for n, o in enumerate(outputs)
                          if n not in matched and o['values'] == values]
            assert candidates, (identity, 'stream differs')
            n, output = candidates[0]
            matched.add(n)
            if mode == 'gate':
                assert not initials, 'gate checkpoint mislabeled initial'
            else:
                assert len(initials) == 1 and initials[0]['available']
                initial = initials[0]
                assert initial['seq'] < checkpoint['seq']
                start = tuple(int(initial[key], 16) for key in ('state0', 'state1'))
                after, first = advance(start, 8)
                assert first == output['first'] and after == state
            checks.append({'mode': mode, 'realm': identity, 'script': checkpoint['script_url'],
                           'values_checked': 20000 + (0 if mode == 'gate' else 8)})
        assert len(matched) == expected_realms
    for mode in ('off', 'seeded-off'):
        assert not report['modes'][mode]['records']
        assert len(report['modes'][mode]['outputs']) == 4
    assert report['modes']['seeded-off']['outputs'] == report['modes']['seeded-on']['outputs']
    return {'checks': checks, 'seeded_page_results_equal': True, 'gate_checkpoint_verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(json.loads(args.report.read_text('utf-8'))), indent=2))


if __name__ == '__main__':
    main()
