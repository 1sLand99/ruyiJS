"""Cost summaries reject missing evidence and retain low-coverage qualifications."""
import copy
import unittest

from tools.trace_audit.cost_summary import summarize


def fixture():
    rows=[]
    for repetition in range(2):
        for mode in ('off','core','calls','detail'):
            calls=mode in ('calls','detail')
            rows.append({'round':repetition,'mode':mode,'surface':{'getter_calls':0},
                'samples':[{'page':{'checksum':[42,7]},'process':{'wall_ms':10 if mode=='off' else 12,
                    'cpu_ms':2,'peak_sum_rss_bytes':1024,'sample_errors':0}}],
                'capture':{'dict_errors':[],'stats':[{'recorded':8}] if calls else [],
                    'call_records':8 if calls else 0,'leaf_records':3 if calls else 0,
                    'bytes_records':2 if calls else 0,'trace_bytes':0 if mode=='off' else 500,
                    'detail_bytes':100 if mode=='detail' else 0}})
    return {'rounds':2,'samples_per_run':1,'runs':rows,'known_calls_per_process':{'leaf':100,'bytes':20}}


class CaptureCostTests(unittest.TestCase):
    def test_ratios_do_not_hide_coverage(self):
        result=summarize(fixture())
        self.assertEqual(result['paired_ratios']['calls']['wall_ms']['median'],1.2)
        self.assertEqual(result['modes']['calls']['leaf_coverage'],[.03,.03])
        self.assertFalse(result['full_call_coverage'])
        self.assertFalse(result['zero_overhead_proven'])

    def test_incomplete_or_duplicate_pairs_rejected(self):
        for change in ('missing','duplicate'):
            report=fixture()
            if change=='missing':report['runs'].pop()
            else:report['runs'].append(copy.deepcopy(report['runs'][0]))
            with self.assertRaises(ValueError):summarize(report)

    def test_empty_trace_cannot_pass_by_matching_page_results(self):
        report=fixture();report['runs'][2]['capture']['call_records']=0
        with self.assertRaises(ValueError):summarize(report)
        report=fixture();report['runs'][1]['capture']['trace_bytes']=0
        with self.assertRaises(ValueError):summarize(report)

    def test_writer_binary_count_mismatch(self):
        report=fixture();report['runs'][2]['capture']['stats'][0]['recorded']=7
        with self.assertRaises(ValueError):summarize(report)

    def test_changed_checksum_or_surface(self):
        report=fixture();report['runs'][1]['samples'][0]['page']['checksum']=[1]
        with self.assertRaises(ValueError):summarize(report)
        report=fixture();report['runs'][1]['surface']['getter_calls']=1
        with self.assertRaises(ValueError):summarize(report)

    def test_invalid_timing_not_used_in_ratios(self):
        for bad in (0,-1,float('nan'),True):
            report=fixture();report['runs'][0]['samples'][0]['process']['wall_ms']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):summarize(report)


if __name__=='__main__':unittest.main()
