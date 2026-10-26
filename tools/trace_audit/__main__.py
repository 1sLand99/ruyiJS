"""python -m tools.trace_audit RUN --output artifacts/trace-audit/report.json"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from . import binary, causal, jsonlines, network


def audit(root, progress=print):
    result = {'schema': 'ruyijs.trace-audit.v1', 'run': str(root.resolve()),
              'created_utc': datetime.now(timezone.utc).isoformat(),
              'jscall': [], 'jsonl': [], 'inventory': {}}
    ids_by_pid = {}
    for directory in sorted(p for p in root.iterdir() if p.is_dir() and p.name != 'profile'):
        files = [p for p in directory.rglob('*') if p.is_file()]
        result['inventory'][directory.name] = {'files': len(files), 'bytes': sum(p.stat().st_size for p in files)}
    for path in sorted((root / 'jscall').glob('*.dict.jsonl')):
        prefix = path.name.removesuffix('.dict.jsonl')
        funcs, stats, errors = jsonlines.dictionary(path)
        item = {'dictionary': path.name, 'functions': len(funcs), 'writer_stats': stats,
                'dictionary_errors': errors, 'source_sha256_functions': sum(bool(f.get('source_sha256')) for f in funcs.values())}
        bin_path = path.with_name(prefix + '.bin')
        if bin_path.exists():
            progress('calls: ' + bin_path.name)
            try:
                summary, ids = binary.calls(bin_path, funcs)
                item.update(summary)
                ids_by_pid[summary['pid']] = ids
                item['writer_record_count_matches'] = bool(stats is not None and stats.get('recorded') == summary.get('records', 0))
                detail = path.with_name(prefix + '.detail.bin')
                if detail.exists():
                    item['detail'] = binary.details(detail, ids, summary['pid'])
            except ValueError as error:
                item['binary_error'] = str(error)
        else:
            item['binary_absent'] = True
        result['jscall'].append(item)
    for kind in ('domtrace', 'event', 'descriptor', 'cookie', 'storage', 'eval', 'wasm', 'exception'):
        for path in sorted((root / kind).glob('*.jsonl')):
            progress('jsonl: ' + path.name)
            result['jsonl'].append(jsonlines.scan(path, root, ids_by_pid))
    result['network'] = network.scan(root, ids_by_pid)
    for path in sorted((root / 'http_packet').glob('*.jsonl')):
        result['jsonl'].append(jsonlines.scan(path, root, ids_by_pid))
    types, stats = Counter(), Counter()
    for item in result['jsonl']:
        types.update(item['types'])
        for row in item['writer_stats'].values():
            stats.update({k: v for k, v in row.items() if (k.startswith('dropped_') or k == 'io_errors') and isinstance(v, int)})
    result['record_types'] = dict(types)
    result['causal_graph'] = causal.graph(result['jsonl'])
    result['dom_sidecar_loss_counters'] = dict(stats)
    result['limitations'] = [
        'Resolved origin_call_id identifies an observed ancestor; caller-JIT gaps can hide immediate callers.',
        'Zero writer drops do not prove JIT, source, nondeterminism or realm coverage.',
        'JSONL field and byte counts are offline observations, not trace overhead measurements.',
        'No full execution replay or original network-byte equality is asserted.',
        'This capture uses PID-scoped binary IDs; process nonce joins require a richer binary schema.']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.run.is_dir():
        parser.error('run directory does not exist')
    report = audit(args.run, lambda value: print(value, flush=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(args.output), 'record_types': report['record_types'],
                      'network': report['network']['counts']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
