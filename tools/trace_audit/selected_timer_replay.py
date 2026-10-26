"""Drive native ruyijs timer selection from preserved local Firefox lifecycle IDs."""
import argparse
import copy
import json
from pathlib import Path
import sys

from .async_contract import marker_groups
from .async_evidence import load_rows
from .rng_probe import digest
from .timer_lifecycle import prove_timers

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python')); sys.path.insert(0, str(ROOT / 'tests'))
from ruyijs import Context
from iframe_client import CClient


def compile_plan(folder, name):
    capture = json.loads((folder / 'probe/result.json').read_text('utf-8'))
    case = next(row for row in capture['cases'] if row['name'] == name)
    rows, sources = load_rows(folder / 'probe' / name)
    if sources != case['sources']: raise ValueError('capture source identity changed')
    proof = prove_timers(rows)
    if proof != case['proof']: raise ValueError('timer identity proof changed')
    script = Path(__file__).with_name('async_mapping.js')
    if digest(script) != capture['sources']['/async-mapping.js']:
        raise ValueError('fixture source differs from captured code')
    groups = marker_groups(rows)
    timers = {tuple(row['identity']): row for row in proof['timers']}
    fires = [row for row in rows if row['type'] == 'timer_lifecycle' and row['phase'] == 'fire']
    if len({r['global_id'] for r in fires}) != 1:
        raise ValueError('this adapter requires a single captured main global')
    commands = []; counts = {}
    for fire in fires:
        key = (fire['process_instance_id'], fire['session'], fire['async_context_id'])
        matches = [g for g in groups if g['root_context'] == [key[0], key[1], fire['execution_context_id']]]
        if len(matches) != 1: raise ValueError('fire does not identify one output checkpoint')
        commands.append({'recorded_timer': list(key), 'recorded_execution_context': fire['execution_context_id'],
                         'public_handle': timers[key]['handle'], 'expected_firings': counts.get(key, 0),
                         'labels': matches[0]['labels']})
        counts[key] = counts.get(key, 0) + 1
    if len(commands) != 4 or len(groups) != 5: raise ValueError('unexpected bounded fixture structure')
    return {'schema': 'local.selected-timer-plan.v1', 'capture_case': name, 'sources': sources,
            'source_sha256': digest(script), 'initial_labels': groups[0]['labels'], 'commands': commands,
            'cancelled_handles': [r['handle'] for r in proof['timers'] if r['terminal'] == 'cancel'],
            'final_labels': case['page']['events'], 'full_goal_complete': False}


def execute(plan, adapter, reorder=False):
    c = Context(shell=ROOT / 'dist/js.exe') if adapter == 'Python' else CClient()
    result = {'adapter': adapter, 'capture_case': plan['capture_case'], 'steps': [], 'counterfactual': reorder}
    try:
        def rpc(action, **fields):
            return c._event_loop(action, **fields) if adapter == 'Python' else c.call('event_loop', action=action, **fields)
        c.configure_clock('logical', epoch_ms=1700000000000)
        rpc('configure_timer_replay', enabled=True)
        c.load_page('http://localhost/selected-timer-proof/', '<!doctype html>')
        c.eval(Path(__file__).with_name('async_mapping.js').read_text('utf-8'))
        page = c.eval('mappingProof')
        if page['events'] != plan['initial_labels']: raise ValueError('initial script checkpoint differs')
        commands = copy.deepcopy(plan['commands'])
        if reorder: commands[0], commands[1] = commands[1], commands[0]
        expected = list(plan['initial_labels']); mapping = {}; realm = None
        for command in commands:
            pending = rpc('pending_timers')
            if any(r['public_handle'] in plan['cancelled_handles'] for r in pending):
                raise ValueError('cancelled capture timer still pending')
            matches = [r for r in pending if r['public_handle'] == command['public_handle']]
            if len(matches) != 1: raise ValueError('recorded public timer is absent or ambiguous')
            selected = matches[0]
            if realm is None: realm = selected['realm_id']
            if selected['realm_id'] != realm: raise ValueError('unexpected replay realm')
            key = tuple(command['recorded_timer'])
            identity = [selected['realm_id'], selected['task_id']]
            if key in mapping and mapping[key] != identity: raise ValueError('timer mapping changed')
            mapping[key] = identity
            if selected['firings'] != command['expected_firings']: raise ValueError('firing occurrence differs')
            before = rpc('status')
            at = max(before['now_ms'], selected['due_ms'])
            outcome = rpc('run_timer', task_id=selected['task_id'], expected_firings=command['expected_firings'], at_ms=at)
            expected += command['labels']
            page = c.eval('mappingProof')
            if page['events'] != expected or page['errors'] or outcome['executed'] != 1:
                raise ValueError('selected native timer output differs')
            result['steps'].append({'command': command, 'selected': selected, 'at_ms': at,
                                    'outcome': outcome, 'observed_labels': page['events']})
        if not page['done'] or rpc('pending_timers'): raise ValueError('selected plan not fully consumed')
        if not reorder and page['events'] != plan['final_labels']: raise ValueError('capture final output differs')
        if reorder and page['events'] == plan['final_labels']: raise ValueError('counterfactual did not control order')
        result.update(passed=True, final=page, mapped_timers=len(mapping), deterministic_scope='single local timer-only main realm')
    finally: c.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'local.selected-timer-replay.v1', 'runs': [], 'controls': [],
              'shell_sha256': digest(ROOT / 'dist/js.exe'), 'client_sha256': digest(ROOT / 'dist/ruyijs_client.dll'),
              'full_goal_complete': False, 'limitations': ['Single fixed main realm; handle correspondence validated in bounded source.',
                 'Uses owner due times, not captured wall time.', 'No messages, worker scheduling, network or original webpage closure.']}
    for name in ('core', 'calls'):
        plan = compile_plan(args.capture.resolve(), name)
        path = args.output / (name + '-plan.json')
        path.write_text(json.dumps(plan, indent=2) + '\n', 'utf-8')
        for adapter in ('Python', 'C'):
            report['runs'].append(execute(plan, adapter))
            print(json.dumps({'capture': name, 'adapter': adapter, 'passed': True}), flush=True)
        if name == 'core':
            for adapter in ('Python', 'C'): report['controls'].append(execute(plan, adapter, reorder=True))
        (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    report['passed'] = True
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')


if __name__ == '__main__': main()
