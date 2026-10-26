"""Map the hash-identified frame timer fixture using recorded registration sites."""
from collections import defaultdict
import hashlib
import json

from .async_evidence import context_key, load_rows
from .timer_identity_fixture import EDGES, RESOURCES
from .timer_lifecycle import prove_timers

SITES = {(7, 14): 'frame0', (7, 48): 'frame1', (9, 34): 'main',
         (10, 12): 'main', (11, 12): 'main', (13, 23): 'removed'}
TARGETS = {'main': 'window', 'frame0': "document.querySelectorAll('iframe')[0].contentWindow",
           'frame1': "document.querySelectorAll('iframe')[1].contentWindow",
           'removed': "document.querySelectorAll('iframe')[2].contentWindow"}


def marker_commands(rows, roles):
    contexts = {}; schedules = {}; fires = {}; markers = defaultdict(list); counts = {}
    for row in rows:
        if row['type'] in ('script_root', 'async_resume') and row.get('phase') == 'start':
            key = context_key(row)
            if key in contexts: raise ValueError('duplicate marker context')
            contexts[key] = row
        if row['type'] == 'async_schedule':
            key = context_key(row, 'async_context_id')
            if key in schedules: raise ValueError('duplicate marker schedule')
            schedules[key] = row
        if row['type'] == 'timer_lifecycle' and row['phase'] == 'fire':
            key = context_key(row)
            if key in fires: raise ValueError('duplicate timer fire context')
            fires[key] = row
    for row in rows:
        if row['type'] != 'call' or row.get('member') != 'setAttribute' or (row.get('args') or [None])[0] != 'data-timer-proof':
            continue
        key = context_key(row); chain = []; seen = set()
        while key not in fires:
            if key in seen or len(seen) >= 64: raise ValueError('cycle in marker ancestry')
            seen.add(key); chain.append(list(key)); parent = contexts.get(key)
            if parent is None: raise ValueError('marker context undeclared')
            if parent['type'] == 'script_root': key = context_key(parent, 'parent_execution_context_id')
            else:
                schedule = schedules.get((key[0], parent.get('schedule_session', key[1]), parent['async_context_id']))
                if schedule is None: raise ValueError('marker schedule undeclared')
                key = context_key(schedule, 'parent_execution_context_id')
        chain.append(list(key))
        markers[key].append({'label': row['args'][1], 'line': row['file_line'], 'ancestry': chain})
    if len({r['file'] for r in fires.values()}) != 1:
        raise ValueError('frame plan requires one recorded process/file order')
    commands = []
    for key, row in sorted(fires.items(), key=lambda item: item[1]['file_line']):
        timer = context_key(row, 'async_context_id')
        if not markers[key]: raise ValueError('timer fire has no output evidence')
        commands.append({'recorded_timer': list(timer), 'recorded_global': row['global_id'],
                         'role': roles[row['global_id']], 'handle': row['public_handle'],
                         'firings': counts.get(timer, 0), 'observations': markers[key]})
        counts[timer] = counts.get(timer, 0) + 1
    return commands


def compile_plan(folder):
    report = json.loads((folder / 'probe/result.json').read_text('utf-8'))
    case = next(c for c in report['cases'] if c['name'] == 'edges')
    if report['sources']['/async-timer-edges.js'] != hashlib.sha256(EDGES).hexdigest():
        raise ValueError('registration site adapter requires exact fixture source')
    for name in ('/edges', '/blank', '/async-timer-start.js'):
        if report['sources'][name] != hashlib.sha256(RESOURCES[name][1]).hexdigest():
            raise ValueError('fixture document topology changed')
    rows, sources = load_rows(folder / 'probe/edges')
    if sources != case['sources']: raise ValueError('recorded capture identity changed')
    proof = prove_timers(rows)
    if proof != case['proof']: raise ValueError('recorded lifecycle proof changed')
    lookup = {(r['file'], r['file_line']): r for r in rows}
    registrations = [r for r in rows if r['type'] == 'timer_lifecycle' and r['phase'] == 'register']
    roles = {}; reverse = {}; evidence = []
    for timer in proof['timers']:
        registration = next(r for r in registrations if list(context_key(r, 'async_context_id')) == timer['identity'])
        call = lookup[(registration['file'], timer['dom_line'])]; site = call['stack'][0]
        if not site['file'].endswith('/async-timer-edges.js') or (site['line'], site['col']) not in SITES:
            raise ValueError('unexpected timer registration site')
        role = SITES[site['line'], site['col']]; global_id = timer['global_id']
        if global_id in roles and roles[global_id] != role: raise ValueError('one recorded global maps to multiple roles')
        if role in reverse and reverse[role] != global_id: raise ValueError('one frame role maps to multiple globals')
        roles[global_id] = role; reverse[role] = global_id
        evidence.append({'timer': timer['identity'], 'global_id': global_id, 'role': role,
                         'register_line': timer['register_line'], 'dom_line': timer['dom_line'], 'site': site})
    if set(reverse) != set(TARGETS): raise ValueError('missing recorded frame role')
    commands = marker_commands(rows, roles)
    if len(commands) != 7 or [o['label'] for c in commands for o in c['observations']] != case['page']['events']:
        raise ValueError('recorded marker order differs from page')
    removed = [t for t in proof['timers'] if roles[t['global_id']] == 'removed']
    if len(removed) != 1 or removed[0]['terminal'] != 'clear_all' or removed[0]['fires']:
        raise ValueError('removed frame timer not retired')
    return {'schema': 'local.frame-timer-plan.v1', 'sources': sources, 'roles': reverse, 'targets': TARGETS,
            'registration_evidence': evidence, 'commands': commands, 'final_page': case['page'],
            'source_sha256': report['sources']['/async-timer-edges.js'], 'removed': removed[0],
            'scope': 'Exact local source sites; not a general DOM topology reconstruction.', 'full_goal_complete': False}
