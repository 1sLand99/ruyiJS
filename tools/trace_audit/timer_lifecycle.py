"""Verify explicit Window timer registration/lifecycle joins in preserved core logs."""
from collections import Counter, defaultdict

from .async_evidence import context_key


def prove_timers(rows, require_complete=True):
    events = [row for row in rows if row['type'] == 'timer_lifecycle']
    gaps = [row for row in rows if row['type'] == 'timer_trace_gap']
    if require_complete and gaps:
        raise ValueError('timer event budget gap')
    if not events:
        raise ValueError('no timer lifecycle evidence')
    stats = [r for r in rows if r['type'] == 'domtrace_writer_stats']
    loss_fields = ('dropped_full', 'dropped_contention', 'dropped_oom', 'dropped_oversize', 'dropped_writer_failed', 'io_errors')
    if not stats or any(r.get(field, 0) for r in stats for field in loss_fields):
        raise ValueError('writer statistics absent or lossy')
    schedules = defaultdict(list); resumes = defaultdict(list); registrations = defaultdict(list)
    for row in rows:
        if row['type'] == 'async_schedule': schedules[context_key(row, 'async_context_id')].append(row)
        if row['type'] == 'async_resume' and row.get('phase') == 'start': resumes[context_key(row)].append(row)
        if row['type'] == 'call' and row.get('interface') == 'Window' and row.get('member') in ('setTimeout', 'setInterval'):
            key = (*context_key(row), row.get('return'), (row.get('thisObj') or {}).get('nativeId'))
            registrations[key].append(row)
    timers = {}; event_indices = defaultdict(list)
    for row in events:
        key = context_key(row, 'async_context_id')
        phase = row['phase']
        event_indices[row['process_instance_id']].append(row['event_index'])
        if phase == 'register':
            if key in timers:
                raise ValueError('duplicate timer registration')
            declaration = schedules.get(key, [])
            if len(declaration) != 1:
                raise ValueError('timer has missing or ambiguous schedule')
            schedule = declaration[0]
            if (context_key(schedule, 'parent_execution_context_id') != context_key(row) or
                    schedule['async_parent_call_id'] != row['origin_call_id']):
                raise ValueError('timer schedule parent identity differs')
            expected_cause = 'set_interval' if row['repeating'] else 'set_timeout'
            if schedule['async_cause'] != expected_cause:
                raise ValueError('timer kind differs from schedule')
            call_key = (*context_key(row), row['public_handle'], row['global_native_id'])
            calls = registrations.get(call_key, [])
            if len(calls) != 1:
                raise ValueError('timer DOM registration is not uniquely joined')
            call = calls[0]
            if call['member'] != ('setInterval' if row['repeating'] else 'setTimeout'):
                raise ValueError('timer registration API differs')
            args = call.get('args', [])
            if len(args) > 1 and type(args[1]) is int and args[1] != row['delay_ms']:
                raise ValueError('timer requested delay differs')
            timers[key] = {'registration': row, 'dom_line': call['file_line'], 'fires': [], 'finishes': [],
                           'terminal': None, 'running': None}
            continue
        timer = timers.get(key)
        if timer is None:
            raise ValueError('lifecycle event has no admitted registration')
        start = timer['registration']
        if any(start[field] != row[field] for field in ('global_id', 'global_native_id', 'public_handle')):
            raise ValueError('timer owner/handle identity changed')
        if phase == 'fire':
            if timer['terminal'] or timer['running'] is not None:
                raise ValueError('cancelled, finished or already running timer fired')
            declarations = resumes.get(context_key(row), [])
            if len(declarations) != 1 or context_key(declarations[0], 'async_context_id') != key:
                raise ValueError('timer fire lacks unique matching resume')
            timer['running'] = row['execution_context_id']
            timer['fires'].append(row['execution_context_id'])
        elif phase == 'finish':
            if timer['running'] != row['execution_context_id']:
                raise ValueError('timer finish does not close its fire context')
            timer['finishes'].append(row['execution_context_id']); timer['running'] = None
            if not row['repeating'] and not timer['terminal']: timer['terminal'] = 'finished'
        elif phase in ('cancel', 'clear_all'):
            if timer['terminal']:
                raise ValueError('duplicate timer terminal event')
            timer['terminal'] = phase
        else:
            raise ValueError('unknown timer lifecycle phase')
    for values in event_indices.values():
        if values != list(range(1, len(values) + 1)):
            raise ValueError('timer event index lost or reordered')
    if require_complete and any(value['running'] is not None or not value['terminal'] for value in timers.values()):
        raise ValueError('timer lifecycle remains unfinished')
    return {'registrations': len(timers), 'phases': dict(Counter(r['phase'] for r in events)),
            'gaps': len(gaps), 'timers': [{'identity': list(key), 'global_id': value['registration']['global_id'],
                'handle': value['registration']['public_handle'], 'register_line': value['registration']['file_line'],
                'dom_line': value['dom_line'], 'fires': value['fires'], 'finishes': value['finishes'],
                'terminal': value['terminal']} for key, value in timers.items()]}
