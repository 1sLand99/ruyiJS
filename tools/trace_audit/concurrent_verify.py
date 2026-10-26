"""Verify equal-payload concurrent round trips across actual distinct-site processes."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
from urllib.parse import urlsplit

from .async_evidence import load_rows,analyze,context_key
from .concurrent_probe import validate_page
from .concurrent_fixture import HOSTS
from .message_graph import MessageGraph
from .rng_probe import digest
from .binary import CALL,header
from .jsonlines import dictionary


def prove(rows,page,folder,mode):
    validate_page(page);basic=analyze(rows)
    if basic['gaps'] or any(basic['writer_losses'].values()):raise ValueError('causal gaps or writer loss')
    graph=MessageGraph(rows)
    if len(graph.messages)!=66:raise ValueError('expected 66 handshake/data messages')
    if basic['schedule_causes']!={'promise_reaction':48} or basic['resume_causes']!={'promise_reaction':48}:
        raise ValueError('missing per-hop promise evidence')
    sites=defaultdict(set);markers=[];workers=[];writers=set()
    for row in rows:
        if row['type']=='script_root' and row.get('phase')=='start':
            sites[urlsplit(row['url']).hostname].add(row['process_instance_id'])
        if row['type']=='call' and row.get('args',[None])[0]=='data-concurrent-proof':markers.append(row)
        if row['type']=='worker_created':workers.append(row)
        if row['type']=='domtrace_writer_stats':writers.add(row['process_instance_id'])
    if set(sites)!=set(HOSTS) or any(len(group)!=1 for group in sites.values()):
        raise ValueError('site/process attribution ambiguous')
    processes={host:next(iter(group)) for host,group in sites.items()}
    if len(set(processes.values()))!=3 or writers!=set(processes.values()):
        raise ValueError('three distinct captured processes and writer summaries required')
    if len(markers)!=68 or len(workers)!=2:raise ValueError('marker/worker count differs')
    by_context=defaultdict(list)
    for marker in markers:
        key=context_key(marker)
        if key not in graph.contexts:raise ValueError('marker context undeclared')
        declaration=graph.contexts[key]
        expected_async=declaration.get('source_async_context_id',0) if declaration['type']=='message_receive' else declaration.get('async_context_id',0)
        if marker.get('async_context_id',0)!=expected_async:raise ValueError('marker async identity differs')
        by_context[key].append(marker['args'][1])
    parent_markers=[m['args'][1] for m in markers if m['process_instance_id']==processes[HOSTS[0]]]
    if parent_markers!=page['order']:raise ValueError('parent marker trace differs from page')
    next_messages=defaultdict(list)
    for identity in graph.messages:
        previous,hops=graph.incoming_for_send(identity)
        if previous:next_messages[previous].append((identity,hops))
    source_pid=processes[HOSTS[0]]
    outgoing=[m for m in graph.messages.values() if m['send']['process_instance_id']==source_pid]
    outgoing.sort(key=lambda m:m['send']['message_sequence'])
    if len(outgoing)!=16:raise ValueError('wrong parent outgoing count')
    circuits=[];used=set();worker_by_process={r['process_instance_id']:r for r in workers}
    for ordinal,first in enumerate(outgoing):
        branch=ordinal%2;sequence=ordinal//2+1
        peer_process=processes[HOSTS[branch+1]];path=[first['send']['message_id']];schedule_hops=[]
        for _ in range(3):
            successors=next_messages[path[-1]]
            if len(successors)!=1:raise ValueError('round trip has missing/ambiguous continuation')
            identity,hops=successors[0]
            if len(hops)!=1 or hops[0]['cause']!='promise_reaction':
                raise ValueError('continuation must be one recorded promise edge')
            path.append(identity);schedule_hops.extend(hops)
        if used.intersection(path):raise ValueError('two round trips share a message')
        used.update(path);messages=[graph.messages[k] for k in path]
        expected=[(source_pid,peer_process,'window_post_message'),
                  (peer_process,peer_process,'dedicated_worker_post_message'),
                  (peer_process,peer_process,'dedicated_worker_post_message'),
                  (peer_process,source_pid,'window_post_message')]
        for message,(sender,receiver,kind) in zip(messages,expected):
            if (message['send']['process_instance_id'],message['receive']['process_instance_id'],message['send']['message_kind'])!=(sender,receiver,kind):
                raise ValueError('message route crossed to wrong branch')
        worker=worker_by_process[peer_process]
        if (messages[1]['send']['source_global_id'],messages[1]['send']['target_global_id'])!=(worker['owner_window_id'],worker['worker_id']):
            raise ValueError('worker request endpoint differs from created owner')
        if (messages[2]['send']['source_global_id'],messages[2]['send']['target_global_id'])!=(worker['worker_id'],worker['owner_window_id']):
            raise ValueError('worker response endpoint differs from created owner')
        if messages[0]['send']['target_global_id']!=worker['owner_window_id'] or messages[3]['send']['source_global_id']!=worker['owner_window_id']:
            raise ValueError('frame endpoint differs from worker owner window')
        expected_labels=[f'frame:receive:{sequence}',None,f'frame:worker-receive:{sequence}',f'parent:receive:{branch}:{sequence}']
        for message,label in zip(messages,expected_labels):
            if label and label not in by_context[message['target_context']]:
                raise ValueError('message delivered to wrong labeled callback')
        circuits.append({'branch':branch,'sequence':sequence,'message_ids':path,'async_hops':schedule_hops})
    if len(used)!=64 or len(set(graph.messages)-used)!=2:raise ValueError('unexplained data messages')
    for identity in set(graph.messages)-used:
        message=graph.messages[identity]
        if message['receive']['process_instance_id']!=source_pid or not any(
                label.startswith('parent:ready:') for label in by_context[message['target_context']]):
            raise ValueError('remaining message is not the startup handshake')
    origins=Counter()
    if mode=='calls':
        for process in processes.values():
            pid=int(process.split('-',1)[0]);prefix=folder/'jscall'/f'trace_jscall_process_{pid}'
            functions,stats,errors=dictionary(prefix.with_suffix('.dict.jsonl'));calls={}
            if errors or not stats or any(stats.get(k,0) for k in ('dropped_limit','dropped_chunks','io_errors')):
                raise ValueError('call dictionary invalid or capture loss')
            with prefix.with_suffix('.bin').open('rb') as stream:
                header(stream,b'JSCT',CALL.size)
                for row in CALL.iter_unpack(stream.read()):
                    if row[0] in calls:raise ValueError('duplicate binary call id')
                    calls[row[0]]=row[2]
            if len(calls)!=stats['recorded']:raise ValueError('call binary count differs from writer')
            for marker in (r for r in markers if r['process_instance_id']==process):
                fn=calls.get(marker['origin_call_id'])
                if fn is None:raise ValueError('marker origin call missing')
                meta=functions[fn];stack=marker.get('stack') or []
                matches=[n for n,frame in enumerate(stack) if frame.get('func')==meta['name'] and frame.get('file')==meta['url']]
                if len(matches)!=1:raise ValueError('origin call does not match a unique observed stack frame')
                origins['direct' if matches[0]==0 else 'observed_ancestor']+=1
    payloads=dict(Counter(str(r.get('args',[None])[0]) for r in rows
        if r['type']=='call' and r.get('member')=='postMessage'))
    if payloads!={'ping':32,'pong':32,'ready':2}:raise ValueError('equal-content fixture was changed')
    ids=Counter(key[2] for key in graph.contexts)
    return {'processes_by_site':processes,'messages':66,'cross_process_messages':sum(
        m['send']['process_instance_id']!=m['receive']['process_instance_id'] for m in graph.messages.values()),
        'markers':68,'promise_hops':48,'circuits':circuits,'writer_losses':basic['writer_losses'],
        'marker_call_origin_kind':dict(origins),
        'equal_payload_observations':payloads,
        'numeric_context_ids_reused_across_processes':sum(count>1 for count in ids.values()),
        'partial_order_only':True,'global_order_inferred':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=json.loads(args.report.read_text('utf-8'));result={'cases':[]}
    for case in report['cases']:
        validate_page(case['page'])
        if case['mode']=='off':continue
        folder=args.report.parent/case['folder'];rows,sources=load_rows(folder)
        proof=prove(rows,case['page'],folder,case['mode'])
        result['cases'].append({'round':case['round'],'mode':case['mode'],'proof':proof,'sources':sources})
    if len(result['cases'])!=report['rounds']*2:raise ValueError('missing trace cases')
    result.update(schema='local.concurrent-proof.v1',verified=True,input_sha256=digest(args.report),full_goal_complete=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps({'cases':len(result['cases']),'circuits_per_case':16,'messages_per_case':66,
        'cross_process_per_case':[c['proof']['cross_process_messages'] for c in result['cases']],'verified':True}))


if __name__=='__main__':main()
