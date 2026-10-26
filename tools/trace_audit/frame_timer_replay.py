"""Replay recorded cross-frame public timers through explicit host realm binding."""
import argparse
import json
from pathlib import Path
import sys

from .frame_timer_plan import compile_plan
from .timer_identity_fixture import EDGES, RESOURCES
from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python')); sys.path.insert(0, str(ROOT / 'tests'))
from ruyijs import Context
from iframe_client import CClient


def execute(plan, adapter, reverse_binding=False, wrong_binding=False):
    c = Context(shell=ROOT / 'dist/js.exe') if adapter == 'Python' else CClient()
    result = {'adapter': adapter, 'reverse_binding': reverse_binding, 'wrong_binding': wrong_binding,
              'bindings': {}, 'steps': [], 'passed': False}
    try:
        def rpc(action, **fields):
            return c._event_loop(action, **fields) if adapter == 'Python' else c.call('event_loop', action=action, **fields)
        def realm(target):
            return c.timer_realm(target) if adapter == 'Python' else c.call('timer_realm', target=target)
        c.configure_clock('logical', epoch_ms=1700000000000)
        rpc('configure_timer_replay', enabled=True)
        origin = 'http://localhost'
        for name in ('/blank', '/async-timer-edges.js'):
            mime, body = RESOURCES[name]; c.put_resource(origin + name, body.decode('utf-8'), headers=[['Content-Type', mime]])
        c.load_page(origin + '/edges', RESOURCES['/edges'][1].decode('utf-8'))
        roles = list(plan['targets'])
        if reverse_binding: roles.reverse()
        for role in roles: result['bindings'][role] = realm(plan['targets'][role])
        if len(set(result['bindings'].values())) != 4: raise ValueError('actual Window bindings are not distinct')
        if rpc('pending_timers'): raise ValueError('binding query scheduled a timer')
        c.eval(RESOURCES['/async-timer-start.js'][1].decode('utf-8'))
        initial = c.eval('timerProof')
        if initial['events'] or initial['handles'] != [1, 1] or initial['errors']:
            raise ValueError('cross-frame script checkpoint differs')
        if wrong_binding:
            result['bindings']['frame0'], result['bindings']['frame1'] = result['bindings']['frame1'], result['bindings']['frame0']
        mapping = {}; expected = []
        for command in plan['commands']:
            pending = rpc('pending_timers')
            if any(t['realm_id'] == result['bindings']['removed'] for t in pending):
                raise ValueError('removed frame still owns a pending timer')
            found = [t for t in pending if t['realm_id'] == result['bindings'][command['role']] and t['public_handle'] == command['handle']]
            if len(found) != 1: raise ValueError('recorded frame/handle mapping absent or ambiguous')
            task = found[0]; key = tuple(command['recorded_timer'])
            if key in mapping and mapping[key] != task['task_id']: raise ValueError('interval remapped to another task')
            mapping[key] = task['task_id']
            if task['firings'] != command['firings']: raise ValueError('recorded repeat occurrence differs')
            at = max(rpc('status')['now_ms'], task['due_ms'])
            outcome = rpc('run_timer', task_id=task['task_id'], expected_firings=command['firings'], at_ms=at)
            expected += [o['label'] for o in command['observations']]
            page = c.eval('timerProof')
            result['steps'].append({'command': command, 'task': task, 'at_ms': at, 'outcome': outcome, 'page': page})
            if page['events'] != expected or page['errors'] or outcome['executed'] != 1:
                raise ValueError('recorded cross-frame output differs')
        if page != plan['final_page'] or rpc('pending_timers'): raise ValueError('final cross-frame state differs')
        result.update(passed=True, final=page, mapped_live_timers=len(mapping), retired_realm=result['bindings']['removed'])
    except Exception as error:
        result['error'] = str(error)
    finally: c.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    plan = compile_plan(args.capture.resolve())
    path = args.output / 'plan.json'; path.write_text(json.dumps(plan, indent=2) + '\n', 'utf-8')
    plan = json.loads(path.read_text('utf-8'))
    report = {'schema': 'local.frame-timer-replay.v1', 'plan_sha256': digest(path), 'runs': [], 'controls': [],
              'shell_sha256': digest(ROOT / 'dist/js.exe'), 'client_sha256': digest(ROOT / 'dist/ruyijs_client.dll'),
              'full_goal_complete': False}
    for adapter in ('Python', 'C'):
        for reverse in (False, True):
            run = execute(plan, adapter, reverse_binding=reverse); report['runs'].append(run)
            (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
            print(json.dumps({k: run.get(k) for k in ('adapter', 'reverse_binding', 'passed', 'error')}), flush=True)
        run = execute(plan, adapter, wrong_binding=True)
        run['rejected_as_expected'] = not run['passed'] and run.get('error') == 'recorded cross-frame output differs'
        report['controls'].append(run)
    report['passed'] = all(r['passed'] for r in report['runs']) and all(r['rejected_as_expected'] for r in report['controls'])
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    return int(not report['passed'])


if __name__ == '__main__': raise SystemExit(main())
