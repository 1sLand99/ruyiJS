"""Protocol-level Worker token tests, independent of production pipe behavior."""
import struct
import unittest

from tools.trace_audit.worker_token_protocol import HEADER, TokenError, decode, encode


TOKEN = {'worker_id': 11, 'process_instance_id': 22, 'trace_session': 3,
         'source_global_id': 44, 'target_global_id': 55,
         'source_execution_context_id': 66, 'source_async_context_id': 77,
         'sequence': 88, 'direction': 0, 'kind': 1}


class WorkerTokenProtocolTests(unittest.TestCase):
    def test_roundtrip_keeps_identity_separate_from_payload(self):
        frame = encode(TOKEN, b'ping')
        decoded = decode(frame)
        self.assertEqual({k: decoded[k] for k in TOKEN}, TOKEN)
        self.assertEqual(decoded['payload'], b'ping')

    def test_empty_payload_is_valid_and_direction_is_explicit(self):
        token = {**TOKEN, 'direction': 1}
        decoded = decode(encode(token))
        self.assertEqual(decoded['direction'], 1)
        self.assertEqual(decoded['payload'], b'')

    def test_equal_payloads_have_distinct_sequences(self):
        a = decode(encode(TOKEN, b'ping')); b = decode(encode({**TOKEN, 'sequence': 89}, b'ping'))
        self.assertNotEqual(a['sequence'], b['sequence']); self.assertEqual(a['payload'], b['payload'])

    def test_header_corruption_is_rejected(self):
        frame = bytearray(encode(TOKEN, b'x'))
        for offset, value in ((0, ord('X')), (4, 2), (5, 3), (8, 9), (9, 1), (16, 0)):
            changed = bytearray(frame); changed[offset] = value
            with self.assertRaises(TokenError): decode(changed)

    def test_zero_or_non_integer_identity_is_rejected(self):
        for key in ('worker_id', 'process_instance_id', 'sequence'):
            with self.assertRaises(TokenError): encode({**TOKEN, key: 0})
        with self.assertRaises(TokenError): encode({**TOKEN, 'sequence': True})

    def test_payload_bound_is_rejected(self):
        with self.assertRaises(TokenError): encode(TOKEN, b'x' * (16 * 1024 * 1024))

    def test_truncated_and_trailing_header_are_rejected(self):
        frame = encode(TOKEN, b'x')
        with self.assertRaises(TokenError): decode(frame[:HEADER.size - 1])
        bad = bytearray(frame); bad[16:24] = struct.pack('<Q', 0)
        with self.assertRaises(TokenError): decode(bad)


if __name__ == '__main__': unittest.main()
