"""Capture input extraction fails closed on ambiguous document or byte evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.trace_audit.crypto_inputs import extract


class CryptoInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'http_packet').mkdir()
        (self.root/'domtrace').mkdir()
        self.url='https://example.test/frame'
        self.packet={'url':self.url,'status':200,'meta':{'requestKind':'subdocument','innerWindowId':3},
                     'responseBody':{'sha256':'body'}}
        self.row={'type':'call','interface':'Crypto','member':'getRandomValues',
                  'postArgs':[{'hex':'01fe','byteLength':2,'truncated':False}],
                  'stack':[{'file':self.url}],'thisObj':{'id':'crypto-1'}}

    def write(self, row=None, root_url=None):
        (self.root/'http_packet/p.json').write_text(json.dumps(self.packet),'utf-8')
        (self.root/'http_packet/p.json').rename(self.root/'http_packet/p.http_packet.json')
        rows=[{'type':'trace_init','process_instance_id':'7-nonce'},
              {'type':'script_root','phase':'start','execution_context_id':1,'url':root_url or self.url},
              row or self.row]
        (self.root/'domtrace/trace_process_7.jsonl').write_text('\n'.join(json.dumps(x) for x in rows),'utf-8')

    def test_complete_bytes_have_hash_and_document_evidence(self):
        self.write()
        report=extract(self.root)
        self.assertEqual(report['documents'],[{'url':self.url,'values':['01fe']}])
        self.assertEqual(report['evidence'][0]['evidence'][0]['bytes_sha256'],hashlib.sha256(b'\x01\xfe').hexdigest())
        self.assertEqual(report['rejected'],[])

    def test_duplicate_packet_does_not_guess_document(self):
        self.write()
        (self.root/'http_packet/other.http_packet.json').write_text(json.dumps(self.packet),'utf-8')
        report=extract(self.root)
        self.assertEqual(report['documents'],[])
        self.assertEqual(len(report['rejected']),1)

    def test_truncation_is_not_replayed(self):
        self.row['postArgs'][0]['truncated']=True
        self.write()
        self.assertEqual(extract(self.root)['documents'],[])

    def test_stack_and_root_must_agree(self):
        self.write(root_url='https://other.test/')
        self.assertEqual(extract(self.root)['documents'],[])

    def test_uuid_uses_same_document_attribution(self):
        self.row.update(member='randomUUID',postArgs=None,**{'return':'00112233-4455-4677-8899-aabbccddeeff'})
        self.write()
        report=extract(self.root)
        self.assertEqual(report['documents'][0]['values'],[{'method':'randomUUID','value':self.row['return']}])
        self.assertEqual(report['evidence'][0]['evidence'][0]['method'],'randomUUID')

    def test_different_crypto_receivers_reject_the_entire_document_group(self):
        self.write()
        other={**self.row,'member':'randomUUID','return':'00112233-4455-4677-8899-aabbccddeeff',
               'postArgs':None,'thisObj':{'id':'other-crypto'}}
        with (self.root/'domtrace/trace_process_7.jsonl').open('a',encoding='utf-8') as stream:
            stream.write('\n'+json.dumps(other))
        report=extract(self.root)
        self.assertEqual(report['documents'],[])
        self.assertEqual(len(report['rejected']),2)


if __name__=='__main__':unittest.main()
