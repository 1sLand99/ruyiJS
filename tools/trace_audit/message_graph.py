"""Resolve local/cross-process message lineage exclusively through explicit IDs."""
from collections import defaultdict

from .async_evidence import context_key

SOURCE_FIELDS=('source_pid','source_process_instance_nonce','source_trace_session',
               'source_execution_context_id','source_async_context_id','message_sequence')
ENDPOINT_FIELDS=('message_kind','source_global_id','target_global_id','source_global_kind','target_global_kind')


class MessageGraph:
    def __init__(self,rows):
        self.contexts={};self.schedules={};self.messages={}
        sends=defaultdict(list);receives=defaultdict(list)
        for row in rows:
            kind=row['type']
            if (kind in ('script_root','async_resume') and row.get('phase')=='start') or kind=='message_receive':
                field='receiver_execution_context_id' if kind=='message_receive' else 'execution_context_id'
                key=context_key(row,field)
                if not key[-1] or key in self.contexts:raise ValueError('missing or duplicate execution identity')
                self.contexts[key]=row
            if kind=='async_schedule':
                key=context_key(row,'async_context_id')
                if not key[-1] or key in self.schedules:raise ValueError('missing or duplicate schedule identity')
                self.schedules[key]=row
            if kind in ('message_send','message_receive'):
                identity=row.get('message_id')
                if not identity:raise ValueError('message identity missing')
                (sends if kind=='message_send' else receives)[identity].append(row)
        if set(sends)!=set(receives):raise ValueError('unmatched message send/receive')
        for identity in sends:
            if len(sends[identity])!=1 or len(receives[identity])!=1:
                raise ValueError('ambiguous message identity')
            send,receive=sends[identity][0],receives[identity][0]
            if any(send.get(field)!=receive.get(field) for field in SOURCE_FIELDS+ENDPOINT_FIELDS):
                raise ValueError('transport changed source or endpoint identity')
            sender=context_key(send,'source_execution_context_id',True)
            if sender[0]!=send['process_instance_id'] or sender[1]!=send['session']:
                raise ValueError('sender token does not belong to emitting process/session')
            if identity!=f"{sender[0]}-{send['message_sequence']}":
                raise ValueError('message token and declared source identity differ')
            if sender not in self.contexts:raise ValueError('message source context undeclared')
            self.messages[identity]={'send':send,'receive':receive,'source_context':sender,
                'target_context':context_key(receive,'receiver_execution_context_id')}
        for key,row in self.contexts.items():
            if row['type']=='async_resume':self.parent(key)

    def parent(self,key):
        row=self.contexts.get(key)
        if row is None:raise ValueError('missing execution context')
        if row['type']=='async_resume':
            schedule_key=(key[0],row.get('schedule_session',row.get('session',0)),row['async_context_id'])
            schedule=self.schedules.get(schedule_key)
            if schedule is None:raise ValueError('resume schedule absent')
            if schedule['async_cause']!=row['async_cause']:raise ValueError('schedule/resume cause differs')
            parent=context_key(schedule,'parent_execution_context_id')
            if not parent[-1] or parent not in self.contexts:raise ValueError('schedule parent undeclared')
            return parent,schedule
        return None,None

    def incoming_for_send(self,identity):
        key=self.messages[identity]['source_context'];seen=set();hops=[]
        while True:
            if key in seen:raise ValueError('cycle in execution lineage')
            seen.add(key)
            if len(seen)>64:raise ValueError('execution lineage bound exceeded')
            row=self.contexts[key]
            if row['type']=='message_receive':return row['message_id'],hops
            if row['type']=='script_root':return None,hops
            parent,schedule=self.parent(key)
            if parent is None:raise ValueError('unsupported execution lineage')
            hops.append({'resume_context':list(key),'schedule_context':list(context_key(schedule,'async_context_id')),
                         'parent_context':list(parent),'cause':row['async_cause']})
            key=parent
