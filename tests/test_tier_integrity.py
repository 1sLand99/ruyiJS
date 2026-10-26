"""Mutated real-format fixture records must not pass parent/value proof."""
from pathlib import Path
import json
import struct
import tempfile
import unittest

from tools.trace_audit.binary import CALL, HEADER, VALUE
from tools.trace_audit.local_call_index import CallIndex
from tools.trace_audit.tier_oracle import leaf, int32
from tools.trace_audit.tier_value_proof import prove


class TierIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.binary=self.folder/'calls.bin';self.dictionary=self.folder/'calls.dict.jsonl'
        self.detail=self.folder/'calls.detail.bin'
        self.calls=[(2,1,2,0,2,1,2,2,0),(4,3,2,0,3,1,2,2,0),(3,1,3,0,2,1,2,2,0),
                    (6,5,2,0,3,1,2,2,0),(5,1,4,0,2,1,2,2,0),(7,1,5,0,2,1,2,2,0),
                    (1,0,1,0,1,2,2,1,0)]
        self.values=[]
        def add(call,slot,kind,payload):self.values.append((call,slot,kind,0,payload))
        def start(call,*args):
            add(call,65534,1,b'')
            for n,value in enumerate(args):add(call,n,4,struct.pack('<i',value))
        def end(call,value):add(call,65535,4,struct.pack('<i',value))
        start(1,3,1)
        start(2,0);end(2,leaf(0))
        start(3,1);start(4,2);end(4,leaf(2));end(3,leaf(2))
        start(5,2);start(6,4);end(6,leaf(4));end(5,leaf(4))
        start(7);add(7,0,10,bytes(1024));end(7,1024)
        add(1,65535,8,b'Object')
        self.expected=[{'arguments':[3,1],'checksum':[int32(leaf(0)^leaf(2)^leaf(4)),1024]}]

    def write(self):
        self.binary.write_bytes(HEADER.pack(b'JSCT',1,CALL.size,7,0)+b''.join(CALL.pack(*r) for r in self.calls))
        names={1:'run',2:'measuredLeaf',3:'shiftedOne',4:'shiftedTwo',5:'measuredBytes'}
        rows=[{'func_id':key,'name':name} for key,name in names.items()]
        rows.append({'type':'jscall_stats','recorded':len(self.calls)})
        self.dictionary.write_text('\n'.join(json.dumps(r) for r in rows),'utf-8')
        self.detail.write_bytes(HEADER.pack(b'JSCV',1,VALUE.size,7,0)+b''.join(
            VALUE.pack(call,slot,kind,flags,len(data))+data for call,slot,kind,flags,data in self.values))

    def verify(self):
        self.write()
        with CallIndex(self.binary,self.dictionary) as index:
            return prove(index,self.detail,self.expected,True)

    def test_all_inputs_outputs_and_checksum(self):
        result=self.verify()
        self.assertEqual(result['leaf_returns'],3)
        self.assertEqual(result['numeric_returns'],6)
        self.assertEqual(result['run_checksums'],1)
        self.assertEqual(result['unknown_object_contents'],1)
        self.assertEqual(result['recovered_runs'][0]['arguments'],[3,1])
        self.assertEqual(result['recovered_runs'][0]['checksum'],self.expected[0]['checksum'])

    def test_known_integer_oracle(self):
        self.assertEqual([leaf(n) for n in (0,2,4)],[-2056600071,461785800,-1350684130])

    def test_wrong_numeric_return_rejected(self):
        self.values[5]=(2,65535,4,0,struct.pack('<i',123))
        with self.assertRaises(ValueError):self.verify()

    def test_missing_and_duplicate_slot_rejected(self):
        del self.values[4]
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_argument_rejected(self):
        self.values.insert(5,self.values[4])
        with self.assertRaises(ValueError):self.verify()

    def test_parent_missing_or_wrong_thread_rejected(self):
        row=list(self.calls[0]);row[1]=(1<<48)+1;self.calls[0]=tuple(row)
        with self.assertRaises(ValueError):self.verify()

    def test_parent_leave_order_rejected(self):
        self.calls=self.calls[-1:]+self.calls[:-1]
        with self.assertRaisesRegex(ValueError,'leave after'):self.verify()

    def test_depth_and_gap_rejected_for_complete_fixture(self):
        row=list(self.calls[0]);row[6]=66;self.calls[0]=tuple(row)
        with self.assertRaisesRegex(ValueError,'caller gaps'):self.verify()

    def test_duplicate_calls_rejected(self):
        self.calls.append(self.calls[0])
        with self.assertRaisesRegex(ValueError,'duplicate'):self.verify()

    def test_truncation_flag_cannot_be_treated_as_full_value(self):
        call,slot,kind,_,data=self.values[4];self.values[4]=(call,slot,kind,1,data)
        with self.assertRaises(ValueError):self.verify()

    def test_same_results_wrong_input_sequence_rejected(self):
        # Keep an arithmetic pair locally consistent while violating the source loop sequence.
        self.values[4]=(2,0,4,0,struct.pack('<i',9))
        self.values[5]=(2,65535,4,0,struct.pack('<i',leaf(9)))
        with self.assertRaisesRegex(ValueError,'input/order'):self.verify()

    def test_wrong_page_checksum_rejected(self):
        self.expected[0]['checksum'][0]^=1
        with self.assertRaisesRegex(ValueError,'checksum'):self.verify()

    def test_boolean_cannot_replace_integer_argument(self):
        self.values[2]=(1,1,3,0,b'\x01')
        with self.assertRaisesRegex(ValueError,'integer type'):self.verify()

    def test_trailing_bytes_rejected(self):
        self.write()
        with self.detail.open('ab') as stream:stream.write(b'x')
        with CallIndex(self.binary,self.dictionary) as index:
            with self.assertRaisesRegex(ValueError,'partial'):prove(index,self.detail,self.expected,True)


if __name__=='__main__':unittest.main()
