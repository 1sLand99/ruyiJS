"""Extract measured navigation fields with stable object/document provenance."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

FIELDS = ('requestStart', 'responseStart', 'responseEnd', 'transferSize', 'encodedBodySize', 'decodedBodySize')


def derive(group, packets, roots):
    rows = group['observations']
    values = {}
    for row in rows:
        values.setdefault(row['member'], []).append(row['value'])
    names = set(values.get('name', []))
    if len(names) != 1:
        raise ValueError('missing or changing navigation name')
    url = next(iter(names))
    if not isinstance(url, str) or url not in roots or len(packets.get(url, [])) != 1:
        raise ValueError('navigation name lacks unique document and script-root evidence')
    if values.get('entryType', []) != ['navigation'] * len(values.get('entryType', [])) or not values.get('entryType'):
        raise ValueError('entryType is not verified navigation')
    if any(url not in row['stack_urls'] for row in rows):
        raise ValueError('getter call stack does not identify the named document')
    fields, transformations = {}, []
    for field in FIELDS:
        observed = values.get(field, [])
        if not observed:
            continue
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in observed):
            raise ValueError('invalid measured field ' + field)
        if len(set(observed)) != 1:
            raise ValueError('changing field requires a phased recording: ' + field)
        value = observed[0]
        if field.endswith('Size') and (value != int(value) or value > 2**53 - 1):
            raise ValueError('invalid byte size')
        fields[field] = value
    durations = values.get('duration', [])
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError('invalid navigation duration')
    nonzero = {value for value in durations if value > 0}
    if len(nonzero) > 1:
        raise ValueError('multiple positive durations need stronger lifecycle evidence')
    if nonzero:
        if any(a > b for a, b in zip(durations, durations[1:])):
            raise ValueError('navigation duration went backwards')
        fields['loadEventEnd'] = next(iter(nonzero))
        transformations.append({'target': 'loadEventEnd', 'source': 'duration',
            'basis': 'PerformanceNavigationTiming startTime is zero; duration equals loadEventEnd',
            'kind': 'derived from navigation-entry semantics, not a direct loadEventEnd getter'})
    if not fields:
        raise ValueError('no supported measured fields')
    ordered = [fields[name] for name in ('requestStart', 'responseStart', 'responseEnd', 'loadEventEnd') if name in fields]
    if ordered != sorted(ordered):
        raise ValueError('measured offsets are inconsistent')
    return {'url': url, 'fields': fields}, {'packet': packets[url][0], 'transformations': transformations, **group}


def extract(run, process_id):
    path = run / 'domtrace' / f'trace_process_{process_id}.jsonl'
    packets = {}
    for packet_path in sorted((run / 'http_packet').glob('*.http_packet.json')):
        packet = json.loads(packet_path.read_text('utf-8'))
        if packet.get('status') == 200 and packet['meta'].get('requestKind') in ('document', 'subdocument'):
            packets.setdefault(packet['url'], []).append({'file': packet_path.name,
                'sha256': hashlib.sha256(packet_path.read_bytes()).hexdigest(),
                'body_sha256': packet['responseBody'].get('sha256')})
    roots, groups = set(), {}
    process = None
    stop = None
    with path.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if row.get('type') == 'trace_init':
                process = row.get('process_instance_id')
            if row.get('type') == 'script_root' and row.get('phase') == 'start':
                roots.add(row.get('url'))
            if row.get('interface') == 'XMLHttpRequest' and row.get('member') == 'send':
                stop = number
                break
            receiver = row.get('thisObj') or {}
            if row.get('type') != 'get' or receiver.get('class') != 'PerformanceNavigationTiming':
                continue
            identity = process, receiver.get('id'), receiver.get('nativeId')
            if not all(identity) or identity[1] == '0000000000000000':
                raise ValueError('navigation receiver identity missing')
            member = row.get('member', '').removeprefix('get ')
            if member not in (*FIELDS, 'duration', 'name', 'entryType'):
                continue
            group = groups.setdefault(identity, {'process_instance_id': process, 'object': receiver, 'observations': []})
            group['observations'].append({'line': number, 'seq': row.get('seq'), 'member': member,
                'value': row.get('value'), 'origin_call_id': str(row.get('origin_call_id', 0)),
                'stack_urls': list(dict.fromkeys(frame.get('file') for frame in row.get('stack', [])))})
    if stop is None:
        raise ValueError('no first XHR send boundary; this extractor requires a bounded prefix')
    documents, evidence, rejected = [], [], []
    for group in groups.values():
        try:
            document, proof = derive(group, packets, roots)
            documents.append(document)
            evidence.append(proof)
        except ValueError as error:
            rejected.append({'object': group['object'], 'reason': str(error)})
    counts = Counter(doc['url'] for doc in documents)
    if any(count > 1 for count in counts.values()):
        raise ValueError('multiple navigation identities for one URL need explicit occurrence mapping')
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'schema': 'ruyijs.recorded-navigation-inputs.v1', 'documents': documents,
        'evidence': evidence, 'rejected': rejected, 'source': {'file': str(path), 'sha256': sha, 'stop_line': stop},
        'scope': 'one process prefix before first XHR.send; unobserved fields and schedule remain unresolved'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--process-id', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = extract(args.run, args.process_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps({'documents': len(report['documents']), 'rejected': report['rejected'],
                      'fields': [row['fields'] for row in report['documents']]}))


if __name__ == '__main__':
    main()
