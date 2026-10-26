"""Read JSCT/JSCV v1 without materializing captured argument values."""
from array import array
from bisect import bisect_left
from collections import Counter
import struct

HEADER = struct.Struct('<4sHHII')
CALL = struct.Struct('<QQIIHHBBH')
VALUE = struct.Struct('<QHBBI')
PATHS = {0: 'unknown', 1: 'stack', 2: 'inline', 3: 'jit', 4: 'baseline'}


def header(stream, magic, record_size):
    data = stream.read(HEADER.size)
    if len(data) != HEADER.size:
        raise ValueError('incomplete file header')
    found, version, size, pid, reserved = HEADER.unpack(data)
    if (found, version, size) != (magic, 1, record_size):
        raise ValueError('unsupported magic/version/record size')
    return pid


def contains(ids, call):
    index = bisect_left(ids, call)
    return index < len(ids) and ids[index] == call


def calls(path, functions):
    ids, parents = array('Q'), array('Q')
    counts, paths, threads = Counter(), Counter(), Counter()
    errors = []
    with path.open('rb') as stream:
        pid = header(stream, b'JSCT', CALL.size)
        while data := stream.read(CALL.size * 32768):
            tail = len(data) % CALL.size
            if tail:
                errors.append({'trailing_bytes': tail})
                data = data[:-tail]
            for call, parent, func, duration, depth, argc, flags, entry, _ in CALL.iter_unpack(data):
                ids.append(call)
                if parent:
                    parents.append(parent)
                    counts['parent_edges'] += 1
                    counts['parent_not_earlier'] += int(parent >= call)
                    counts['parent_different_thread'] += int(parent >> 48 != call >> 48)
                counts['records'] += 1
                counts['unknown_function'] += int(func not in functions)
                counts['root_records'] += int(not parent)
                counts['native'] += bool(flags & 4)
                counts['caller_jit_gap'] += bool(flags & 64)
                counts['suspended'] += bool(flags & 16)
                counts['resumed'] += bool(flags & 32)
                counts['not_ok'] += not bool(flags & 2)
                paths[PATHS.get(entry, str(entry))] += 1
                threads[str(call >> 48)] += 1
    ids = array('Q', sorted(ids))
    counts['duplicate_call_ids'] = sum(a == b for a, b in zip(ids, ids[1:]))
    counts['missing_parent_records'] = sum(not contains(ids, p) for p in parents)
    return {'pid': pid, **counts, 'entry_paths': dict(paths),
            'threads': dict(threads), 'errors': errors}, ids


def details(path, ids, expected_pid):
    counts, types, flags = Counter(), Counter(), Counter()
    errors = []
    size = path.stat().st_size
    with path.open('rb') as stream:
        pid = header(stream, b'JSCV', VALUE.size)
        if pid != expected_pid:
            errors.append({'pid_mismatch': pid})
        while data := stream.read(VALUE.size):
            if len(data) != VALUE.size:
                errors.append({'incomplete_value_header': len(data)})
                break
            call, slot, typ, bits, length = VALUE.unpack(data)
            if stream.tell() + length > size:
                errors.append({'incomplete_payload_at': stream.tell(), 'expected_bytes': length})
                break
            counts['values'] += 1
            counts['payload_bytes'] += length
            counts['missing_call_values'] += not contains(ids, call)
            counts['returns' if slot == 65535 else 'this' if slot == 65534 else 'arguments'] += 1
            types[str(typ)] += 1
            for bit, name in ((1, 'truncated'), (2, 'unreadable'),
                              (4, 'identity_only'), (8, 'unstable_identity')):
                flags[name] += bool(bits & bit)
            stream.seek(length, 1)
    return {**counts, 'types': dict(types), 'flags': dict(flags), 'errors': errors}
