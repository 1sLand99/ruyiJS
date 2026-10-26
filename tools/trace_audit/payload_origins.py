"""Verify the fourteen observed numeric differences against message and clock evidence."""
import argparse
import json
from pathlib import Path

from .rng_probe import digest


MESSAGE_FIELDS = {
    '/tmhp0': ('timeLoadInitMs',), '/ECvL0': ('timeExtraParamsMs',),
    '/fuhL4': ('timeInitMs',), '/ccKqy6': ('timeRenderMs',),
    '/jrshV1': ('timeParamsMs',), '/nulf3': ('timeTiefMs',),
    '/OtYa2/0/t': ('cs', 0, 1),
    '/jLEVv0/2/JeJZR2': ('apiJsResourceTiming', 'responseEnd'),
    '/jLEVv0/2/ePsF3': ('apiJsResourceTiming', 'duration')}
CLOCK_PAIRS = {
    '/URVD0': (289, 842), '/shUar7': (869, 8439), '/ghqno0': (869, 8439),
    '/RxXRQ8': (282, 868), '/mHsm4': (869, 10567)}


def get(value, path):
    for part in path: value = value[part]
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('alignment',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    alignment=json.loads(args.alignment.read_text('utf-8'))
    differences={row['path']:row for row in alignment['differences']}
    if set(differences)!=set(MESSAGE_FIELDS)|set(CLOCK_PAIRS):
        raise ValueError('this evidence mapping applies only to the verified captured deployment')
    parent=args.capture/'domtrace/trace_process_34928.jsonl'
    child=args.capture/'domtrace/trace_process_58620.jsonl'
    message=None
    with parent.open('rb') as stream:
        for n,line in enumerate(stream,1):
            if n==32638:
                row=json.loads(line)
                if (row.get('interface'),row.get('member'))!=('Window','postMessage'):
                    raise ValueError('recorded message boundary changed')
                message={'line':n,'seq':row['seq'],'call_id':row['origin_call_id'],'payload':row['args'][0]}
                break
    wanted={n for pair in CLOCK_PAIRS.values() for n in pair};clocks={}
    with child.open('rb') as stream:
        for n,line in enumerate(stream,1):
            if n>max(wanted):break
            if n not in wanted:continue
            row=json.loads(line)
            if (row.get('interface'),row.get('member'))!=('Date','now'):
                raise ValueError('recorded clock boundary changed')
            clocks[n]={'line':n,'seq':row['seq'],'value':row['return'],
                       'source_frame':(row.get('stack') or [None])[0]}
    proof=[]
    for path,field in MESSAGE_FIELDS.items():
        value=get(message['payload'],field)
        assert type(value) is int and value==differences[path]['reference']
        proof.append({'path':path,'kind':'parent_message_measurement','message_field':field,
            'message_line':message['line'],'message_seq':message['seq'],'value':value,
            'replay':differences[path]['replay']})
    for path,(start,end) in CLOCK_PAIRS.items():
        value=clocks[end]['value']-clocks[start]['value']
        assert value==differences[path]['reference']
        proof.append({'path':path,'kind':'child_Date_now_difference','start':clocks[start],
            'end':clocks[end],'value':value,'replay':differences[path]['replay']})
    report={'schema':'payload.numeric-origins.v1','mapping_scope':'manually reviewed mapping for this exact deployment',
        'fields':proof,'message_fields':len(MESSAGE_FIELDS),'clock_fields':len(CLOCK_PAIRS),
        'sources':{str(p):digest(p) for p in (parent,child,args.alignment)},
        'limits':['Numeric equality supports the source mapping together with the reviewed script assignments.',
            'Recorded parent message is outgoing data, not a license to overwrite arbitrary page globals.',
            'Runtime inputs, task deadlines and matching message identities still need native replay integration.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps({'verified_differences':len(proof),'parent_message_fields':9,'child_clock_differences':5}))


if __name__=='__main__':main()
