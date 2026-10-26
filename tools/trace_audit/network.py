"""Verify captured HTTP bodies and resolve process-scoped call references."""
import base64
from collections import Counter
import hashlib
import json
from urllib.parse import urlsplit

from .binary import contains


def body_bytes(body):
    if isinstance(body.get('base64'), str):
        return base64.b64decode(body['base64'], validate=True)
    if isinstance(body.get('text'), str):
        return body['text'].encode('utf-8')
    raise ValueError('body kind has no replayable content')


def scan(root, call_ids):
    packets, counts, errors, seen = [], Counter(), [], Counter()
    for path in sorted((root / 'http_packet').glob('*.http_packet.json')):
        obj = json.loads(path.read_text('utf-8'))
        meta, body = obj.get('meta', {}), obj.get('responseBody', {})
        pid = meta.get('originPid', meta.get('origin_pid', 0))
        call = meta.get('originCallId', meta.get('origin_call_id', 0))
        url = obj.get('url', '')
        parts = urlsplit(url)
        # Full URLs, headers, arguments and bodies stay in the original run.
        item = {'file': path.name, 'host': parts.netloc,
                'url_sha256': hashlib.sha256(url.encode()).hexdigest(),
                'method': obj.get('method'), 'status': obj.get('status'),
                'request_kind': meta.get('requestKind'), 'origin_pid': pid,
                'origin_call_id': str(call), 'call_resolved': bool(call and contains(call_ids.get(pid, ()), call)),
                'execution_context_id': meta.get('originExecutionContextId'),
                'async_context_id': meta.get('originAsyncContextId'),
                'inner_window_id': meta.get('innerWindowId'),
                'correlation_status': meta.get('correlationStatus'),
                'body_kind': body.get('kind'), 'body_truncated': body.get('truncated'),
                'start_ms': meta.get('startMs'), 'duration_ms': meta.get('durationMs')}
        try:
            data = body_bytes(body)
            item['body_bytes'] = len(data)
            item['stored_hash_matches'] = hashlib.sha256(data).hexdigest() == body.get('sha256')
        except (ValueError, TypeError) as error:
            item['stored_hash_matches'] = False
            errors.append({'file': path.name, 'error': type(error).__name__})
        counts['packets'] += 1
        counts['origin_nonzero'] += bool(call)
        counts['origin_resolved'] += item['call_resolved']
        counts['truncated_bodies'] += bool(body.get('truncated'))
        counts['body_hash_mismatches'] += not item['stored_hash_matches']
        counts['missing_execution_context'] += not bool(item['execution_context_id'])
        seen[(obj.get('method'), url)] += 1
        packets.append(item)
    return {'counts': dict(counts), 'errors': errors, 'packets': packets,
            'repeated_method_url_keys': sum(n > 1 for n in seen.values()),
            'hash_scope': 'stored decoded text re-encoded as UTF-8, or stored base64 bytes; not wire bytes'}
