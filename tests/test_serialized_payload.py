"""Reject incomplete evidence instead of treating reconstructed JSON as observed bytes."""
import json
import unittest

from tools.trace_audit.serialized_payload import reconstruct, differences
from tools.trace_audit.payload_alignment import byte_array, replay_rows


def sample():
    def enter(call,start,value,parent=0):
        return {'type':'jscall','callee':'encode','phase':'enter','column':7,
            'call_id':call,'parent_call_id':parent,'args':[value,{'type':'object','class':'Array'},
                                                       {'type':'number','value':start}]}
    def leave(call,end):
        return {'type':'jscall','callee':'encode','phase':'leave','call_id':call,
                'completion':'return','result':{'type':'number','value':end}}
    return [enter(1,1,{'type':'object','class':'Object'}),
        enter(2,2,{'type':'string','value':'x','length':1},1),leave(2,5),
        enter(3,6,{'type':'number','value':42},1),leave(3,8),leave(1,9)]


class SerializedPayloadTests(unittest.TestCase):
    def test_exact_spans_reconstruct_json(self):
        payload,proof=reconstruct(sample(),'encode',7)
        self.assertEqual(payload,{'x':42})
        self.assertEqual(proof['end']-proof['start'],8)
        self.assertEqual(proof['serializer_calls'],3)

    def test_missing_or_wrong_leave(self):
        for rows in (sample()[:-1],sample()[:3]+sample()[4:]):
            with self.assertRaises(ValueError):reconstruct(rows,'encode',7)

    def test_bad_primitive_offset_length_or_truncation(self):
        for field,value in [('value','longer'),('length',2)]:
            rows=sample();rows[1]['args'][0][field]=value
            with self.assertRaises(ValueError):reconstruct(rows,'encode',7)
        rows=sample();rows[3]['args'][2]['value']=7
        with self.assertRaises(ValueError):reconstruct(rows,'encode',7)
        rows=sample();rows[3]['args'][0]={'type':'string','length':100,'head':'a'}
        with self.assertRaises(ValueError):reconstruct(rows,'encode',7)

    def test_missing_key_or_wrong_container(self):
        rows=sample();del rows[1:3]
        with self.assertRaises(ValueError):reconstruct(rows,'encode',7)
        rows=sample();rows[0]['args'][0]['class']='Proxy'
        with self.assertRaises(ValueError):reconstruct(rows,'encode',7)

    def test_recorded_array_requires_full_byte_contents(self):
        self.assertEqual(byte_array((9,0,b'[32,123,125,32]')),b' {} ')
        for record in [(9,1,b'[1]'),(9,0,b'[true]'),(9,0,b'[-1]'),(9,0,b'[256]'),(8,0,b'Object')]:
            with self.assertRaises(ValueError):byte_array(record)

    def test_structural_difference_preserves_false_missing_and_null(self):
        result=differences({'a':False,'b':None},{'a':0,'c':None})
        self.assertEqual([r['path'] for r in result],['/a','/b','/c'])
        self.assertFalse(result[1]['replay_present'])
        self.assertFalse(result[2]['reference_present'])

    def test_limit_before_completeness_is_rejected(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'trace.jsonl'
            path.write_text('\n'.join(json.dumps(r) for r in sample()+[{'type':'limit_reached'}]),'utf-8')
            with self.assertRaises(ValueError):replay_rows(path,'encode',7,'compress',8)

    def test_complete_prefix_is_valid_before_later_limit(self):
        import tempfile
        from pathlib import Path
        next_stage={'type':'jscall','callee':'compress','phase':'enter','column':8,'call_id':4}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'trace.jsonl'
            path.write_text('\n'.join(json.dumps(r) for r in sample()+[next_stage,{'type':'limit_reached'}]),'utf-8')
            rows,end=replay_rows(path,'encode',7,'compress',8)
            self.assertEqual(len(rows),6)
            self.assertEqual(end['call_id'],4)


if __name__=='__main__':unittest.main()
