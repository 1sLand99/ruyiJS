"""Adversarial capture-format and process-identity checks for offline evidence."""
from array import array
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.trace_audit import binary, causal, jsonlines, network


class TraceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_leave_order_and_jit_gap_are_not_missing_parent(self):
        # Child leaves before its parent; the edge is still resolvable.
        data = binary.HEADER.pack(b'JSCT', 1, 32, 7, 0)
        data += binary.CALL.pack(2, 1, 9, 2, 1, 0, 66, 3, 0)
        data += binary.CALL.pack(1, 0, 9, 3, 0, 0, 2, 1, 0)
        report, ids = binary.calls(self.write('calls.bin', data), {9: {}})
        self.assertEqual(report['missing_parent_records'], 0)
        self.assertEqual(report['caller_jit_gap'], 1)
        self.assertEqual(list(ids), [1, 2])

    def test_missing_parent_and_partial_record_are_reported(self):
        data = binary.HEADER.pack(b'JSCT', 1, 32, 7, 0)
        data += binary.CALL.pack(3, 2, 9, 2, 1, 0, 2, 1, 0) + b'x'
        report, ids = binary.calls(self.write('calls.bin', data), {})
        self.assertEqual(report['missing_parent_records'], 1)
        self.assertEqual(report['unknown_function'], 1)
        self.assertEqual(report['errors'], [{'trailing_bytes': 1}])

    def test_future_version_rejected(self):
        data = binary.HEADER.pack(b'JSCV', 2, 16, 7, 0)
        with self.assertRaises(ValueError):
            binary.details(self.write('values.bin', data), array('Q'), 7)

    def test_partial_value_is_not_silently_accepted(self):
        data = binary.HEADER.pack(b'JSCV', 1, 16, 7, 0)
        data += binary.VALUE.pack(1, 0, 6, 0, 20) + b'abc'
        report = binary.details(self.write('values.bin', data), array('Q', [1]), 7)
        self.assertEqual(len(report['errors']), 1)
        self.assertEqual(report.get('values', 0), 0)

    def test_nondictionary_json_and_invalid_utf8_are_errors(self):
        path = self.write('domtrace/events.jsonl', b'{}\n[]\n\xff\n{"type":\n')
        report = jsonlines.scan(path, self.root, {})
        self.assertEqual(report['malformed_rows'], 3)

    def test_same_call_id_in_other_process_does_not_resolve(self):
        row = {'url': 'https://example.test/', 'method': 'GET', 'status': 200,
               'meta': {'originPid': 8, 'originCallId': 1},
               'responseBody': {'kind': 'text', 'text': 'hello',
                                'sha256': hashlib.sha256(b'hello').hexdigest()}}
        self.write('http_packet/p.http_packet.json', json.dumps(row).encode())
        report = network.scan(self.root, {7: array('Q', [1])})
        self.assertEqual(report['counts']['origin_nonzero'], 1)
        self.assertEqual(report['counts']['origin_resolved'], 0)
        self.assertEqual(report['counts']['body_hash_mismatches'], 0)

    def test_content_kind_is_not_storage_encoding(self):
        self.assertEqual(network.body_bytes({'kind': 'html', 'text': '<html>'}), b'<html>')
        self.assertEqual(network.body_bytes({'kind': 'binary', 'base64': 'AAEC'}), b'\x00\x01\x02')
        with self.assertRaises(ValueError):
            network.body_bytes({'kind': 'javascript', 'text': None, 'base64': None})

    def test_interval_resume_and_cross_process_ids(self):
        events = [{'type': 'async_schedule', 'pid': 7, 'async_context_id': 1, 'line': 1},
                  {'type': 'async_resume', 'phase': 'start', 'pid': 7, 'async_context_id': 1, 'line': 2},
                  {'type': 'async_resume', 'phase': 'start', 'pid': 7, 'async_context_id': 1, 'line': 3},
                  {'type': 'async_resume', 'phase': 'start', 'pid': 8, 'async_context_id': 1, 'line': 4}]
        report = causal.graph([{'path': 'events.jsonl', 'causal_events': events}])
        self.assertEqual(report['counts']['resume_enters'], 3)
        self.assertEqual(report['counts']['resume_without_schedule'], 1)
        self.assertEqual(len(report['edges']), 2)

    def test_ambiguous_message_send_is_not_guessed(self):
        events = [{'type': 'message_send', 'message_id': 'm', 'line': 1},
                  {'type': 'message_send', 'message_id': 'm', 'line': 2},
                  {'type': 'message_receive', 'message_id': 'm', 'line': 3}]
        report = causal.graph([{'path': 'events.jsonl', 'causal_events': events}])
        self.assertEqual(report['counts']['receive_with_ambiguous_send'], 1)
        self.assertEqual(report['edges'], [])

    def test_async_identity_includes_process_instance_and_session(self):
        schedule = {'type': 'async_schedule', 'pid': 7, 'process_instance_id': 'first',
                    'session': 2, 'async_context_id': 1, 'line': 1}
        resume = {**schedule, 'type': 'async_resume', 'phase': 'start', 'line': 2}
        events = [schedule, resume, {**resume, 'process_instance_id': 'reused-pid'},
                  {**resume, 'schedule_session': 3}, {**resume, 'trace_run_id': 'other-run'}]
        report = causal.graph([{'path': 'events.jsonl', 'causal_events': events}])
        self.assertEqual(report['counts']['resume_without_schedule'], 3)
        self.assertEqual(len(report['edges']), 1)

    def test_duplicate_schedule_and_absent_message_ids_are_unresolved(self):
        schedule = {'type': 'async_schedule', 'pid': 7, 'async_context_id': 1, 'line': 1}
        events = [schedule, {**schedule, 'line': 2},
                  {**schedule, 'type': 'async_resume', 'phase': 'start', 'line': 3},
                  {'type': 'message_send', 'line': 4}, {'type': 'message_receive', 'line': 5}]
        report = causal.graph([{'path': 'events.jsonl', 'causal_events': events}])
        self.assertEqual(report['counts']['resume_with_ambiguous_schedule'], 1)
        self.assertEqual(report['counts']['receive_without_send'], 1)
        self.assertEqual(report['edges'], [])

    def test_trace_init_identity_propagates_to_causal_records(self):
        records = [{'type': 'trace_init', 'trace_run_id': 'r', 'process_instance_id': 'p'},
                   {'type': 'async_schedule', 'pid': 7, 'session': 3, 'async_context_id': 1},
                   {'type': 'async_resume', 'phase': 'start', 'pid': 7, 'session': 4,
                    'schedule_session': 3, 'async_context_id': 1}]
        path = self.write('domtrace/events.jsonl', b'\n'.join(json.dumps(x).encode() for x in records))
        report = jsonlines.scan(path, self.root, {})
        self.assertEqual(report['causal_events'][0]['process_instance_id'], 'p')
        self.assertEqual(report['causal_events'][1]['schedule_session'], 3)
        self.assertEqual(len(causal.graph([report])['edges']), 1)

    def test_message_id_spans_process_local_run_ids(self):
        rows = [{'type': 'message_send', 'trace_run_id': '7-start', 'pid': 7,
                 'message_id': '7-nonce-1', 'line': 1},
                {'type': 'message_receive', 'trace_run_id': '8-start', 'pid': 8,
                 'message_id': '7-nonce-1', 'line': 2}]
        report = causal.graph([{'path': 'events.jsonl', 'causal_events': rows}])
        self.assertEqual(report['counts']['receive_without_send'], 0)
        self.assertEqual(len(report['edges']), 1)


if __name__ == '__main__':
    unittest.main()
