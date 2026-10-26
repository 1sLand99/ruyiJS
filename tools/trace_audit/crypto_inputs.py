"""Extract complete random-byte inputs with explicit script-root/document evidence."""
import argparse
import hashlib
import json
import uuid
from pathlib import Path


def extract(run):
    documents={}
    for path in (run/'http_packet').glob('*.http_packet.json'):
        packet=json.loads(path.read_text('utf-8'))
        if packet['meta'].get('requestKind') not in ('document','subdocument') or packet['status']!=200:
            continue
        documents.setdefault(packet['url'],[]).append({'file':path.name,
            'packet_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'body_sha256':packet['responseBody'].get('sha256'),
            'inner_window_id':packet['meta'].get('innerWindowId')})
    groups={}
    ambiguous=set()
    rejected=[]
    sources=[]
    for path in sorted((run/'domtrace').glob('*.jsonl')):
        roots=[]
        process=None
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for number,line in enumerate(stream,1):
                digest.update(line)
                if not any(marker in line for marker in (b'"script_root"',b'"Crypto"',b'"trace_init"')):continue
                row=json.loads(line)
                if row.get('type')=='trace_init':process=row.get('process_instance_id')
                if row.get('type')=='script_root':
                    if row.get('phase')=='start':roots.append((row.get('execution_context_id'),row.get('url')))
                    elif roots and roots[-1][0]==row.get('execution_context_id'):roots.pop()
                    continue
                if row.get('interface')!='Crypto' or row.get('type')!='call' or row.get('member') not in ('getRandomValues','randomUUID'):continue
                url=roots[-1][1] if roots else None
                source=next((x.get('file') for x in row.get('stack',[]) if x.get('file')==url),None)
                args=row.get('postArgs') or []
                value=args[0] if args and isinstance(args[0],dict) else {}
                encoded=value.get('hex')
                reason=None
                if row.get('ok') is False:reason='recorded call failed'
                elif not url or source!=url or len(documents.get(url,[]))!=1:reason='ambiguous document/root attribution'
                elif row['member']=='randomUUID':
                    try:
                        parsed=uuid.UUID(row.get('return',''))
                        if parsed.version!=4:reason='UUID is not version 4'
                        data=parsed.bytes
                        encoded={'method':'randomUUID','value':str(parsed)}
                    except (ValueError,AttributeError,TypeError):reason='invalid UUID'
                elif value.get('truncated') or not isinstance(encoded,str):reason='missing or truncated byte contents'
                else:
                    try:
                        data=bytes.fromhex(encoded)
                        if len(encoded)!=len(data)*2 or len(data)!=value.get('byteLength'):reason='invalid byte length'
                    except ValueError:reason='invalid hex'
                if reason:
                    rejected.append({'file':path.name,'line':number,'reason':reason});continue
                identity=(process,url)
                if identity in ambiguous:
                    rejected.append({'file':path.name,'line':number,'reason':'document contains multiple Crypto receivers'})
                    continue
                group=groups.setdefault(identity,{'url':url,'values':[],'evidence':[],
                    'process_instance_id':process,'packet':documents[url][0]})
                object_id=row.get('thisObj',{}).get('id')
                if group['evidence'] and group['evidence'][0]['crypto_object_id']!=object_id:
                    rejected.extend({'file':x['file'],'line':x['line'],'reason':'document contains multiple Crypto receivers'}
                                    for x in group['evidence'])
                    rejected.append({'file':path.name,'line':number,'reason':'document contains multiple Crypto receivers'})
                    ambiguous.add(identity)
                    del groups[identity]
                    continue
                group['values'].append(encoded)
                group['evidence'].append({'file':path.name,'line':number,'seq':row.get('seq'),
                    'origin_call_id':str(row.get('origin_call_id',0)),
                    'method':row['member'],
                    'crypto_object_id':row.get('thisObj',{}).get('id'),
                    'byte_length':len(data),'bytes_sha256':hashlib.sha256(data).hexdigest()})
        sources.append({'file':path.relative_to(run).as_posix(),'sha256':digest.hexdigest()})
    urls=[g['url'] for g in groups.values()]
    if len(set(urls))!=len(urls):raise ValueError('same URL in multiple processes needs stronger realm attribution')
    return {'schema':'ruyijs.recorded-crypto-inputs.v1',
            'documents':[{'url':g['url'],'values':g['values']} for g in groups.values()],
            'evidence':[{k:v for k,v in g.items() if k!='values'} for g in groups.values()],
            'rejected':rejected,
            'sources':sources,
            'attribution':'active script_root URL equals stack URL and unique captured document; not a universal realm declaration'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=extract(args.run)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps({'documents':len(report['documents']),
        'calls':sum(len(x['values']) for x in report['documents']),'rejected':len(report['rejected'])}))


if __name__=='__main__':main()
