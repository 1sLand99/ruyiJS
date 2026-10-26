"""Request-body comparisons describe byte evidence without overstating equality."""
import hashlib
import unittest
from tools.trace_audit.request_diff import compare_body


class RequestDiffTests(unittest.TestCase):
    def test_same_prefix_does_not_imply_same_body(self):
        body=b'abcdef'
        result=compare_body('abcxyz',[{'file':'p','body':body,'post_sha256':hashlib.sha256(body).hexdigest()}])
        self.assertEqual(result['recorded_candidates'][0]['common_prefix_bytes'],3)
        self.assertFalse(result['recorded_body_hash_match'])
        self.assertFalse(result['recorded_candidates'][0]['actual_body_equal'])

    def test_equal_stored_utf8_bytes_and_hash(self):
        body='汉字'.encode()
        result=compare_body('汉字',[{'file':'p','body':body,'post_sha256':hashlib.sha256(body).hexdigest()}])
        self.assertEqual(result['body_bytes'],6)
        self.assertTrue(result['recorded_body_hash_match'])
        self.assertTrue(result['recorded_candidates'][0]['recorded_body_hash_valid'])

    def test_absent_body_is_not_an_empty_body(self):
        result=compare_body('',[{'file':'p','body':None,'post_sha256':None}])
        self.assertNotIn('actual_body_equal',result['recorded_candidates'][0])
        self.assertFalse(result['recorded_body_hash_match'])


if __name__=='__main__':unittest.main()
