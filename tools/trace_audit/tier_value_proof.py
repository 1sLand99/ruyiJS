"""Validate synchronous fixture value nesting against call records and its source oracle."""
import struct

from .binary import CALL, HEADER, VALUE, header
from .tier_oracle import TierOracle


def decode(kind, payload):
    if kind==1 and not payload: return ('undefined',)
    if kind==2 and not payload: return None
    if kind==3 and len(payload)==1 and payload[0] in (0,1): return bool(payload[0])
    if kind==4 and len(payload)==4: return struct.unpack('<i',payload)[0]
    if kind==5 and len(payload)==8: return struct.unpack('<d',payload)[0]
    if kind==6: return payload.decode('utf-8')
    if kind==8: return ('label',payload.decode('utf-8'))
    if kind==9: return ('array_representation',payload)
    if kind==10: return ('bytes',payload)
    raise ValueError('unsupported fixture value type or length')


def prove(index, detail, expected_runs, complete):
    if complete and index.gaps: raise ValueError('complete fixture proof has caller gaps')
    oracle=TierOracle(expected_runs,complete)
    stack=[];returns=records=0
    size=detail.stat().st_size
    with detail.open('rb') as stream:
        if header(stream,b'JSCV',VALUE.size)!=index.pid: raise ValueError('value file process mismatch')
        while block:=stream.read(VALUE.size):
            if len(block)!=VALUE.size: raise ValueError('partial value header')
            call,slot,kind,flags,length=VALUE.unpack(block)
            if flags or length>65536 or stream.tell()+length>size:
                raise ValueError('incomplete or oversized fixture value')
            value=decode(kind,stream.read(length));records+=1
            if slot==65534:
                frame=index.row(call)
                if frame['parent']!=(stack[-1]['id'] if stack else 0):
                    raise ValueError('value nesting and observed call parent differ')
                frame['args']={}
                oracle.enter(frame,stack[-1] if stack else None)
                stack.append(frame)
            else:
                if not stack or stack[-1]['id']!=call: raise ValueError('value slot has no active matching frame')
                frame=stack[-1]
                if slot==65535:
                    frame['result']=value
                    if frame['leave_offset']!=HEADER.size+returns*CALL.size:
                        raise ValueError('call/value leave ordering differs')
                    oracle.leave(frame,stack[-2] if len(stack)>1 else None)
                    stack.pop();returns+=1
                else:
                    if slot>=frame['argc'] or slot in frame['args']: raise ValueError('invalid or duplicate argument slot')
                    frame['args'][slot]=value
    if stack or returns!=len(index.offsets): raise ValueError('missing value frame or return')
    return {'value_records':records,'completed_calls':returns,**oracle.finish(),
        'complete_sequence_checked':complete,
        'scope':'Synchronous local tier fixture only; object labels are never treated as captured fields.'}
