"""Offline inference inputs reject unsupported values and ordering evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.trace_audit.random_state import next_value, observations
from tools.trace_audit.script_order import extract


class RandomEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_boundary_values_and_invalid_random_output(self):
        path = self.root / 'trace.jsonl'
        row = {'interface':'Math','member':'random','type':'call','return':0}
        path.write_text(json.dumps(row), 'utf-8')
        self.assertEqual(observations(path)[0]['value'], 0)
        for value in (1, -0.1, 'number', 0.1):
            row['return'] = value
            path.write_text(json.dumps(row), 'utf-8')
            with self.assertRaises(ValueError):
                observations(path)

    def test_xorshift_known_integer_transition(self):
        a, b, value = next_value(1, 2)
        self.assertEqual((a, b), (2, 8388675))
        self.assertEqual(value, 8388677 / (1 << 53))

    def test_order_requires_phase_evidence(self):
        packet, trace = self.root/'packet.json', self.root/'trace.jsonl'
        packet.write_text(json.dumps({'url':'https://example.test/', 'responseBody':
            {'text':'<script async src="a.js"></script>', 'truncated':False}}), 'utf-8')
        rows = [{'type':'script_root','phase':'start','script_kind':'classic','url':'https://example.test/a.js','seq':1},
                {'type':'get','interface':'Document','member':'get readyState','value':'loading'},
                {'type':'script_root','phase':'end','seq':3}]
        trace.write_text('\n'.join(json.dumps(r) for r in rows), 'utf-8')
        with self.assertRaises(ValueError): extract(packet, trace)
        rows[1]['value'] = 'interactive'
        trace.write_text('\n'.join(json.dumps(r) for r in rows), 'utf-8')
        self.assertEqual(extract(packet, trace)['urls'], ['https://example.test/a.js'])


if __name__ == '__main__':
    unittest.main()
