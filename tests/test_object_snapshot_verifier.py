"""Snapshot evidence rejects empty captures and hidden page-side effects."""
import unittest
from tools.trace_audit.verify_object_snapshots import verify


class SnapshotVerifierTests(unittest.TestCase):
    def test_no_capture_does_not_prove_nonperturbing_capture(self):
        report={'capture_present':False,'page_results_equal':True,
                'modes':{'off':{'page':{'gets':0,'traps':0,'jsonCalls':0,'descriptorsEqual':True}}}}
        with self.assertRaises(AssertionError):verify(report)

    def test_page_side_effect_fails_even_when_modes_match(self):
        report={'capture_present':True,'page_results_equal':True,
                'modes':{'off':{'page':{'gets':1,'traps':0,'jsonCalls':0,'descriptorsEqual':True}}}}
        with self.assertRaises(AssertionError):verify(report)


if __name__=='__main__':unittest.main()
