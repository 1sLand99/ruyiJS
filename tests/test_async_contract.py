"""Recorded checkpoint grouping must reject lost, split, repeated or corrupt evidence."""
import copy
import json
import unittest

from tools.trace_audit.async_contract import ContractCursor, marker_groups
from tools.trace_audit.async_mapping_probe import inspect


def fixture_rows():
    base = {'process_instance_id': '10-aaa', 'session': 0, 'file': 'trace.jsonl'}
    values = [
        {'type': 'script_root', 'phase': 'start', 'execution_context_id': 1},
        {'type': 'call', 'execution_context_id': 1, 'interface': 'Element', 'member': 'setAttribute',
         'args': ['data-causal-proof', 'start']},
        {'type': 'async_schedule', 'async_context_id': 7, 'parent_execution_context_id': 1, 'async_cause': 'queue_microtask'},
        {'type': 'async_resume', 'phase': 'start', 'execution_context_id': 2, 'async_context_id': 7,
         'async_cause': 'queue_microtask'},
        {'type': 'call', 'execution_context_id': 2, 'interface': 'Element', 'member': 'setAttribute',
         'args': ['data-causal-proof', 'microtask']},
        {'type': 'async_schedule', 'async_context_id': 8, 'parent_execution_context_id': 2, 'async_cause': 'set_timeout'},
        {'type': 'async_resume', 'phase': 'start', 'execution_context_id': 3, 'async_context_id': 8,
         'async_cause': 'set_timeout'},
        {'type': 'call', 'execution_context_id': 3, 'interface': 'Element', 'member': 'setAttribute',
         'args': ['data-causal-proof', 'timer']}]
    return [{**base, **row, 'file_line': index + 1} for index, row in enumerate(values)]


def contract():
    groups = marker_groups(fixture_rows())
    return {'groups': groups, 'labels': [label for group in groups for label in group['labels']]}


class AsyncContractTests(unittest.TestCase):
    def test_explicit_microtask_parent_joins_same_observed_group(self):
        groups = marker_groups(fixture_rows())
        self.assertEqual([row['labels'] for row in groups], [['start', 'microtask'], ['timer']])
        self.assertEqual(groups[0]['observations'][1]['context_ancestry'], [['10-aaa', 0, 2], ['10-aaa', 0, 1]])

    def test_missing_schedule_is_not_inferred_from_adjacency(self):
        rows = fixture_rows(); del rows[2]
        with self.assertRaisesRegex(ValueError, 'missing'): marker_groups(rows)

    def test_schedule_cause_mismatch(self):
        rows = fixture_rows(); rows[2]['async_cause'] = 'promise_reaction'
        with self.assertRaisesRegex(ValueError, 'mismatched'): marker_groups(rows)

    def test_schedule_cycle(self):
        rows = fixture_rows(); rows[2]['parent_execution_context_id'] = 2
        with self.assertRaisesRegex(ValueError, 'cycle'): marker_groups(rows)

    def test_duplicate_context(self):
        rows = fixture_rows(); rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError, 'ambiguous'): marker_groups(rows)

    def test_wrong_session_not_merged(self):
        rows = fixture_rows(); rows[3]['schedule_session'] = 1
        with self.assertRaisesRegex(ValueError, 'missing'): marker_groups(rows)

    def test_two_marker_files_not_globally_ordered(self):
        rows = fixture_rows(); rows[-1]['file'] = 'other.jsonl'
        with self.assertRaisesRegex(ValueError, 'one observed'): marker_groups(rows)

    def test_checkpoint_reentry_is_not_merged(self):
        rows = fixture_rows(); extra = copy.deepcopy(rows[1]); extra['file_line'] = 9; rows.append(extra)
        with self.assertRaisesRegex(ValueError, 'reappeared'): marker_groups(rows)

    def test_empty_polls_preserve_cursor(self):
        cursor = ContractCursor(contract())
        self.assertIsNone(cursor.observe([]))
        self.assertEqual(cursor.observe(['start', 'microtask']), 0)
        self.assertIsNone(cursor.observe(['start', 'microtask']))
        self.assertEqual(cursor.observe(['start', 'microtask', 'timer']), 1)
        self.assertTrue(cursor.finish())

    def test_split_or_merged_checkpoints_fail(self):
        for values in (['start'], ['start', 'microtask', 'timer'], ['microtask', 'start']):
            with self.assertRaisesRegex(ValueError, 'checkpoint'): ContractCursor(contract()).observe(values)

    def test_changed_output_prefix_fails(self):
        cursor = ContractCursor(contract()); cursor.observe(['start', 'microtask'])
        with self.assertRaisesRegex(ValueError, 'previously'): cursor.observe(['start'])

    def test_truncated_execution_fails_terminal_check(self):
        cursor = ContractCursor(contract()); cursor.observe(['start', 'microtask'])
        with self.assertRaisesRegex(ValueError, 'fully consumed'): cursor.finish()

    def test_extra_output_fails(self):
        cursor = ContractCursor(contract()); cursor.observe(['start', 'microtask'])
        cursor.observe(['start', 'microtask', 'timer'])
        with self.assertRaisesRegex(ValueError, 'extra output'): cursor.observe(['start', 'microtask', 'timer', 'extra'])

    def test_mapping_proof_survives_json(self):
        rows = fixture_rows()
        rows[2]['async_cause'] = rows[3]['async_cause'] = 'promise_reaction'
        rows[4]['async_context_id'] = 7
        rows[-1]['async_context_id'] = 8
        proof = inspect(rows)
        self.assertEqual(json.loads(json.dumps(proof)), proof)


if __name__ == '__main__':
    unittest.main()
