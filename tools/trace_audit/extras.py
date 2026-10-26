"""Additional source-integrity and nondeterministic-API evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def entropy(root):
    counts, values, examples = Counter(), Counter(), {}
    names = ('Math', 'Crypto', 'Date', 'Performance')
    markers = tuple(('"' + name + '"').encode() for name in names)
    for path in (root / 'domtrace').glob('*.jsonl'):
        with path.open('rb') as stream:
            for line_no, line in enumerate(stream, 1):
                if not any(marker in line for marker in markers):
                    continue
                obj = json.loads(line)
                if obj.get('interface') not in names:
                    continue
                key = '|'.join(obj.get(k, '') for k in ('interface', 'member', 'type'))
                counts[key] += 1
                values[key] += obj.get('return') is not None
                examples.setdefault(key, {'file': path.name, 'line': line_no, 'fields': list(obj)})
    return {'counts': dict(counts), 'non_null_return_field': dict(values), 'examples': examples,
            'scope': 'Recorded native-boundary calls only; no assertion of JIT-inlined API coverage.'}


def sources(root):
    result = {'eval': Counter(), 'wasm': [], 'errors': []}
    seen = set()
    for path in (root / 'eval').glob('*.jsonl'):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                obj = json.loads(line)
                if obj.get('type') != 'dynamicCode':
                    continue
                result['eval']['records'] += 1
                filename = obj.get('file')
                if not filename:
                    result['eval']['no_source_file'] += 1
                    continue
                source = (root / filename).resolve()
                if not source.is_relative_to(root.resolve()) or not source.is_file():
                    result['errors'].append({'missing_or_external': filename})
                    continue
                matches = hashlib.sha256(source.read_bytes()).hexdigest() == obj['sha256']
                result['eval']['hash_matches' if matches else 'hash_mismatches'] += 1
                seen.add(filename)
    result['eval']['unique_files'] = len(seen)
    for path in (root / 'wasm').glob('*.jsonl'):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                obj = json.loads(line)
                if obj.get('type') == 'wasm':
                    result['wasm'].append({k: obj.get(k) for k in
                                          ('op', 'phase', 'byteLength', 'file', 'dumped', 'dumpReason')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('source-evidence', sources(args.run)), ('entropy-evidence', entropy(args.run))]:
        (args.output / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n', 'utf-8')
        print(name, flush=True)


if __name__ == '__main__':
    main()
