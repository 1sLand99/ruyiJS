"""Audit the current Worker pipe boundary for record-driven message selection."""
import argparse
import hashlib
import json
from pathlib import Path

from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    files = ['src/web_workers/child.cpp', 'src/web_workers/poll.cpp', 'src/web_workers/process.cpp',
             'src/web_workers/process.h', 'src/web_workers/clone.cpp', 'src/web_workers/clone.h',
             'src/web_workers/state.h', 'src/runtime/rpc.cpp', 'src/execution_scheduling/realm.h',
             'src/execution_scheduling/state.h', 'src/runtime/window_message_ports.cpp']
    source = {name: {'bytes': (ROOT / name).stat().st_size, 'sha256': digest(ROOT / name)} for name in files}
    concurrent = json.loads((ROOT / 'artifacts/concurrent-proof-20261024/final-proof.json').read_text('utf-8'))
    enabled = [case for case in concurrent['cases'] if case['mode'] in ('core', 'calls')]
    messages = sum(case['proof']['messages'] for case in enabled)
    cross_process = sum(case['proof']['cross_process_messages'] for case in enabled)
    result = {'schema': 'local.worker-message-boundary.v1', 'sources': source,
              'concurrent_capture_cases': len(enabled), 'messages_checked': messages,
              'cross_process_messages_checked': cross_process,
              'parent_scheduler_selection': False, 'child_scheduler_selection': False,
              'shared_task_identity': False, 'payload_used_as_identity': False,
              'wall_time_used_as_identity': False, 'full_goal_complete': False,
              'findings': [
                  'Parent web_workers::Poll chooses an active WorkerRecord/process pipe and schedules one parent poll callback.',
                  'Child::Serve reads a pipe frame and calls its own Interaction/engine checkpoint; child task identity is not exposed to parent RPC.',
                  'Worker clone frames preserve structured data/version but carry no trace message_id, source sequence, source/target realm token or parent task id.',
                  'runtime::rpc.cpp exposes the parent Context pipe only; no child event_loop endpoint exists.',
                  'The concurrent proof joins Firefox message_id/process/session/context statically and therefore does not prove ruyijs Worker task selection.'
              ],
              'required_token_fields': ['process_instance_id', 'trace_session', 'source_global_id',
                                        'target_global_id', 'message_sequence', 'message_kind',
                                        'source_execution_context_id', 'source_async_context_id'],
              'next_owner_boundary': 'Carry the token through Worker pipe frame and child queue owner, then expose a bounded child selection RPC or parent relay with explicit readiness.'}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    (args.output / 'WORKER_MESSAGE_BOUNDARY.md').write_text('\n'.join([
        '# Worker message boundary: static proof versus ruyijs selection', '',
        'The current concurrent trace proves explicit Firefox message lineage, including',
        f"{messages} messages and {cross_process} cross-process messages in the enabled captures.",
        'It does not prove that ruyijs can choose a Worker message task from that record.', '',
        '## Current runtime path', '',
        'The parent `web_workers::Poll` scans active WorkerRecord pipes and consumes at most',
        'one ready frame through a parent Scheduling callback. The independent Worker',
        '`Child::Serve` reads its pipe, dispatches a decoded message in its own JS realm,',
        'runs its own checkpoint, and continues its own loop. Parent `event_loop` RPC has',
        'no child endpoint or child task ID.', '',
        'The existing structured-clone frame contains only clone version and bytes. It has',
        'no message_id, source/target realm token, process/session identity, sequence or',
        'recorded ready state. Payload text is deliberately equal in the concurrent fixture,',
        'so payload matching would be ambiguous; wall time is not a causal identity.', '',
        '## Required implementation boundary', '',
        'A future Worker replay slice must carry an explicit bounded token through the pipe:',
        '`process_instance_id`, `trace_session`, source/target global IDs, message sequence',
        'and kind, source execution/async context IDs, plus a child task identity and ready',
        'state. The child owner must validate the token before dispatch. Parent selection',
        'cannot claim completion until the child acknowledges the selected task and its',
        'engine checkpoint. Termination, pipe closure, queue limits and stale tokens need',
        'negative cases. This belongs in WebWorkers/child ownership plus the existing',
        'Scheduling adapter; it is not a timer or WindowMessaging-only extension.', '',
        '## Conclusion', '',
        'The static concurrent proof remains valid and is preserved. The current ruyijs',
        'implementation intentionally reports this boundary as incomplete. No opcode',
        'trace would create the missing cross-process token or child queue selection.',
        'The next useful implementation is token transport and child acknowledgment,',
        'followed by a same fixture positive replay and wrong-token controls.', '',
        'Source and evidence identities are in `result.json`; this report does not alter',
        'production binaries or claim the original webpage business closure.', '']), 'utf-8')
    print(json.dumps({'published': True, 'enabled_cases': len(enabled), 'messages': messages,
                      'cross_process_messages': cross_process, 'full_goal_complete': False}))


if __name__ == '__main__':
    raise SystemExit(main())
