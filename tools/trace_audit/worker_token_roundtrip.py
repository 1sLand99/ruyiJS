"""Round-trip current concurrent trace identities through the future token schema."""
import argparse
import json
from pathlib import Path

from .message_graph import MessageGraph
from .async_evidence import load_rows
from .worker_token_protocol import decode, from_trace, TokenError


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    report = json.loads(args.capture.read_text('utf-8')); rows = []
    for case in report['cases']:
        if case['mode'] == 'off': continue
        folder = args.capture.parent / case['folder']; current, _ = load_rows(folder)
        rows.extend(current)
    graph = MessageGraph(rows)
    checked = []; errors = []
    for identity, message in graph.messages.items():
        send = message['send']; receive = message['receive']
        try:
            worker_id = hash((send['process_instance_id'], send['source_global_id'])) & ((1 << 64) - 1)
            if not worker_id: worker_id = 1
            outbound = decode(from_trace(send, worker_id, 0, b'opaque-payload'))
            inbound = decode(from_trace(receive, worker_id, 1, b'opaque-payload'))
            for key in ('process_instance_id', 'trace_session', 'source_global_id',
                        'target_global_id', 'sequence'):
                expected = send.get('source_pid') if key == 'process_instance_id' else (
                    send.get('source_trace_session', send.get('session', 0)) if key == 'trace_session' else
                    send.get('source_global_id') if key == 'source_global_id' else
                    send.get('target_global_id') if key == 'target_global_id' else send['message_sequence'])
                if outbound[key] != expected or inbound[key] != expected:
                    raise TokenError(f'{identity}: {key} changed during round-trip')
            if outbound['direction'] != 0 or inbound['direction'] != 1:
                raise TokenError(f'{identity}: direction changed')
            checked.append(identity)
        except (KeyError, TokenError) as error: errors.append(str(error))
    result = {'schema': 'local.worker-token-roundtrip.v1', 'messages_checked': len(checked),
              'errors': errors, 'passed': not errors and len(checked) == len(graph.messages),
              'scope': 'Protocol-only; production Worker pipe unchanged.', 'full_goal_complete': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', 'utf-8')
    print(json.dumps(result)); return int(not result['passed'])


if __name__ == '__main__': raise SystemExit(main())
