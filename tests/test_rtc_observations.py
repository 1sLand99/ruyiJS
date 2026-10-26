"""ICE object evidence distinguishes repeated reads from distinct candidate events."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.trace_audit.rtc_observations import scan


class RtcObservationTests(unittest.TestCase):
    def rows(self):
        rows=[{'type':'trace_init','pid':1,'process_instance_id':'process-one'}]
        for event,candidate,text in [('e1','c1','candidate:0 1 UDP 1 host 9 typ host'),
                                     ('e2','c2','candidate:0 1 UDP 1 host 9 typ host')]:
            for _ in range(2):
                rows.append({'type':'get','interface':'RTCPeerConnectionIceEvent','member':'get candidate',
                             'thisObj':{'id':event},'value':'[Object RTCIceCandidate]','valueObj':{'id':candidate}})
                rows.append({'type':'get','interface':'RTCIceCandidate','member':'get candidate',
                             'thisObj':{'id':candidate},'value':text})
        return rows

    def scan_rows(self,rows):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'trace.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows),'utf-8')
            return scan(path)

    def test_equal_text_preserves_distinct_event_and_candidate_identity(self):
        report=self.scan_rows(self.rows())
        self.assertEqual(len(report['events']),2)
        self.assertEqual([x['getter_count'] for x in report['events']],[2,2])
        self.assertEqual(report['phases']['before_first_send'],{'host':2})
        self.assertEqual(report['anomalies'],[])
        self.assertTrue(all(x['missing_fields']==['sdpMid','sdpMLineIndex','usernameFragment'] for x in report['events']))

    def test_null_before_send_keeps_actual_send_boundary(self):
        rows=self.rows()+[{'type':'get','interface':'RTCPeerConnectionIceEvent','member':'get candidate',
                          'thisObj':{'id':'end'},'value':None,'valueObj':None},
                         {'type':'call','interface':'XMLHttpRequest','member':'send','seq':100}]
        report=self.scan_rows(rows)
        self.assertEqual(report['first_send']['seq'],100)
        self.assertEqual(report['phases']['before_first_send'],{'host':2,'null':1})

    def test_send_separates_observed_phases(self):
        rows=self.rows()
        rows.insert(5,{'type':'call','interface':'XMLHttpRequest','member':'send'})
        report=self.scan_rows(rows)
        self.assertEqual(report['phases'],{'before_first_send':{'host':1},'after_first_send':{'host':1}})

    def test_mutated_candidate_is_reported_as_anomaly(self):
        rows=self.rows();rows[4]['value']='different'
        report=self.scan_rows(rows)
        self.assertEqual(len(report['anomalies']),1)
        self.assertEqual(report['anomalies'][0]['reason'],'candidate field changed')


if __name__=='__main__':unittest.main()
