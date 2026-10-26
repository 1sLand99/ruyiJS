"""Stream JSONL metadata and count evidence without exporting captured values."""
from collections import Counter, defaultdict
import json

CAUSAL_TYPES = {'async_schedule', 'async_resume', 'script_root', 'message_send',
                'message_receive', 'message_drop', 'worker_created', 'worker_terminated'}
CAUSAL_FIELDS = {'type', 'phase', 'pid', 'seq', 'execution_context_id', 'async_context_id',
                 'parent_execution_context_id', 'async_parent_call_id', 'parent_call_id',
                 'origin_call_id', 'async_cause', 'script_kind', 'message_id', 'message_kind',
                 'source_pid', 'source_execution_context_id', 'source_async_context_id',
                 'receiver_execution_context_id', 'source_global_id', 'target_global_id',
                 'source_global_kind', 'target_global_kind', 'process_instance_id',
                 'trace_run_id', 'session', 'schedule_session'}


def rows(path, errors):
    with path.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError('record is not an object')
            except (ValueError, UnicodeError) as error:
                if len(errors) < 20:
                    errors.append({'line': number, 'error': type(error).__name__})
                yield number, None
                continue
            yield number, obj


def dictionary(path):
    funcs, stats, errors = {}, [], []
    for line, row in rows(path, errors):
        if row is None:
            continue
        kind = row.get('type')
        if kind == 'jscall_stats':
            stats.append(row)
        elif 'func_id' in row:
            funcs.setdefault(row['func_id'], {}).update(row)
    return funcs, stats[-1] if stats else None, errors


def scan(path, root, call_ids):
    from .binary import contains
    kinds, api, correlated = Counter(), Counter(), defaultdict(Counter)
    fields, stats, init, examples = defaultdict(Counter), {}, [], {}
    errors, malformed = [], 0
    causal = []
    timestamps = []
    line_count = 0
    for line, row in rows(path, errors):
        line_count = line
        if row is None:
            malformed += 1
            continue
        kind = row.get('type', row.get('kind', row.get('schema', 'unknown')))
        kinds[kind] += 1
        if kind in CAUSAL_TYPES:
            identity = {k: init[-1][k] for k in ('trace_run_id', 'process_instance_id')
                        if init and k in init[-1]}
            causal.append({'line': line, **identity, **{k: v for k, v in row.items() if k in CAUSAL_FIELDS}})
        for name in row:
            fields[kind][name] += 1
        if kind == 'trace_init':
            init.append(row)
        if kind.endswith('_stats') or kind == 'http_packet_writer_stats.v1':
            row = {k: v for k, v in row.items() if k not in ('document_channels', 'recent_errors')}
            stats[kind] = row
        if len(examples) < 100 and kind not in examples:
            examples[kind] = {'line': line, 'fields': list(row)}
        if isinstance(row.get('ts'), (int, float)):
            if not timestamps:
                timestamps = [row['ts'], row['ts']]
            else:
                timestamps[0] = min(timestamps[0], row['ts'])
                timestamps[1] = max(timestamps[1], row['ts'])
        if kind in ('get', 'set', 'call'):
            api['|'.join(str(row.get(k, '')) for k in ('interface', 'member', 'type'))] += 1
        if 'origin_call_id' in row:
            counts = correlated[kind]
            counts['rows'] += 1
            call = row['origin_call_id']
            if call:
                counts['nonzero'] += 1
                ids = call_ids.get(row.get('pid'), ())
                counts['resolved' if contains(ids, call) else 'unresolved'] += 1
    return {'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size,
            'lines': line_count, 'malformed_rows': malformed, 'errors': errors,
            'types': dict(kinds), 'fields_by_type': {k: dict(v) for k, v in fields.items()},
            'origin_links': {k: dict(v) for k, v in correlated.items()},
            'top_apis': api.most_common(30), 'init': init, 'writer_stats': stats,
            'timestamp_range_raw': timestamps, 'schema_examples': examples, 'causal_events': causal}
