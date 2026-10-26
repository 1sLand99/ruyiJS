"""Compare primitive host-boundary observations at matching source locations."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path


def primitive(value):
    return value is None or isinstance(value,(bool,int,float,str)) and not (
        isinstance(value,str) and value.startswith(('[Object ','[Function ','[object ')))


def read(path, stop, script_url):
    records=defaultdict(list)
    with path.open('rb') as stream:
        for line_no,line in enumerate(stream,1):
            if stop and line_no>=stop:break
            row=json.loads(line)
            if row.get('type') not in ('get','set','call'):continue
            stack=row.get('stack') or []
            frame=next((x for x in stack if x.get('file')==script_url),None)
            if frame is None:continue
            value=row.get('value') if row['type'] in ('get','set') else row.get('return')
            if not primitive(value):continue
            args=row.get('args')
            args_key=json.dumps(args,sort_keys=True) if isinstance(args,list) and all(primitive(x) for x in args) else None
            key=(row['type'],row.get('interface'),row.get('member'),frame.get('line'),frame.get('col'),args_key)
            records[key].append({'line':line_no,'seq':row.get('seq'),'value':value})
    return records


def diff(reference,current):
    differences=[]
    counts=Counter()
    for key,left in reference.items():
        right=current.get(key,[])
        if not right:counts['unmatched_reference_keys']+=1;continue
        counts['matched_keys']+=1
        if len(left)!=len(right):counts['ambiguous_occurrence_keys']+=1;continue
        for before,after in zip(left,right):
            counts['compared_values']+=1
            if type(before['value'])!=type(after['value']) or before['value']!=after['value']:
                counts['different_values']+=1
                differences.append({'key':list(key),'reference':before,'replay':after})
    counts['unmatched_replay_keys']=sum(k not in reference for k in current)
    return {'schema':'ruyijs.primitive-boundary-diff.v1','counts':dict(counts),'differences':differences,
            'limitations':'Equal occurrence counts and source coordinates are alignment evidence, not proof of identical execution paths; object encodings are excluded.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path)
    parser.add_argument('replay',type=Path)
    parser.add_argument('--script-url',required=True)
    parser.add_argument('--reference-stop',type=int,default=0)
    parser.add_argument('--replay-stop',type=int,default=0)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=diff(read(args.reference,args.reference_stop,args.script_url),read(args.replay,args.replay_stop,args.script_url))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report['counts']))


if __name__=='__main__':main()
