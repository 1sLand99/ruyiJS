"""Join explicit local context/schedule/message IDs, preserving missing evidence."""
from collections import Counter, defaultdict
import json

from .rng_probe import digest


def load_rows(folder):
    rows=[];sources=[];selected=set()
    for path in sorted((folder/'domtrace').glob('*.jsonl')):
        identity=None;file_rows=[]
        with path.open('rb') as stream:
            for number,line in enumerate(stream,1):
                row=json.loads(line)
                if row.get('type')=='trace_init':identity=row
                if identity is None:raise ValueError('core trace lacks initial process declaration')
                item={**identity,**row,'file':path.name,'file_line':number}
                if row.get('type')=='script_root' and '/async-' in row.get('url',''):
                    selected.add(identity['process_instance_id'])
                file_rows.append(item)
        rows.extend(file_rows)
        sources.append({'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size})
    return [r for r in rows if r['process_instance_id'] in selected],sources


def context_key(row, field='execution_context_id', source=False):
    if source:
        identity=f"{row['source_pid']}-{row['source_process_instance_nonce']}"
        session=row.get('source_trace_session',row.get('session',0))
    else:
        identity=row['process_instance_id']
        session=row.get('trace_session',row.get('session',0))
    return identity,session,row.get(field,0)


def analyze(rows):
    contexts=defaultdict(list);schedules=defaultdict(list);sends=defaultdict(list)
    resumes=[];receives=[];markers=[];gaps=[];stats={}
    for row in rows:
        kind=row['type']
        if (kind in ('script_root','async_resume') and row.get('phase')=='start') or kind=='message_receive':
            field='receiver_execution_context_id' if kind=='message_receive' else 'execution_context_id'
            key=context_key(row,field)
            if not key[-1]:gaps.append({'kind':'zero_context_declaration','line':row['file_line']})
            else:contexts[key].append(row)
        if kind=='async_schedule':schedules[context_key(row,'async_context_id')].append(row)
        if kind=='async_resume' and row.get('phase')=='start':resumes.append(row)
        if kind=='message_send':sends[row.get('message_id')].append(row)
        if kind=='message_receive':receives.append(row)
        if kind=='call' and row.get('interface')=='Element' and row.get('member')=='setAttribute':
            args=row.get('args') or []
            if len(args)==2 and args[0]=='data-causal-proof':markers.append(row)
        if kind=='domtrace_writer_stats':stats[row['process_instance_id']]=row
    for key,values in contexts.items():
        if len(values)!=1:gaps.append({'kind':'ambiguous_context','identity':key})
    def declared(row,field,source=False):
        key=context_key(row,field,source)
        return len(contexts.get(key,[]))==1
    edges=[]
    for row in resumes:
        key=(row['process_instance_id'],row.get('schedule_session',row.get('session',0)),row['async_context_id'])
        found=schedules.get(key,[])
        if len(found)!=1:
            gaps.append({'kind':'missing_or_ambiguous_schedule','line':row['file_line'],'candidates':len(found)})
        else:
            if found[0].get('async_cause')!=row.get('async_cause'):
                gaps.append({'kind':'schedule_resume_cause_mismatch','line':row['file_line']})
            edges.append({'relation':'schedule_to_resume','source_line':found[0]['file_line'],
                'target_line':row['file_line'],'file':row['file'],'cause':row['async_cause'],
                'async_context_id':row['async_context_id'],'execution_context_id':row['execution_context_id']})
    for row in receives:
        found=sends.get(row.get('message_id'),[]) if row.get('message_id') else []
        if len(found)!=1:
            gaps.append({'kind':'missing_or_ambiguous_send','line':row['file_line'],'candidates':len(found)})
        else:
            sender=found[0]
            if sender['message_kind']!=row['message_kind'] or sender['source_pid']!=row['source_pid']:
                gaps.append({'kind':'message_metadata_mismatch','line':row['file_line']})
            for field in ('source_process_instance_nonce','source_trace_session','source_execution_context_id','source_async_context_id'):
                if sender.get(field)!=row.get(field):
                    gaps.append({'kind':'message_source_field_mismatch','field':field,'line':row['file_line']})
            if not declared(sender,'source_execution_context_id',True):
                gaps.append({'kind':'undeclared_message_source','line':sender['file_line']})
            edges.append({'relation':'send_to_receive','source_file':sender['file'],'source_line':sender['file_line'],
                'target_file':row['file'],'target_line':row['file_line'],'message_id':row['message_id'],
                'message_kind':row['message_kind'],'receiver_context':row['receiver_execution_context_id']})
    marked=[]
    for row in markers:
        key=context_key(row)
        found=contexts.get(key,[]) if key[-1] else []
        declaration=found[0] if len(found)==1 else None
        if declaration is None:gaps.append({'kind':'marker_context_missing','label':row['args'][1]})
        elif declaration['type']=='async_resume' and row.get('async_context_id')!=declaration['async_context_id']:
            gaps.append({'kind':'marker_async_identity_mismatch','label':row['args'][1]})
        elif declaration['type']=='script_root' and row.get('async_context_id') not in (None,0):
            gaps.append({'kind':'script_marker_has_async_identity','label':row['args'][1]})
        marked.append({'label':row['args'][1],'file':row['file'],'line':row['file_line'],
            'execution_context_id':key[-1],'async_context_id':row.get('async_context_id'),
            'origin_call_id':row.get('origin_call_id',0),'context_declared':declaration is not None,
            'context_kind':declaration['type'] if declaration else None,
            'cause':declaration.get('async_cause') if declaration else None})
    for row in schedules.values():
        for item in row:
            if item.get('parent_execution_context_id') and not declared(item,'parent_execution_context_id'):
                gaps.append({'kind':'undeclared_schedule_parent','line':item['file_line']})
    losses={key:sum(row.get(key,0) for row in stats.values()) for key in
        ('dropped_full','dropped_contention','dropped_oom','dropped_oversize','dropped_writer_failed','io_errors')}
    return {'markers':marked,'edges':edges,'gaps':gaps,'writer_losses':losses,
        'schedule_causes':dict(Counter(r['async_cause'] for v in schedules.values() for r in v)),
        'resume_causes':dict(Counter(r['async_cause'] for r in resumes)),
        'message_kinds':dict(Counter(r['message_kind'] for r in receives)),
        'context_declarations':len(contexts),'writer_processes':len(stats),
        'scope':'Explicit IDs only. File/timestamp adjacency is not used to assign a callback context.'}
