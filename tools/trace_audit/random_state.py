"""Infer a SpiderMonkey RNG state from recorded native Math.random outputs.

Optional dependency: z3-solver. The result is an inferred state under the stated
contiguous-output assumption, never a seed purportedly recorded by Firefox.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

MASK64, MASK53 = (1 << 64) - 1, (1 << 53) - 1


def next_value(a, b):
    value = (a ^ (a << 23)) & MASK64
    a, b = b, (value ^ b ^ (value >> 17) ^ (b >> 26)) & MASK64
    return a, b, ((a + b) & MASK53) / (1 << 53)


def observations(path):
    rows = []
    with path.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            if b'"Math"' not in line or b'"random"' not in line:
                continue
            row = json.loads(line)
            if (row.get('interface'), row.get('member'), row.get('type')) != ('Math', 'random', 'call'):
                continue
            value = row.get('return')
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value < 1:
                raise ValueError('invalid random return at line ' + str(number))
            mantissa = value * (1 << 53)
            if mantissa != int(mantissa):
                raise ValueError('return is not an exact low53 output at line ' + str(number))
            frame = (row.get('stack') or [{}])[0]
            rows.append({'line': number, 'seq': row.get('seq'), 'value': value,
                         'script_sha256': hashlib.sha256(frame.get('file', '').encode()).hexdigest(),
                         'source_line': frame.get('line'), 'source_column': frame.get('col')})
    return rows


def constraints(z3, rows, timeout):
    first, second = z3.BitVecs('initial0 initial1', 64)
    a, b = first, second
    solver = z3.SolverFor('QF_BV')
    solver.set(timeout=timeout)
    solver.add(z3.Or(first != 0, second != 0))
    for row in rows:
        value = a ^ (a << 23)
        a, b = b, value ^ b ^ z3.LShR(value, 17) ^ z3.LShR(b, 26)
        solver.add(z3.Extract(52, 0, a + b) == int(row['value'] * (1 << 53)))
    return solver, first, second


def recover(rows, train=12, holdout=7, timeout=60000, max_gap=100000):
    import z3
    if train < 3 or holdout < 1 or len(rows) < train + holdout:
        raise ValueError('require at least 3 training outputs and 1 held-out output')
    solver, first, second = constraints(z3, rows[:train], timeout)
    status = solver.check()
    report = {'schema': 'ruyijs.inferred-random-state.v1',
              'algorithm': 'spidermonkey-xorshift128plus-low53-v1',
              'solver_version': z3.get_version_string(), 'fit_status': str(status),
              'training_count': train, 'holdout_count': holdout,
              'assumption': 'contiguous outputs in one realm starting at the first selected observation'}
    if status != z3.sat:
        return report
    model = solver.model()
    state = [model[first].as_long(), model[second].as_long()]
    report.update(state0=f'{state[0]:016x}', state1=f'{state[1]:016x}')
    a, b = state
    matches = []
    for row in rows[:train + holdout]:
        a, b, value = next_value(a, b)
        matches.append(value == row['value'])
    report['heldout_matches'] = matches[train:]
    if all(matches):
        unique, first, second = constraints(z3, rows[:train + holdout], timeout)
        unique.add(z3.Or(first != state[0], second != state[1]))
        status = unique.check()
        report['alternative_state_status'] = str(status)
        report['unique_under_assumption'] = status == z3.unsat
    a, b = state
    alignments = []
    for index, row in enumerate(rows):
        found = None
        for gap in range(max_gap + 1):
            a, b, value = next_value(a, b)
            if value == row['value']:
                found = gap
                break
        alignments.append({'observation': index, 'line': row['line'], 'skipped_draws': found})
        if found is None:
            break
    report['forward_alignments'] = alignments
    report['observations'] = rows
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--deps', type=Path, help='directory containing optional z3-solver installation')
    parser.add_argument('--train', type=int, default=12)
    parser.add_argument('--holdout', type=int, default=7)
    parser.add_argument('--timeout-ms', type=int, default=60000)
    parser.add_argument('--check-contiguous', action='store_true',
                        help='only test whether every observed value can be consecutive in one realm')
    args = parser.parse_args()
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))
    rows = observations(args.trace)
    if args.check_contiguous:
        import z3
        solver, _, _ = constraints(z3, rows, args.timeout_ms)
        status = solver.check()
        report = {'schema':'ruyijs.random-contiguity-check.v1', 'status':str(status),
                  'observations':len(rows), 'solver_version':z3.get_version_string(),
                  'assumption':'all recorded outputs are consecutive in one realm',
                  'candidate_applied':False}
    else:
        report = recover(rows, args.train, args.holdout, args.timeout_ms)
    report['input'] = str(args.trace.resolve())
    with args.trace.open('rb') as stream:
        report['input_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('observations','forward_alignments','state0','state1')}, indent=2))


if __name__ == '__main__':
    main()
