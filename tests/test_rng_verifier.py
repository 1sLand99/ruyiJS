"""Reject incomplete and misattributed RNG captures before consuming states."""
import copy
import unittest

from tools.trace_audit.verify_rng import advance, validate


def fixture():
    modes = {}
    for mode in ('off', 'on', 'seeded-off', 'seeded-on', 'gate'):
        outputs, rows = [], []
        for realm in range(1, 2 if mode == 'gate' else 5):
            start = (0x123456789ABCDEF0 + realm, 0xFEDCBA9876543210)
            checkpoint, first = advance(start, 8)
            _, values = advance(checkpoint, 20000)
            outputs.append({'first': first, 'values': values})
            if mode.endswith('off'):
                continue
            for phase, state, seq in [('initial', start, 1), ('script-entry', checkpoint, 2)]:
                if mode == 'gate' and phase == 'initial':
                    continue
                rows.append({'type': 'realm_rng', 'schema': 'realm_rng.v1',
                    'algorithm': 'xorshift128plus-low53', 'process_instance_id': mode,
                    'realm_id': realm, 'phase': phase, 'available': True, 'seq': seq,
                    'state0': f'{state[0]:016x}', 'state1': f'{state[1]:016x}',
                    'script_url': 'http://fixture/rng-second.js', 'script_url_truncated': False})
        modes[mode] = {'outputs': outputs, 'records': rows}
    return {'modes': modes}


class RngVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = fixture()

    def setUp(self):
        self.report = copy.deepcopy(self.good)
        self.rows = self.report['modes']['on']['records']

    def test_complete_evidence(self):
        result = validate(self.report)
        self.assertEqual(sum(row['values_checked'] for row in result['checks']), 180064)

    def test_changed_state(self):
        self.rows[1]['state0'] = '0000000000000001'
        with self.assertRaises(AssertionError):
            validate(self.report)

    def test_missing_output_and_corresponding_records(self):
        self.report['modes']['on']['outputs'].pop()
        del self.rows[-2:]
        with self.assertRaises(AssertionError):
            validate(self.report)

    def test_merged_realm_identity(self):
        self.rows[2]['realm_id'] = self.rows[3]['realm_id'] = 1
        with self.assertRaises(AssertionError):
            validate(self.report)

    def test_identity_needs_process_scope(self):
        self.rows[1]['process_instance_id'] = 'different-process'
        with self.assertRaises(AssertionError):
            validate(self.report)

    def test_missing_checkpoint(self):
        self.rows[1]['available'] = False
        with self.assertRaises(AssertionError):
            validate(self.report)

    def test_gate_is_not_initial_state(self):
        row = copy.deepcopy(self.report['modes']['gate']['records'][0])
        row['phase'] = 'initial'
        self.report['modes']['gate']['records'].append(row)
        with self.assertRaises(AssertionError):
            validate(self.report)

    def test_gap_record(self):
        self.rows.append({'type': 'rng_trace_gap', 'reason': 'record-limit'})
        with self.assertRaises(AssertionError):
            validate(self.report)

    def test_seeded_mode_page_difference(self):
        self.report['modes']['seeded-off']['outputs'][0]['first'][0] = -1
        with self.assertRaises(AssertionError):
            validate(self.report)


if __name__ == '__main__':
    unittest.main()
