"""Recorded marker ancestry must preserve nested script and repeat identities."""
import copy
import json
import unittest

from tools.trace_audit.frame_timer_plan import marker_commands


def rows():
    base = {'process_instance_id': '3-aaa', 'session': 0, 'file': 'trace.jsonl'}
    values = [
        {'type': 'async_resume', 'phase': 'start', 'execution_context_id': 4, 'async_context_id': 8},
        {'type': 'timer_lifecycle', 'phase': 'fire', 'execution_context_id': 4, 'async_context_id': 8, 'global_id': 100, 'public_handle': 1},
        {'type': 'script_root', 'phase': 'start', 'execution_context_id': 5, 'parent_execution_context_id': 4},
        {'type': 'call', 'member': 'setAttribute', 'execution_context_id': 5, 'args': ['data-timer-proof', 'first']},
        {'type': 'async_resume', 'phase': 'start', 'execution_context_id': 6, 'async_context_id': 8},
        {'type': 'timer_lifecycle', 'phase': 'fire', 'execution_context_id': 6, 'async_context_id': 8, 'global_id': 100, 'public_handle': 1},
        {'type': 'call', 'member': 'setAttribute', 'execution_context_id': 6, 'args': ['data-timer-proof', 'second']}]
    return [{**base, **row, 'file_line': index + 1} for index, row in enumerate(values)]


class FrameTimerPlanTests(unittest.TestCase):
    def test_nested_script_has_explicit_parent_chain_and_stable_json(self):
        plan = marker_commands(rows(), {100: 'frame0'})
        self.assertEqual([c['firings'] for c in plan], [0, 1])
        self.assertEqual(plan[0]['observations'][0]['ancestry'], [['3-aaa', 0, 5], ['3-aaa', 0, 4]])
        self.assertEqual(json.loads(json.dumps(plan)), plan)

    def test_missing_parent_not_guessed_by_adjacent_fire(self):
        values = rows(); values[2]['parent_execution_context_id'] = 1000
        with self.assertRaisesRegex(ValueError, 'undeclared'): marker_commands(values, {100: 'frame0'})

    def test_wrong_session_not_globally_joined(self):
        values = rows(); values[3]['session'] = 1
        with self.assertRaisesRegex(ValueError, 'undeclared'): marker_commands(values, {100: 'frame0'})

    def test_context_cycle_stops(self):
        values = rows(); values[2]['parent_execution_context_id'] = 5
        with self.assertRaisesRegex(ValueError, 'cycle'): marker_commands(values, {100: 'frame0'})

    def test_two_capture_files_not_sorted_by_timestamp(self):
        values = rows(); values[5]['file'] = 'other.jsonl'
        with self.assertRaisesRegex(ValueError, 'one recorded'): marker_commands(values, {100: 'frame0'})

    def test_unobserved_fire_is_not_invented_output(self):
        values = rows(); del values[-1]
        with self.assertRaisesRegex(ValueError, 'no output'): marker_commands(values, {100: 'frame0'})

    def test_duplicate_fire_is_ambiguous(self):
        values = rows(); values.append(copy.deepcopy(values[1]))
        with self.assertRaisesRegex(ValueError, 'duplicate'): marker_commands(values, {100: 'frame0'})


if __name__ == '__main__': unittest.main()
