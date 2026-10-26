"""Observed ancestry retains unsigned IDs, gaps, corruption and process identity."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.trace_audit import binary, chain, chain_index


class ChainIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'jscall').mkdir()
        (self.root / 'domtrace').mkdir()
        self.db = self.root / 'calls.sqlite'

    def capture(self, records, tail=b''):
        prefix = self.root / 'jscall/trace_jscall_process_7'
        prefix.with_suffix('.bin').write_bytes(binary.HEADER.pack(b'JSCT', 1, 32, 7, 0) +
            b''.join(binary.CALL.pack(*row) for row in records) + tail)
        entries = [{'func_id': 9, 'name': 'leaf', 'url': 'https://example.test/app.js'},
                   {'type': 'jscall_stats', 'recorded': len(records)}]
        prefix.with_suffix('.dict.jsonl').write_text('\n'.join(json.dumps(x) for x in entries), 'utf-8')
        (self.root / 'domtrace/trace_process_7.jsonl').write_text(json.dumps(
            {'type': 'trace_init', 'pid': 7, 'process_instance_id': 'nonce-a', 'trace_run_id': 'run'}), 'utf-8')

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return chain_index.index(self.root, self.db)

    def test_unsigned_call_id_and_leave_order(self):
        parent, child = (1 << 63) + 1, (1 << 63) + 2
        self.capture([(child, parent, 9, 2, 1, 0, 66, 3, 0), (parent, 0, 9, 3, 0, 0, 2, 1, 0)])
        self.assertEqual(self.build(), 2)
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            report = chain.ancestors(db, 7, child, 'nonce-a')
            self.assertEqual(report['status'], 'observed_root')
            self.assertTrue(report['has_jit_gap'])
            self.assertEqual([r['call_id'] for r in report['calls']], [str(child), str(parent)])
            self.assertEqual(chain.ancestors(db, 7, child, 'nonce-b')['status'], 'process_instance_mismatch')
            self.assertEqual(chain.ancestors(db, 8, child)['status'], 'missing_process')

    def test_truncated_capture_remains_incomplete(self):
        self.capture([], b'x')
        with self.assertRaises(ValueError):
            self.build()
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(dict(db.execute('SELECT name,value FROM metadata'))['status'], 'incomplete')
        with self.assertRaises(ValueError):
            chain.build_report(self.root, self.db)

    def test_missing_parent_is_preserved_as_a_gap(self):
        self.capture([(3, 2, 9, 1, 0, 0, 2, 1, 0)])
        self.build()
        with contextlib.closing(sqlite3.connect(self.db)) as db:
            report = chain.ancestors(db, 7, 3)
            self.assertEqual(report['status'], 'missing_call')
            self.assertEqual(report['missing_call_id'], '2')
            self.assertEqual(len(report['calls']), 1)

    def test_changed_capture_invalidates_index_even_with_same_size(self):
        self.capture([(3, 0, 9, 1, 0, 0, 2, 1, 0)])
        self.build()
        path = self.root / 'jscall/trace_jscall_process_7.bin'
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'indexed input changed'):
            chain.build_report(self.root, self.db)


if __name__ == '__main__':
    unittest.main()
