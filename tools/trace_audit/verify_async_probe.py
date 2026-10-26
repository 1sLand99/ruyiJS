"""Verify explicit causal evidence against the local page's observed markers."""
import argparse
import json
from pathlib import Path

from .async_probe import EXPECTED
from .async_evidence import analyze,load_rows
from .rng_probe import digest
from .binary import CALL,header
from .jsonlines import dictionary


def check_call_ids(folder,proof):
    by_file={}
    for marker in proof['markers']:
        by_file.setdefault(marker['file'],[]).append(marker)
    for filename,markers in by_file.items():
        pid=int(filename.removeprefix('trace_process_').removesuffix('.jsonl'))
        prefix=folder/'jscall'/f'trace_jscall_process_{pid}'
        functions,stats,errors=dictionary(prefix.with_suffix('.dict.jsonl'))
        if errors or not stats:raise ValueError('missing call dictionary statistics')
        calls={}
        with prefix.with_suffix('.bin').open('rb') as stream:
            if header(stream,b'JSCT',CALL.size)!=pid:raise ValueError('call PID differs')
            while block:=stream.read(CALL.size):
                if len(block)!=CALL.size:raise ValueError('partial call binary')
                call,parent,fn,duration,depth,argc,flags,entry,reserved=CALL.unpack(block)
                if call in calls:raise ValueError('duplicate call identity')
                calls[call]=(fn,parent)
        if len(calls)!=stats['recorded']:raise ValueError('call writer count differs')
        for marker in markers:
            if marker['origin_call_id'] not in calls:raise ValueError('marker references absent call')
            fn,_=calls[marker['origin_call_id']]
            if functions[fn]['name']!='record':raise ValueError('marker call identifies wrong source function')
        proof.setdefault('call_id_evidence',[]).append({'pid':pid,'markers':len(markers),
            'binary_sha256':digest(prefix.with_suffix('.bin')),
            'dictionary_sha256':digest(prefix.with_suffix('.dict.jsonl'))})


def verify_case(case,proof,require_contexts):
    page=case['page']
    if page['events']!=EXPECTED or page['errors'] or not page['done'] or page['intervalCount']!=3:
        raise ValueError('page workload did not finish as specified')
    if [r['label'] for r in proof['markers']]!=EXPECTED:
        raise ValueError('markers missing, duplicated or out of page sequence')
    if any(proof['writer_losses'].values()) or not proof['writer_processes']:
        raise ValueError('trace writer losses or missing terminal statistics')
    if proof['message_kinds']!={'window_post_message':3,'message_port_post_message':1,'dedicated_worker_post_message':2}:
        raise ValueError('expected message paths missing')
    if sum(row['relation']=='send_to_receive' for row in proof['edges'])!=6:
        raise ValueError('message identities unresolved')
    if require_contexts:
        if proof['gaps']:raise ValueError('causal proof gaps: '+json.dumps(proof['gaps']))
        if proof['schedule_causes']!={'queue_microtask':2,'promise_reaction':3,'set_timeout':1,'set_interval':1}:
            raise ValueError('fixture schedule causes/counts incomplete')
        if proof['resume_causes']!={'queue_microtask':2,'promise_reaction':3,'set_timeout':1,'set_interval':3}:
            raise ValueError('fixture resume causes/counts incomplete')
        labels={row['label']:row for row in proof['markers']}
        causes={'microtask':'queue_microtask','promise':'promise_reaction','timeout':'set_timeout',
                'interval-1':'set_interval','interval-2':'set_interval','interval-3':'set_interval',
                'complete':'queue_microtask'}
        for label,cause in causes.items():
            if labels[label]['cause']!=cause:raise ValueError('marker linked to wrong async cause: '+label)
        if len({labels[name]['execution_context_id'] for name in ('timeout','before-dispatch','listener','after-dispatch')})!=1:
            raise ValueError('synchronous listener changed its surrounding execution context')
        if len({labels['interval-'+str(n)]['execution_context_id'] for n in (1,2,3)})!=3:
            raise ValueError('recurring callback reused an execution id')
        if len({labels['interval-'+str(n)]['async_context_id'] for n in (1,2,3)})!=1:
            raise ValueError('recurring callback lost its shared schedule identity')
        if case['mode']=='calls' and any(not row['origin_call_id'] for row in proof['markers']):
            raise ValueError('call-enabled markers lack call identity')
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-contexts',action='store_true')
    args=parser.parse_args();report=json.loads(args.report.read_text('utf-8'));result={'cases':[]}
    for case in report['cases']:
        if case['mode']=='off':
            if (args.report.parent/case['folder']/'domtrace').exists():
                raise ValueError('off case unexpectedly produced trace')
            continue
        rows,sources=load_rows(args.report.parent/case['folder'])
        proof=analyze(rows);verify_case(case,proof,args.require_contexts)
        if case['mode']=='calls':check_call_ids(args.report.parent/case['folder'],proof)
        result['cases'].append({'round':case['round'],'mode':case['mode'],'proof':proof,'sources':sources})
    if len(result['cases'])!=report['rounds']*2:raise ValueError('missing trace cases')
    result.update(schema='local.async-evidence.v1',input_sha256=digest(args.report),
        all_contexts_resolved=all(not case['proof']['gaps'] for case in result['cases']),
        page_results_equal=True,full_goal_complete=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps({'cases':len(result['cases']),'all_contexts_resolved':result['all_contexts_resolved'],
        'schedule_causes':[case['proof']['schedule_causes'] for case in result['cases']]}))


if __name__=='__main__':main()
