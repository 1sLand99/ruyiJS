"""Summarize real-page RNG capture coverage without publishing URLs or seeds."""
import argparse
from collections import Counter
import json
from pathlib import Path
from urllib.parse import urlsplit

from .rng_probe import digest


def summarize(root):
    files, groups, gaps = [], {}, []
    types = Counter()
    random_calls = 0
    for path in sorted((root / 'domtrace').glob('*.jsonl')):
        count = 0
        with path.open('rb') as stream:
            for number, line in enumerate(stream, 1):
                row = json.loads(line)
                count += 1
                types[row.get('type', '<missing>')] += 1
                if (row.get('interface'), row.get('member'), row.get('type')) == ('Math', 'random', 'call'):
                    random_calls += 1
                if row.get('type') == 'rng_trace_gap':
                    gaps.append({'file': path.name, 'line': number, 'reason': row['reason']})
                if row.get('type') != 'realm_rng':
                    continue
                identity = row['process_instance_id'], row['realm_id']
                group = groups.setdefault(identity, {'identity': identity, 'phases': Counter(),
                    'script_hosts': set(), 'contexts': set(), 'available': 0, 'truncated_urls': 0})
                group['phases'][row['phase']] += 1
                group['script_hosts'].add(urlsplit(row['script_url']).hostname or '<non-http>')
                group['contexts'].add(row['execution_context_id'])
                group['available'] += row['available']
                group['truncated_urls'] += row['script_url_truncated']
        files.append({'file': path.name, 'bytes': path.stat().st_size, 'rows': count, 'sha256': digest(path)})
    rows = []
    for group in groups.values():
        group['script_hosts'] = sorted(group['script_hosts'])
        group['contexts'] = sorted(group['contexts'])
        rows.append(group)
    return {'schema': 'rng.capture-coverage.v1', 'files': files, 'record_types': dict(types),
        'realms': rows, 'gaps': gaps, 'observed_native_random_calls': random_calls,
        'limitations': ['Script association is not a document identity declaration.',
            'Native random call observations omit JIT-inlined calls and carry no new RNG realm ID.',
            'No full stream or request equality follows from capture presence.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps({'realms': len(result['realms']), 'rng_records': result['record_types'].get('realm_rng', 0),
        'gaps': len(result['gaps']), 'observed_native_random_calls': result['observed_native_random_calls'],
        'core_bytes': sum(f['bytes'] for f in result['files'])}))


if __name__ == '__main__':
    main()
