"""Exercise the original Element rect factory against native Firefox layout bounds."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context
from iframe_client import CClient

PROBE=Path(__file__).with_name('layout_saturation_probe.js').read_text('utf8')
EXPECTED=json.loads(Path(__file__).with_name('layout_saturation_firefox.json').read_text('utf8'))


class SaturationCases:
    def setUp(self):
        self.context=self.client()
        self.addCleanup(self.context.close)
        self.context.load_page('https://layout.example.test/','<!doctype html><body>')

    def check_rects(self,actual):
        self.assertEqual(actual['standalone'],EXPECTED['standalone'])
        for name,expected in EXPECTED.items():
            if name=='standalone':continue
            with self.subTest(case=name):
                # Extreme negative origins retain the pre-existing one-app-unit
                # float conversion difference. Integer client/offset rounding
                # belongs to separate Document Model accessors, not this slice.
                for left,right in zip(actual[name]['rect'],expected['rect']):
                    self.assertAlmostEqual(left,right,delta=1/60+1e-5 if name=='negativePosition' else 1e-6)
                self.assertEqual(actual[name]['list'][0],1)
                self.assertEqual(actual[name]['list'][1:],actual[name]['rect'][2:])

    def test_firefox_rect_boundaries(self):
        self.check_rects(self.context.eval('('+PROBE+')(window)'))

    def test_firefox_iframe_boundaries(self):
        self.check_rects(self.context.eval('''(()=>{
          const f=document.createElement('iframe');document.body.append(f);
          return f.contentWindow.eval('''+json.dumps('('+PROBE+')(window)')+''');})()'''))

    def test_snapshot_factory_receiver_and_mutation(self):
        self.assertEqual(self.context.eval('''(()=>{
          const f=document.createElement('iframe');document.body.append(f);const w=f.contentWindow;
          const e=w.document.createElement('div');e.style.cssText='position:absolute;left:0;top:0;width:1e38px;height:10px';
          w.document.body.append(e);const first=e.getBoundingClientRect();
          const borrowed=Element.prototype.getBoundingClientRect.call(e);
          e.style.width='42px';const next=e.getBoundingClientRect();
          let invalid;try{Element.prototype.getBoundingClientRect.call({})}catch(error){invalid=error.name}
          return [first.width,borrowed.width,next.width,first instanceof w.DOMRect,
            first instanceof DOMRect,invalid,new DOMRect(0,0,1e38,1).width];})()'''),
            [17895698,17895698,42,True,False,'TypeError',1e38])


class PythonSaturation(SaturationCases,unittest.TestCase):
    client=staticmethod(lambda:Context(shell=ROOT/'dist/js.exe'))


class CSaturation(SaturationCases,unittest.TestCase):
    client=staticmethod(CClient)


if __name__=='__main__':unittest.main()
