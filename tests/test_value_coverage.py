import tempfile
import json
from pathlib import Path
import unittest
from tools.trace_audit.binary import HEADER,VALUE
from tools.trace_audit.value_coverage import inspect


class ValueCoverageTests(unittest.TestCase):
    def test_object_label_is_not_a_property_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'detail.bin'
            path.write_bytes(HEADER.pack(b'JSCV',1,16,7,0)+VALUE.pack(1,0,8,0,6)+b'Object')
            report=inspect(path,[1])
            self.assertFalse(report['records'][0]['object_fields_captured'])
            self.assertEqual(report['records'][0]['object_class_label'],'Object')

    def test_truncated_unselected_record_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'detail.bin'
            path.write_bytes(HEADER.pack(b'JSCV',1,16,7,0)+VALUE.pack(2,0,6,0,9)+b'x')
            with self.assertRaises(ValueError):inspect(path,[1])

    def test_object_snapshot_has_explicit_lossy_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'detail.bin'
            payload=json.dumps({'schema':'jscall.object.v1','root':{'t':'object','properties':[],'propertiesCut':True}}).encode()
            path.write_bytes(HEADER.pack(b'JSCV',1,16,7,0)+VALUE.pack(1,0,15,1,len(payload))+payload)
            row=inspect(path,[1])['records'][0]
            self.assertTrue(row['object_fields_captured'])
            self.assertTrue(row['object_snapshot_lossy'])

    def test_malformed_object_snapshot_is_not_reported_as_captured(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'detail.bin'
            path.write_bytes(HEADER.pack(b'JSCV',1,16,7,0)+VALUE.pack(1,0,15,0,1)+b'{')
            with self.assertRaises(ValueError):inspect(path,[1])


if __name__=='__main__':unittest.main()
