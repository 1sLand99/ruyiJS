"""RTC gathering creation order and completion through real Python/C adapters."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context
from iframe_client import CClient

SCRIPT=(ROOT/'tests/rtc_gathering_fixture.js').read_text('utf-8')
HTML='<!doctype html><script>'+SCRIPT+'</script>'
ORDER={'dataFirst':[2,0,1],'mediaFirst':[0,1,2],'dataMiddle':[0,2,1],
       'mediaOnly':[0,1],'dataOnly':[0],'legacyDataFirst':[2,0,1],'closedData':[1,0]}


class RtcGatheringCases:
    def setUp(self):
        self.c=self.client()
        self.addCleanup(self.c.close)
        self.c.configure_clock('logical',epoch_ms=1700000000000)
        self.c.put_resource('https://rtc.test/frame',HTML,headers=[['Content-Type','text/html']])
        self.c.load_page('https://rtc.test/',HTML+'<iframe src="/frame"></iframe>')
        self.c.eval('window.child=document.querySelector("iframe").contentWindow;undefined')

    def assert_results(self,results):
        self.assertEqual(set(results),set(ORDER))
        for name,order in ORDER.items():
            row=results[name]
            with self.subTest(case=name):
                self.assertNotIn('error',row)
                self.assertTrue(row['done'] and row['setLocalResolved'])
                self.assertEqual([x['index'] for x in row['ends']],order)
                self.assertEqual([x['mid'] for x in row['ends']],[str(i) for i in order])
                self.assertEqual(row['events'],['state:gathering']+
                    ['end:'+str(i)+':gathering' for i in order]+['state:complete','null:complete'])
                actual=list(dict.fromkeys(x['index'] for x in row['candidates']))
                self.assertEqual(actual,order)
                for candidate in row['candidates']+row['ends']:
                    self.assertTrue(all(candidate[k] is True for k in
                        ('sameObject','prototype','eventPrototype','trusted','target','ufrag')))
                self.assertEqual(row['mids'],[str(i) for i in range(len(order))])
                self.assertEqual(row['bundle'],'a=group:BUNDLE '+' '.join(row['mids']))

    def test_main_creation_order_and_completion_match_firefox(self):
        self.c.eval('startRtcCases()');self.c.advance(2000)
        self.assert_results(self.c.eval('rtcResults'))

    def test_frame_factory_and_gc_preserve_peer_specific_order(self):
        self.c.eval('child.startRtcCases()')
        if isinstance(self.c,Context): self.c.collect_garbage()
        else:self.c.call('collect')
        self.c.advance(2000)
        self.assert_results(self.c.eval('child.rtcResults'))

    def test_close_in_candidate_handler_cancels_remaining_delivery(self):
        self.c.eval('''window.edge=[];window.pc=new RTCPeerConnection();pc.createDataChannel('');
          pc.onicecandidate=e=>{edge.push(e.candidate===null?'null':'candidate');pc.close()};
          pc.createOffer().then(o=>pc.setLocalDescription(o));undefined''')
        self.c.advance(2000)
        self.assertEqual(self.c.eval('edge'),['candidate'])
        self.assertEqual(self.c.eval('pc.signalingState'),'closed')

    def test_close_in_complete_handler_suppresses_later_null(self):
        self.c.eval('''window.edge=[];window.pc=new RTCPeerConnection();pc.createDataChannel('');
          pc.onicecandidate=e=>{if(e.candidate===null)edge.push('null')};
          pc.onicegatheringstatechange=()=>{if(pc.iceGatheringState==='complete'){edge.push('complete');pc.close()}};
          pc.createOffer().then(o=>pc.setLocalDescription(o));undefined''')
        self.c.advance(2000)
        self.assertEqual(self.c.eval('edge'),['complete'])

    def test_failed_channel_creation_does_not_allocate_a_transport(self):
        self.c.eval('''window.pc=new RTCPeerConnection();window.offerResult=null;
          try{pc.createDataChannel('bad',{negotiated:true})}catch(e){}
          pc.addTransceiver('audio');pc.createOffer().then(o=>offerResult=o.sdp);undefined''')
        self.c.advance(20)
        offer=self.c.eval('offerResult')
        self.assertIn('m=audio',offer)
        self.assertNotIn('m=application',offer)

    def test_methods_keep_native_descriptors_and_receiver_errors(self):
        result=self.c.eval('''(() => {const d=Object.getOwnPropertyDescriptor(RTCPeerConnection.prototype,'createDataChannel');
          let errors=0;for(const receiver of [{},new Proxy(new RTCPeerConnection(),{})]){
            try{d.value.call(receiver,'bad')}catch(e){if(e instanceof TypeError)errors++}}
          return [d.writable,d.enumerable,d.configurable,d.value.length,
            d.value.toString().includes('[native code]'),errors]})()''')
        self.assertEqual(result,[True,True,True,1,True,2])


class PythonRtcGathering(RtcGatheringCases,unittest.TestCase):
    client=staticmethod(lambda:Context(shell=ROOT/'dist/js.exe'))


class CRtcGathering(RtcGatheringCases,unittest.TestCase):
    client=staticmethod(CClient)


if __name__=='__main__':unittest.main()
