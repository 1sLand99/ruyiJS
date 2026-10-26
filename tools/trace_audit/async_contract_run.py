"""Run trace-derived checkpoint contracts and deliberate divergence controls."""
import argparse
import copy
import json
from pathlib import Path

from .async_contract import compile_contract
from .async_consume import ROOT, consume
from .rng_probe import digest


def changed_contract(contract, mutation):
    value = copy.deepcopy(contract)
    if mutation == 'swap_first_group_labels':
        value['groups'][0]['labels'][0:2] = reversed(value['groups'][0]['labels'][0:2])
    elif mutation == 'split_final_microtask':
        last = value['groups'][-1]
        extra = copy.deepcopy(last)
        extra['labels'] = [last['labels'].pop()]
        value['groups'].append(extra)
    elif mutation == 'omit_interval_group':
        del value['groups'][-2]
    else:
        raise ValueError('unknown contract mutation')
    value['labels'] = [label for group in value['groups'] for label in group['labels']]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    capture = json.loads(args.capture.read_text('utf-8'))
    contracts = [compile_contract(args.capture, case) for case in capture['cases'] if case['mode'] != 'off']
    report = {'schema': 'local.async-contract-consumption.v1', 'contracts': [], 'runs': [], 'negative_controls': [],
              'shell_sha256': digest(ROOT / 'dist/js.exe'), 'client_sha256': digest(ROOT / 'dist/ruyijs_client.dll'),
              'full_goal_complete': False, 'deterministic_task_replay': False,
              'limitations': ['Observed checkpoint contracts only; no task identity selection.',
                              'Worker internal execution is outside the one-task owner budget.',
                              'Logical time follows live owner deadlines, not capture timestamps.']}

    def save():
        (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')

    for contract in contracts:
        name = f"contract-{contract['round']}-{contract['mode']}.json"
        path = args.output / name
        path.write_text(json.dumps(contract, indent=2) + '\n', 'utf-8')
        report['contracts'].append({'path': name, 'sha256': digest(path), 'groups': len(contract['groups'])})
        for adapter in ('Python', 'C'):
            result = consume(contract, adapter)
            result['contract'] = name
            report['runs'].append(result)
            save()
            print(json.dumps({key: result.get(key) for key in ('adapter', 'round', 'mode', 'passed', 'groups_consumed', 'error')}), flush=True)
    for mutation in ('swap_first_group_labels', 'split_final_microtask', 'omit_interval_group'):
        for adapter in ('Python', 'C'):
            result = consume(changed_contract(contracts[0], mutation), adapter)
            result['mutation'] = mutation
            result['rejected_as_expected'] = not result['passed'] and result.get('error', '').startswith('checkpoint ')
            report['negative_controls'].append(result)
            save()
    report['passed'] = all(row['passed'] for row in report['runs']) and all(
        row['rejected_as_expected'] for row in report['negative_controls'])
    report['sources'] = {str(path.relative_to(ROOT)): digest(path) for path in [
        Path(__file__), Path(__file__).with_name('async_contract.py'), Path(__file__).with_name('async_consume.py')]}
    save()
    print(json.dumps({'passed': report['passed'], 'runs': len(report['runs']),
                      'negative_controls': len(report['negative_controls']), 'full_goal_complete': False}))
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
