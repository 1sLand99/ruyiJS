"""Resolve observed asynchronous edges; never infer order from wall-clock sorting."""
from collections import Counter


def graph(files):
    schedules, sends, edges, counts = {}, {}, [], Counter()
    events = [(file['path'], row) for file in files for row in file.get('causal_events', [])]
    def identity(row, resume=False):
        session = row.get('schedule_session' if resume else 'session', row.get('session', 0))
        return (row.get('trace_run_id'), row.get('process_instance_id'), row['pid'],
                session, row.get('async_context_id'))

    for path, row in events:
        kind = row['type']
        if kind == 'async_schedule':
            key = identity(row)
            counts['duplicate_schedule_ids'] += key in schedules
            schedules.setdefault(key, []).append((path, row))
        if kind == 'message_send':
            if row.get('message_id'):
                sends.setdefault(row['message_id'], []).append((path, row))
            else:
                counts['send_without_message_id'] += 1
            counts['message_sends'] += 1
            counts['message_sends_without_async_context'] += not bool(row.get('source_async_context_id'))
    for path, row in events:
        if row['type'] == 'async_resume' and row.get('phase') == 'start':
            counts['resume_enters'] += 1
            sources = schedules.get(identity(row, resume=True), [])
            counts['resume_without_schedule'] += not bool(sources)
            counts['resume_with_ambiguous_schedule'] += len(sources) > 1
            if len(sources) == 1:
                source = sources[0]
                edges.append({'relation': 'schedule_to_resume', 'source_file': source[0],
                              'source_line': source[1]['line'], 'target_file': path,
                              'target_line': row['line'], 'pid': row['pid'],
                              'async_context_id': row.get('async_context_id'),
                              'execution_context_id': row.get('execution_context_id')})
        if row['type'] == 'message_receive':
            counts['message_receives'] += 1
            sources = sends.get(row.get('message_id'), [])
            counts['receive_without_send'] += not bool(sources)
            counts['receive_with_ambiguous_send'] += len(sources) > 1
            if len(sources) == 1:
                source = sources[0]
                edges.append({'relation': 'send_to_receive', 'source_file': source[0],
                              'source_line': source[1]['line'], 'target_file': path,
                              'target_line': row['line'], 'message_id': row.get('message_id')})
    return {'counts': dict(counts), 'edges': edges,
            'scope': 'Explicit schedule/resume and message IDs only; no reconstructed total execution order.'}
