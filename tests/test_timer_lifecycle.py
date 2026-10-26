"""Timer keys must remain unambiguous across handles, sessions and cancellations."""
import copy
import json
import unittest

from tools.trace_audit.timer_lifecycle import prove_timers


def rows(repeating=False):
    base = {'process_instance_id': '7-aaa', 'session': 0, 'file': 'trace.jsonl'}
    timer = {'type': 'timer_lifecycle', 'async_context_id': 9, 'public_handle': 1,
             'global_id': 100, 'global_native_id': 'abc', 'repeating': repeating,
             'origin_call_id': 2, 'delay_ms': 0}
    values = [
        {'type': 'async_schedule', 'async_context_id': 9, 'parent_execution_context_id': 3,
         'async_parent_call_id': 2, 'async_cause': 'set_interval' if repeating else 'set_timeout'},
        {**timer, 'phase': 'register', 'execution_context_id': 3, 'event_index': 1},
        {'type': 'call', 'interface': 'Window', 'member': 'setInterval' if repeating else 'setTimeout',
         'execution_context_id': 3, 'return': 1, 'thisObj': {'nativeId': 'abc'}, 'args': ['callback', 0]},
        {'type': 'async_resume', 'phase': 'start', 'async_context_id': 9, 'execution_context_id': 4},
        {**timer, 'phase': 'fire', 'execution_context_id': 4, 'event_index': 2},
        {**timer, 'phase': 'finish', 'execution_context_id': 4, 'event_index': 3},
        {'type': 'domtrace_writer_stats', 'io_errors': 0}]
    return [{**base, **row, 'file_line': index + 1} for index, row in enumerate(values)]


class TimerLifecycleTests(unittest.TestCase):
    def test_complete_identity_and_json_roundtrip(self):
        proof = prove_timers(rows())
        self.assertEqual(proof['registrations'], 1)
        self.assertEqual(proof['timers'][0]['terminal'], 'finished')
        self.assertEqual(json.loads(json.dumps(proof)), proof)

    def test_same_handle_in_two_globals_is_distinct(self):
        first = rows(); second = copy.deepcopy(rows())
        for row in second:
            if 'async_context_id' in row: row['async_context_id'] = 10
            if row.get('execution_context_id') == 4: row['execution_context_id'] = 5
            if 'global_id' in row: row['global_id'] = 101; row['global_native_id'] = 'def'
            if 'thisObj' in row: row['thisObj']['nativeId'] = 'def'
            if 'event_index' in row: row['event_index'] += 3
        self.assertEqual(prove_timers(first + second)['registrations'], 2)

    def test_cancel_before_fire(self):
        data = rows(); data = data[:3] + [{**data[4], 'phase': 'cancel', 'execution_context_id': 3}] + data[-1:]
        proof = prove_timers(data)
        self.assertEqual(proof['timers'][0]['fires'], [])
        self.assertEqual(proof['timers'][0]['terminal'], 'cancel')

    def test_interval_self_cancel_then_finish(self):
        data = rows(True); data.insert(5, {**data[4], 'phase': 'cancel', 'event_index': 3})
        data[6]['event_index'] = 4; data[6]['repeating'] = False
        self.assertEqual(prove_timers(data)['timers'][0]['terminal'], 'cancel')

    def test_lifecycle_owner_mutation_is_error(self):
        for field, value in [('global_id', 99), ('global_native_id', 'bad'), ('public_handle', 2)]:
            data = rows(); data[4][field] = value
            with self.assertRaisesRegex(ValueError, 'owner/handle'): prove_timers(data)

    def test_ambiguous_dom_call_is_error(self):
        data = rows(); data.insert(3, copy.deepcopy(data[2]))
        with self.assertRaisesRegex(ValueError, 'uniquely'): prove_timers(data)

    def test_wrong_schedule_session_is_error(self):
        data = rows(); data[0]['session'] = 1
        with self.assertRaisesRegex(ValueError, 'schedule'): prove_timers(data)

    def test_parent_call_change_is_error(self):
        data = rows(); data[0]['async_parent_call_id'] = 100
        with self.assertRaisesRegex(ValueError, 'parent'): prove_timers(data)

    def test_finish_without_fire_is_error(self):
        data = rows(); del data[4]
        with self.assertRaisesRegex(ValueError, 'close'): prove_timers(data)

    def test_fire_after_terminal_is_error(self):
        data = rows(); data.insert(4, {**data[4], 'phase': 'cancel'})
        with self.assertRaisesRegex(ValueError, 'cancelled'): prove_timers(data)

    def test_index_loss_and_open_lifecycle_are_errors(self):
        data = rows(); data[4]['event_index'] = 8
        with self.assertRaisesRegex(ValueError, 'index'): prove_timers(data)
        data = rows(); del data[5]
        with self.assertRaisesRegex(ValueError, 'unfinished'): prove_timers(data)

    def test_budget_and_writer_loss_reject_completeness(self):
        data = rows(); data.append({'type': 'timer_trace_gap'})
        with self.assertRaisesRegex(ValueError, 'budget'): prove_timers(data)
        data = rows(); data[-1]['io_errors'] = 1
        with self.assertRaisesRegex(ValueError, 'writer'): prove_timers(data)


if __name__ == '__main__': unittest.main()
