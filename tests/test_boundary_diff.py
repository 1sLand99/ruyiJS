"""Primitive comparison keeps ambiguous occurrences out of claimed alignments."""
import unittest
from tools.trace_audit.boundary_diff import diff,primitive


class BoundaryDiffTests(unittest.TestCase):
    def test_ambiguous_occurrences_are_not_compared(self):
        key=('get','Window','x',1,2,None)
        row={'line':1,'seq':1,'value':3}
        report=diff({key:[row,row]},{key:[row]})
        self.assertEqual(report['counts']['ambiguous_occurrence_keys'],1)
        self.assertEqual(report['differences'],[])
        self.assertEqual(report['counts'].get('compared_values',0),0)

    def test_object_encodings_are_not_primitive_semantics(self):
        self.assertFalse(primitive('[Object Window]'))
        self.assertFalse(primitive({'type':'object','class':'Window'}))
        self.assertTrue(primitive('ordinary text'))
        self.assertTrue(primitive(None))

    def test_value_differences_keep_both_locations(self):
        key=('call','Window','setTimeout',1,2,'[]')
        report=diff({key:[{'line':7,'seq':1,'value':1}]},
                    {key:[{'line':9,'seq':2,'value':2}]})
        self.assertEqual(report['counts']['different_values'],1)
        self.assertEqual(report['differences'][0]['reference']['line'],7)
        self.assertEqual(report['differences'][0]['replay']['line'],9)


if __name__=='__main__':unittest.main()
