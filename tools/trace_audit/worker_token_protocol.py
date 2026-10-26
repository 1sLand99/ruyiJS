"""Bounded opaque token envelope for a future Worker pipe integration."""
import struct

MAGIC = b'WTP1'
VERSION = 1
# magic, version, direction, kind, reserved, worker/process/global/context fields, sequence.
HEADER = struct.Struct('<4sBBH Q Q Q Q Q Q Q Q Q')
MAX_PAYLOAD = 16 * 1024 * 1024 - HEADER.size


class TokenError(ValueError):
    pass


def _integer(row, name, minimum=0, maximum=(1 << 64) - 1):
    value = row.get(name)
    if type(value) is not int or not minimum <= value <= maximum:
        raise TokenError(f'{name} must be a bounded integer')
    return value


def encode(token, payload=b''):
    if not isinstance(payload, (bytes, bytearray)) or len(payload) > MAX_PAYLOAD:
        raise TokenError('payload exceeds frame bound')
    direction = _integer(token, 'direction', 0, 1)
    kind = _integer(token, 'kind', 0, 255)
    values = [_integer(token, key, 1 if key in ('worker_id', 'process_instance_id', 'sequence') else 0) for key in (
        'worker_id', 'process_instance_id', 'trace_session', 'source_global_id',
        'target_global_id', 'source_execution_context_id', 'source_async_context_id',
        'sequence')]
    return HEADER.pack(MAGIC, VERSION, direction, kind, 0, *values) + bytes(payload)


def decode(frame):
    if not isinstance(frame, (bytes, bytearray)) or len(frame) < HEADER.size:
        raise TokenError('frame is shorter than token header')
    fields = HEADER.unpack(bytes(frame[:HEADER.size]))
    magic, version, direction, kind, reserved, *values = fields
    if magic != MAGIC or version != VERSION or reserved != 0 or direction > 1 or kind > 255:
        raise TokenError('token header version, magic, direction or reserved bits invalid')
    names = ('worker_id', 'process_instance_id', 'trace_session', 'source_global_id',
             'target_global_id', 'source_execution_context_id', 'source_async_context_id', 'sequence')
    token = dict(zip(names, values)); token.update(direction=direction, kind=kind)
    if not token['worker_id'] or not token['process_instance_id'] or not token['sequence']:
        raise TokenError('worker, process and sequence identities must be nonzero')
    token['payload'] = bytes(frame[HEADER.size:])
    return token


def from_trace(row, worker_id, direction, payload=b''):
    """Build an envelope from one explicit trace send row; payload is opaque."""
    return encode({'worker_id': worker_id, 'process_instance_id': row['source_pid'],
                   'trace_session': row.get('source_trace_session', row.get('session', 0)),
                   'source_global_id': row.get('source_global_id', 0),
                   'target_global_id': row.get('target_global_id', 0),
                   'source_execution_context_id': row.get('source_execution_context_id', 0),
                   'source_async_context_id': row.get('source_async_context_id', 0),
                   'sequence': row['message_sequence'], 'direction': direction,
                   'kind': row.get('message_kind_id', 0)}, payload)
