"""Coverage reports reject missing evidence and separate changed tier policy."""
import copy
import unittest

from tools.trace_audit.tier_summary import PREFERENCES, summarize


def fixture():
    rows=[];order=[(t,m) for t in ('normal','interpreter') for m in ('off','calls','detail')]
    for n in range(2):
        for tier,mode in order:
            count=0 if mode=='off' else 100 if tier=='interpreter' else 3
            rows.append({'round':n,'tier':tier,'mode':mode,'order':order,
                'preferences':{k:tier=='normal' for k in PREFERENCES},'surface':{'gets':0,'traps':0},
                'samples':[{'host_ms':101,'page_ms':10 if tier=='normal' else 30 if mode=='off' else 60,'checksum':42}],
                'capture':{'functions':{'measuredLeaf':count,'measuredBytes':count} if count else {},
                    'call_records':count*2,'writer_records':count*2,'dictionary_count':int(count>0),
                    'trace_bytes':count*100,'detail_bytes':count*68 if mode=='detail' else 0,
                    'detail':{'records':count*6} if mode=='detail' else {},
                    'writer_drops':{'io_errors':0},'caller_jit_gaps':0}})
    return {'rounds':2,'samples':1,'iterations':50,'warmup':50,'byte_calls':50,
            'known_calls':{'measuredLeaf':100,'measuredBytes':100},'runs':rows}


class TierSummaryTests(unittest.TestCase):
    def test_tier_and_capture_cost_separated(self):
        result=summarize(fixture())
        self.assertEqual(result['ratios']['tier_without_trace']['median'],3)
        self.assertEqual(result['ratios']['interpreter_calls_vs_off']['median'],2)
        self.assertTrue(result['fixture_calls_complete_in_interpreter'])
        self.assertFalse(result['opcode_measured'])
        self.assertFalse(result['zero_overhead_proven'])
        self.assertEqual(result['cells']['normal/calls']['coverage']['measuredLeaf'],[.03,.03])

    def test_wrong_preference_does_not_pass_as_interpreter(self):
        report=fixture();report['runs'][3]['preferences'][PREFERENCES[0]]=True
        with self.assertRaises(ValueError):summarize(report)

    def test_missing_or_duplicate_cell_rejected(self):
        report=fixture();report['runs'].pop()
        with self.assertRaises(ValueError):summarize(report)
        report=fixture();report['runs'].append(copy.deepcopy(report['runs'][0]))
        with self.assertRaises(ValueError):summarize(report)

    def test_budget_or_empty_capture_rejected(self):
        report=fixture();report['runs'][1]['capture']['writer_drops']['dropped_limit']=1
        with self.assertRaises(ValueError):summarize(report)
        report=fixture();report['runs'][1]['capture']['call_records']=0
        with self.assertRaises(ValueError):summarize(report)

    def test_known_call_denominator_validated(self):
        report=fixture();report['known_calls']['measuredLeaf']=99
        with self.assertRaises(ValueError):summarize(report)

    def test_surface_side_effects_and_values_rejected(self):
        report=fixture()
        for row in report['runs']:row['surface']['gets']=1
        with self.assertRaises(ValueError):summarize(report)
        report=fixture();report['runs'][1]['samples'][0]['checksum']=43
        with self.assertRaises(ValueError):summarize(report)

    def test_unreadable_detail_rejected(self):
        report=fixture();report['runs'][2]['capture']['detail']['unreadable']=1
        with self.assertRaises(ValueError):summarize(report)

    def test_zero_resolution_retained_without_infinite_ratio(self):
        report=fixture()
        for row in report['runs']:
            if row['tier']=='normal' and row['mode']=='off':row['samples'][0]['page_ms']=0
        result=summarize(report)
        self.assertIsNone(result['ratios']['tier_without_trace']['median'])
        self.assertEqual(result['cells']['normal/off']['zero_page_samples'],2)


if __name__=='__main__':unittest.main()
