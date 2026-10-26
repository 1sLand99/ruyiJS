"""Cross-process lineage must survive equal payloads and reject identity corruption."""
import copy
import json
import unittest

from tools.trace_audit.message_graph import MessageGraph


def rows():
    a={'process_instance_id':'7-aaa','pid':7,'session':0,'trace_run_id':'7-run','ts':1}
    b={'process_instance_id':'8-bbb','pid':8,'session':0,'trace_run_id':'8-run','ts':1}
    root_a={**a,'type':'script_root','phase':'start','execution_context_id':1}
    root_b={**b,'type':'script_root','phase':'start','execution_context_id':1}
    request={'message_id':'7-aaa-1','message_sequence':1,'message_kind':'window_post_message',
        'source_pid':7,'source_process_instance_nonce':'aaa','source_trace_session':0,
        'source_execution_context_id':1,'source_async_context_id':0,
        'source_global_id':100,'target_global_id':200,'source_global_kind':'window','target_global_kind':'window'}
    reply={**request,'message_id':'8-bbb-1','source_pid':8,'source_process_instance_nonce':'bbb',
        'source_execution_context_id':3,'source_async_context_id':1,
        'source_global_id':200,'target_global_id':100}
    return [root_a,root_b,{**a,**request,'type':'message_send'},
        {**b,**request,'type':'message_receive','receiver_execution_context_id':2},
        {**b,'type':'async_schedule','async_context_id':1,'parent_execution_context_id':2,'async_cause':'promise_reaction'},
        {**b,'type':'async_resume','phase':'start','execution_context_id':3,'async_context_id':1,
         'schedule_session':0,'async_cause':'promise_reaction'},
        {**b,**reply,'type':'message_send'},
        {**a,**reply,'type':'message_receive','receiver_execution_context_id':2}]


class MessageGraphTests(unittest.TestCase):
    def test_same_local_ids_across_processes_remain_distinct(self):
        graph=MessageGraph(rows())
        self.assertEqual(len(graph.contexts),5)
        previous,hops=graph.incoming_for_send('8-bbb-1')
        self.assertEqual(previous,'7-aaa-1')
        self.assertEqual(hops[0]['parent_context'],['8-bbb',0,2])
        self.assertEqual(graph.incoming_for_send('7-aaa-1'),(None,[]))

    def test_file_and_timestamp_order_not_used(self):
        values=rows();expected=MessageGraph(values).incoming_for_send('8-bbb-1')
        for n,row in enumerate(values):row['ts']=100-n
        self.assertEqual(MessageGraph(list(reversed(values))).incoming_for_send('8-bbb-1'),expected)

    def test_published_hops_survive_json_without_type_changes(self):
        previous,hops=MessageGraph(rows()).incoming_for_send('8-bbb-1')
        published={'message_id':previous,'async_hops':hops}
        self.assertEqual(json.loads(json.dumps(published)),published)
        self.assertEqual(published['async_hops'][0]['resume_context'],['8-bbb',0,3])

    def test_duplicate_send_not_selected_arbitrarily(self):
        values=rows();values.append(copy.deepcopy(values[2]))
        with self.assertRaisesRegex(ValueError,'ambiguous'):MessageGraph(values)

    def test_missing_send_or_receive_is_rejected(self):
        for index in (2,3):
            values=rows();del values[index]
            with self.assertRaisesRegex(ValueError,'unmatched'):MessageGraph(values)

    def test_changed_receiver_endpoint_is_rejected(self):
        values=rows();values[3]['target_global_id']=999
        with self.assertRaisesRegex(ValueError,'endpoint'):MessageGraph(values)

    def test_token_spoofed_process_not_accepted(self):
        values=rows();values[2]['source_pid']=9;values[3]['source_pid']=9
        with self.assertRaisesRegex(ValueError,'emitting process'):MessageGraph(values)

    def test_message_id_not_consistent_with_nonce(self):
        values=rows();values[2]['message_id']=values[3]['message_id']='9-other-1'
        with self.assertRaisesRegex(ValueError,'token'):MessageGraph(values)

    def test_missing_schedule_not_joined_by_adjacent_timestamp(self):
        values=rows();del values[4]
        with self.assertRaisesRegex(ValueError,'schedule absent'):MessageGraph(values)

    def test_wrong_schedule_session_is_rejected(self):
        values=rows();values[5]['schedule_session']=1
        with self.assertRaisesRegex(ValueError,'schedule absent'):MessageGraph(values)

    def test_duplicate_context_is_ambiguous_even_with_equal_data(self):
        values=rows();values.append(copy.deepcopy(values[0]))
        with self.assertRaisesRegex(ValueError,'duplicate execution'):MessageGraph(values)

    def test_resume_cycle_not_reported_as_successful_lineage(self):
        values=rows();values[4]['parent_execution_context_id']=3
        graph=MessageGraph(values)
        with self.assertRaisesRegex(ValueError,'cycle'):graph.incoming_for_send('8-bbb-1')

    def test_source_context_must_be_declared(self):
        values=rows();values[6]['source_execution_context_id']=99;values[7]['source_execution_context_id']=99
        with self.assertRaisesRegex(ValueError,'undeclared'):MessageGraph(values)


if __name__=='__main__':unittest.main()
