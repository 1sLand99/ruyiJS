"""Canvas measurements use font baselines and the receiver's retained drawing state."""
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient

PROBE = Path(__file__).with_name('canvas_baselines_probe.js').read_text('utf8')
EXPECTED = json.loads(Path(__file__).with_name('canvas_baselines_firefox.json').read_text('utf8'))


class BaselineCases:
    def setUp(self):
        self.context = self.client()
        self.addCleanup(self.context.close)
        self.context.load_page('https://canvas.example.test/', '<!doctype html><body>')

    def compare(self, actual):
        self.assertEqual(set(actual), set(EXPECTED))
        for case, expected in EXPECTED.items():
            for index, (left, right) in enumerate(zip(actual[case], expected)):
                with self.subTest(case=case, metric=index):
                    if isinstance(right, (int, float)) and not isinstance(right, bool):
                        self.assertAlmostEqual(left, right, delta=1e-6)
                    else:
                        self.assertEqual(left, right)

    def test_native_firefox_measurements(self):
        self.compare(self.context.eval('(' + PROBE + ')(window)'))

    def test_native_firefox_measurements_in_iframe(self):
        actual = self.context.eval('''(()=>{
          const frame=document.createElement('iframe');document.body.append(frame);
          return frame.contentWindow.eval(''' + json.dumps('(' + PROBE + ')(window)') + ''');})()''')
        self.compare(actual)

    def test_saved_state_and_unmodified_method_identity(self):
        self.assertEqual(self.context.eval('''(()=>{
          const c=document.createElement('canvas').getContext('2d');c.font='16px Arial';
          const original=CanvasRenderingContext2D.prototype.measureText;
          c.textBaseline='hanging';const first=c.measureText('Hello');
          c.save();c.textBaseline='bottom';c.textAlign='right';
          const changed=c.measureText('Hello');c.restore();
          const restored=c.measureText('Hello');
          Object.defineProperty(c,'textBaseline',{get(){throw Error('public getter')}});
          const privateState=original.call(c,'Hello');
          return [first.hangingBaseline,changed.hangingBaseline>0,
            first.alphabeticBaseline===restored.alphabeticBaseline,
            restored.actualBoundingBoxLeft===first.actualBoundingBoxLeft,
            privateState.hangingBaseline===restored.hangingBaseline,
            c.measureText===original,typeof original];})()'''), [0,True,True,True,True,True,'function'])

    def test_borrowed_methods_read_receiver_state(self):
        self.assertEqual(self.context.eval('''(()=>{
          const frame=document.createElement('iframe');document.body.append(frame);
          const w=frame.contentWindow,c=w.document.createElement('canvas').getContext('2d');
          c.font='16px Arial';c.textBaseline='ideographic';
          const local=c.measureText('Hello');
          const borrowed=CanvasRenderingContext2D.prototype.measureText.call(c,'Hello');
          return [local.ideographicBaseline,borrowed.ideographicBaseline,
            local.hangingBaseline===borrowed.hangingBaseline,
            local instanceof w.TextMetrics,local instanceof TextMetrics,
            w.TextMetrics.prototype!==TextMetrics.prototype];})()'''), [0,0,True,True,False,True])

    def test_invalid_context_receiver(self):
        self.assertEqual(self.context.eval('''(()=>{
          try{CanvasRenderingContext2D.prototype.measureText.call({},'x')}
          catch(e){return e.name}})()'''), 'TypeError')

    def test_worker_offscreen_uses_font_baselines(self):
        self.context.eval('''globalThis.workerMetrics=null;
          globalThis.metricWorker=new Worker(URL.createObjectURL(new Blob([
            "const c=new OffscreenCanvas(20,20).getContext('2d');c.font='16px Arial';"+
            "c.textBaseline='ideographic';const m=c.measureText('Hello');"+
            "postMessage([m.hangingBaseline,m.alphabeticBaseline,m.ideographicBaseline]);"
          ],{type:'text/javascript'})));
          metricWorker.onmessage=e=>{workerMetrics=e.data;metricWorker.terminate()};undefined''')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            self.context.advance(50)
            result=self.context.eval('workerMetrics')
            if result is not None:
                self.assertEqual(result,[12.599990844726562,3,0])
                return
        self.fail('Worker baseline measurement did not complete')


class PythonBaselines(BaselineCases, unittest.TestCase):
    client=staticmethod(lambda:Context(shell=ROOT/'dist/js.exe',timeout=20))


class CBaselines(BaselineCases, unittest.TestCase):
    client=staticmethod(CClient)


if __name__=='__main__':
    unittest.main()
