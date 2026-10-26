"""Inspect selected JSCV values without mistaking type labels for object snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
from .binary import VALUE,header


def inspect(path,call_ids):
    selected=set(call_ids)
    records=[]
    size=path.stat().st_size
    with path.open('rb') as stream:
        pid=header(stream,b'JSCV',VALUE.size)
        while block:=stream.read(VALUE.size):
            if len(block)!=VALUE.size:raise ValueError('partial value header')
            call,slot,typ,flags,length=VALUE.unpack(block)
            if stream.tell()+length>size:raise ValueError('partial value payload')
            if call not in selected:
                stream.seek(length,1);continue
            payload=stream.read(length)
            item={'call_id':str(call),'slot':slot,'type_id':typ,'flags':flags,
                  'bytes':length,'sha256':hashlib.sha256(payload).hexdigest()}
            if typ==8 and flags==0:
                item['object_class_label']=payload.decode('utf-8',errors='replace')
                item['object_fields_captured']=False
            if typ==15:
                snapshot=json.loads(payload.decode('utf-8'))
                if snapshot.get('schema')!='jscall.object.v1':raise ValueError('unsupported object snapshot schema')
                item['object_snapshot']=snapshot
                item['object_snapshot_lossy']=bool(flags&1)
                item['object_fields_captured']=snapshot.get('root',{}).get('t') in ('object','array')
            records.append(item)
    return {'schema':'ruyijs.selected-value-coverage.v1','pid':pid,'file':str(path.resolve()),
            'selected_call_ids':[str(x) for x in call_ids],'records':records,
            'scope':'captured representation only; no reconstruction of omitted object properties'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('detail',type=Path)
    parser.add_argument('--call-id',type=int,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=inspect(args.detail,args.call_id)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps({'values':len(report['records']),
        'class_only_objects':sum(r.get('object_fields_captured') is False for r in report['records'])}))


if __name__=='__main__':main()
