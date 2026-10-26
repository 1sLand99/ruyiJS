"""Compare an observed serialized byte array to a complete replay serializer subtree."""
import argparse
import hashlib
import json
from pathlib import Path
import zlib

from .binary import CALL, VALUE, header
from .jsonlines import dictionary
from .rng_probe import digest
from .serialized_payload import reconstruct, differences, encode


def reference_values(path, calls):
    result = {}
    size = path.stat().st_size
    with path.open('rb') as stream:
        header(stream, b'JSCV', VALUE.size)
        while block := stream.read(VALUE.size):
            if len(block) != VALUE.size: raise ValueError('incomplete value header')
            call, slot, kind, flags, length = VALUE.unpack(block)
            if stream.tell() + length > size: raise ValueError('incomplete value payload')
            if call not in calls:
                stream.seek(length, 1); continue
            value = stream.read(length)
            if (call, slot) in result: raise ValueError('duplicate value slot')
            result[call, slot] = kind, flags, value
    return result


def byte_array(record):
    kind, flags, payload = record
    if kind != 9 or flags: raise ValueError('not a complete recorded array')
    values = json.loads(payload)
    if not isinstance(values, list) or any(type(v) is not int or not 0 <= v <= 255 for v in values):
        raise ValueError('array contains omitted or non-byte values')
    return bytes(values)


def replay_rows(path, serializer, column, next_function, next_column):
    rows, started, closed, next_entry, limits = [], False, False, None, []
    active = set()
    root = None
    with path.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if row.get('type') == 'limit_reached': limits.append(number)
            if row.get('type') != 'jscall': continue
            enter = row.get('phase') == 'enter'
            selected = row.get('callee') == serializer and row.get('column') == column
            if enter and selected:
                if closed: raise ValueError('more than one serializer root before next stage')
                if not started: root = row['call_id']; started = True
                active.add(row['call_id'])
            if started and row['call_id'] in active:
                rows.append({'file_line': number, **row})
                if not enter:
                    active.remove(row['call_id'])
                    if row['call_id'] == root: closed = True
            if closed and enter and row.get('callee') == next_function and row.get('column') == next_column:
                next_entry = {'file_line': number, **row}; break
    if limits or active or not next_entry: raise ValueError('missing complete serializer/next-stage boundary')
    return rows, next_entry


def align(run, pid, array_call, serializer_call, replay, output):
    output.mkdir(parents=True, exist_ok=False)
    prefix = run/'jscall'/f'trace_jscall_process_{pid}'
    functions, _, errors = dictionary(prefix.with_suffix('.dict.jsonl'))
    if errors: raise ValueError(errors)
    metadata = {}
    with prefix.with_suffix('.bin').open('rb') as stream:
        header(stream, b'JSCT', CALL.size)
        while block := stream.read(CALL.size*16384):
            for call, parent, fn, duration, depth, argc, flags, entry, _ in CALL.iter_unpack(block):
                if call in (array_call, serializer_call):
                    metadata[call] = {'parent': parent, 'flags': flags, 'function': functions[fn]}
    if len(metadata) != 2 or metadata[array_call]['parent'] != metadata[serializer_call]['parent']:
        raise ValueError('serializer and array stage do not have the same observed parent')
    parent = metadata[array_call]['parent']
    details = reference_values(prefix.with_suffix('.detail.bin'), {array_call, serializer_call, parent})
    raw = byte_array(details[array_call, 0])
    compressed = byte_array(details[array_call, 65535])
    if compressed[:3] != bytes((253, 1, 1)): raise ValueError('unsupported recorded compression envelope')
    inflate = zlib.decompressobj(-15)
    inflated = inflate.decompress(compressed[3:]) + inflate.flush()
    if inflated != raw or not inflate.eof or inflate.unused_data: raise ValueError('recorded compression roundtrip failed')
    reference = json.loads(raw.decode('utf-8'))
    if raw != b' ' + encode(reference) + b' ': raise ValueError('reference JSON is not exactly reproduced')
    kind, flags, end = details[serializer_call, 65535]
    if (kind, flags, len(end)) != (4, 0, 4) or int.from_bytes(end, 'little', signed=True) != len(raw)-1:
        raise ValueError('reference serializer end does not bound recorded bytes')
    function = metadata[serializer_call]['function']; stage = metadata[array_call]['function']
    if function['url'] != stage['url']: raise ValueError('reference stages use different sources')
    rows, next_entry = replay_rows(replay, function['name'], function['column'], stage['name'], stage['column'])
    if next_entry['url'] != stage['url'] or any(row['url'] != function['url'] for row in rows):
        raise ValueError('replay script URL differs')
    current, proof = reconstruct(rows, function['name'], function['column'])
    delta = differences(reference, current)
    body_kind, body_flags, body = details[parent, 65535]
    if body_kind != 6 or body_flags: raise ValueError('recorded request encoder return is incomplete')
    matches = []
    for path in (run/'http_packet').glob('*.http_packet.json'):
        packet = json.loads(path.read_text('utf-8'))
        if packet.get('method') != 'POST': continue
        params = packet.get('params', {})
        post = params.get('postText')
        if isinstance(post, str) and post.encode() == body:
            if params.get('postSha256') != hashlib.sha256(body).hexdigest():
                raise ValueError('recorded packet body hash differs')
            matches.append({'file':path.name,'sha256':digest(path)})
    if len(matches) != 1: raise ValueError('encoder return lacks unique matching HTTP packet')
    result = {'schema':'serialized-payload.alignment.v1','reference_calls':{str(k):v for k,v in metadata.items()},
        'reference_bytes':len(raw),'reference_json_bytes':len(encode(reference)),
        'reference_raw_sha256':hashlib.sha256(raw).hexdigest(),'compression_roundtrip':True,
        'recorded_encoder_bytes':len(body),'recorded_encoder_sha256':hashlib.sha256(body).hexdigest(),
        'matching_packets':matches,'replay':proof,'replay_json_bytes':len(encode(current)),
        'differences':delta,'sources':{str(p):digest(p) for p in
            (prefix.with_suffix('.bin'),prefix.with_suffix('.dict.jsonl'),prefix.with_suffix('.detail.bin'),replay)},
        'limits':['One complete serializer subtree; full replay trace may stop at a later record budget.',
                  'Payload equality does not prove task order, request equality or server acceptance.']}
    for name,value in [('reference-payload',reference),('replay-payload',current),('serializer-calls',rows),('result',result)]:
        (output/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n','utf-8')
    (output/'reference-serialized.bin').write_bytes(raw)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path);parser.add_argument('replay',type=Path)
    parser.add_argument('--pid',type=int,required=True);parser.add_argument('--array-call',type=int,required=True)
    parser.add_argument('--serializer-call',type=int,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=align(args.capture,args.pid,args.array_call,args.serializer_call,args.replay,args.output)
    print(json.dumps({'reference_bytes':report['reference_bytes'],'replay_json_bytes':report['replay_json_bytes'],
        'serializer_calls':report['replay']['serializer_calls'],'different_fields':len(report['differences'])}))


if __name__=='__main__':main()
