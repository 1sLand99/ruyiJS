"""Causal evidence uses explicit identities, not timestamp/file adjacency guesses."""
import copy
import unittest

from tools.trace_audit.async_evidence import analyze


def fixture():
    base={'process_instance_id':'7-abc','trace_run_id':'7-run','pid':7,'session':0,'file':'a.jsonl'}
    rows=[{'type':'script_root','phase':'start','execution_context_id':1},
        {'type':'async_schedule','async_context_id':2,'parent_execution_context_id':1,'async_cause':'set_timeout'},
        {'type':'async_resume','phase':'start','async_context_id':2,'execution_context_id':3,
         'schedule_session':0,'async_cause':'set_timeout'},
        {'type':'call','interface':'Element','member':'setAttribute','args':['data-causal-proof','timeout'],
         'execution_context_id':3,'async_context_id':2,'trace_session':0},
        {'type':'message_send','message_id':'7-abc-1','message_kind':'window_post_message',
         'source_pid':7,'source_process_instance_nonce':'abc','source_trace_session':0,'source_execution_context_id':3},
        {'type':'message_receive','message_id':'7-abc-1','message_kind':'window_post_message',
         'source_pid':7,'source_process_instance_nonce':'abc','source_trace_session':0,
         'source_execution_context_id':3,'receiver_execution_context_id':4},
        {'type':'domtrace_writer_stats','io_errors':0,'dropped_full':0}]
    return [{**base,**row,'file_line':n,'seq':n,'ts':1000} for n,row in enumerate(rows,1)]


class AsyncEvidenceTests(unittest.TestCase):
    def test_explicit_ids_with_equal_timestamps(self):
        proof=analyze(fixture())
        self.assertEqual(proof['gaps'],[])
        self.assertEqual(len(proof['edges']),2)
        self.assertEqual(proof['markers'][0]['cause'],'set_timeout')

    def test_missing_context_not_assigned_to_nearest_row(self):
        rows=fixture();del rows[3]['execution_context_id']
        proof=analyze(rows)
        self.assertFalse(proof['markers'][0]['context_declared'])
        self.assertIn('marker_context_missing',[r['kind'] for r in proof['gaps']])

    def test_reused_process_and_session_ids_do_not_join(self):
        for change in ({'process_instance_id':'7-other'},{'schedule_session':1}):
            rows=fixture();rows[2].update(change)
            proof=analyze(rows)
            self.assertIn('missing_or_ambiguous_schedule',[r['kind'] for r in proof['gaps']])

    def test_duplicate_schedule_is_not_arbitrarily_selected(self):
        rows=fixture();rows.append(copy.deepcopy(rows[1]))
        proof=analyze(rows)
        self.assertEqual(sum(r['relation']=='schedule_to_resume' for r in proof['edges']),0)
        self.assertIn('missing_or_ambiguous_schedule',[r['kind'] for r in proof['gaps']])

    def test_message_identity_spans_different_receiver_process(self):
        rows=fixture();rows[5].update(process_instance_id='8-def',trace_run_id='8-run',pid=8,file='b.jsonl')
        self.assertEqual(analyze(rows)['gaps'],[])

    def test_undeclared_message_source_detected(self):
        rows=fixture();rows[4]['source_execution_context_id']=999
        self.assertIn('undeclared_message_source',[r['kind'] for r in analyze(rows)['gaps']])

    def test_duplicate_message_sender_rejected(self):
        rows=fixture();rows.append(copy.deepcopy(rows[4]))
        proof=analyze(rows)
        self.assertEqual(sum(r['relation']=='send_to_receive' for r in proof['edges']),0)
        self.assertIn('missing_or_ambiguous_send',[r['kind'] for r in proof['gaps']])

    def test_wrong_cause_and_missing_parent_are_visible(self):
        rows=fixture();rows[2]['async_cause']='queue_microtask';rows[1]['parent_execution_context_id']=99
        kinds=[r['kind'] for r in analyze(rows)['gaps']]
        self.assertIn('schedule_resume_cause_mismatch',kinds)
        self.assertIn('undeclared_schedule_parent',kinds)

    def test_writer_loss_retained(self):
        rows=fixture();rows[-1]['dropped_full']=2
        self.assertEqual(analyze(rows)['writer_losses']['dropped_full'],2)

    def test_marker_context_with_wrong_async_id_rejected(self):
        rows=fixture();rows[3]['async_context_id']=99
        self.assertIn('marker_async_identity_mismatch',[r['kind'] for r in analyze(rows)['gaps']])

    def test_message_source_identity_must_survive_transport(self):
        rows=fixture();rows[5]['source_execution_context_id']=99
        self.assertIn('message_source_field_mismatch',[r['kind'] for r in analyze(rows)['gaps']])


if __name__=='__main__':unittest.main()
