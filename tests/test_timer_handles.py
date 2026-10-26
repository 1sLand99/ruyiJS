"""Window-local public handles over the existing Scheduling owner and C/Python paths."""
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context
from iframe_client import CClient

PROBE=Path(__file__).with_name('timer_handles_probe.js').read_text('utf-8')


class TimerCases:
    def setUp(self):
        self.c=self.client()
        self.addCleanup(self.c.close)
        self.c.configure_clock('logical',epoch_ms=1700000000000)
        self.c.load_page('https://timers.test/','<!doctype html><body><iframe></iframe><iframe></iframe>')
        self.c.eval("globalThis.a=document.querySelectorAll('iframe')[0].contentWindow;globalThis.b=document.querySelectorAll('iframe')[1].contentWindow;globalThis.events=[];undefined")

    def test_handle_values_match_firefox(self):
        result=self.c.eval('('+PROBE+')(window)')
        self.assertEqual(result['ids'],[1,2,1,1,1,3,2,4,3,5])
        self.assertEqual(result['shape'],['setTimeout',1,True,True,True,True])
        self.assertTrue(result['separateFunctions'])

    def test_cancel_isolated_by_global_and_family(self):
        self.c.eval("a.setTimeout(()=>events.push('a'),5);b.setTimeout(()=>events.push('b'),5);a.clearInterval(1);a.requestAnimationFrame(()=>events.push('frame'));a.clearTimeout(1);undefined")
        self.c.advance(40)
        self.assertEqual(self.c.eval('events'),['b','frame'])

    def test_borrowed_schedule_and_cancel_use_receiver(self):
        ids=self.c.eval("[a.setTimeout.call(b,function(){events.push(this===b?'b':'wrong')},5),a.setTimeout(()=>events.push('a'),5)]")
        self.assertEqual(ids,[1,1])
        self.c.eval('a.clearTimeout.call(b,1);undefined')
        self.c.advance(10)
        self.assertEqual(self.c.eval('events'),['a'])

    def test_callback_this_is_receiving_window(self):
        self.c.eval("a.setTimeout.call(b,function(){events.push(this===b)},0);undefined")
        self.c.advance(5)
        self.assertEqual(self.c.eval('events'),[True])

    def test_reentrant_conversion_and_failed_registration(self):
        result=self.c.eval('''(() => {
          let nested;
          try{a.setTimeout(()=>{},Symbol())}catch(e){}
          const outer=a.setTimeout(()=>{}, {valueOf(){nested=a.setTimeout(()=>{},60000);return 60000}});
          a.clearTimeout(nested);a.clearTimeout(outer);
          return [nested,outer,a.setTimeout(()=>{},60000)];
        })()''')
        self.assertEqual(result,[1,2,3])

    def test_self_cancel_and_internal_tasks(self):
        self.c.eval("a.eval(\"window.n=0;const id=setInterval(()=>{n++;clearTimeout(id)},0)\");window.onmessage=()=>events.push('message');postMessage('ok','*');for(let i=1;i<30;i++)clearTimeout(i);undefined")
        self.c.advance(40)
        self.assertEqual(self.c.eval('[a.n,events]'),[1,['message']])

    def test_retired_global_and_gc(self):
        self.c.eval("a.setTimeout(()=>events.push('retired'),5);b.setTimeout(()=>events.push('live'),5);document.querySelector('iframe').remove();undefined")
        if isinstance(self.c,Context):self.c.collect_garbage()
        else:self.c.call('collect')
        self.assertEqual(self.c.eval('a.setTimeout(()=>{},0)'),0)
        self.c.advance(10)
        self.assertEqual(self.c.eval('events'),['live'])

    def test_successor_document_starts_new_handle_space(self):
        self.assertEqual(self.c.eval('setTimeout(()=>{},60000)'),1)
        self.c.put_resource('https://timers.test/next','<script>window.first=setTimeout(()=>{},60000)</script>')
        self.c.eval("location.assign('/next');undefined")
        self.c.advance(30)
        self.assertEqual(self.c.eval('[first,setInterval(()=>{},60000)]'),[1,2])

    def test_bad_receiver_and_callback_realm(self):
        self.assertEqual(self.c.eval('''(() => {
          let error;
          try {a.setTimeout.call({},()=>{},0)} catch(e) {error=e.name}
          a.callback=function(){parent.events.push(this===b)};
          const handle=b.setTimeout(a.callback,0);
          return [error,handle];
        })()'''),['TypeError',1])
        self.c.advance(5)
        self.assertEqual(self.c.eval('events'),[True])

    def test_worker_uses_own_timer_counter(self):
        self.c.put_resource('https://timers.test/worker.js',
            "const first=setTimeout(()=>{},60000),second=setInterval(()=>{},60000);clearInterval(first);clearTimeout(second);postMessage([first,second])",
            headers=[['Content-Type','text/javascript']])
        self.c.eval("window.workerResult=null;window.worker=new Worker('/worker.js');worker.onmessage=e=>workerResult=e.data;undefined")
        deadline=time.monotonic()+5
        result=None
        while time.monotonic()<deadline:
            self.c.advance(10)
            result=self.c.eval('workerResult')
            if result is not None:break
            time.sleep(.01)
        self.assertEqual(result,[1,2])
        self.c.eval('worker.terminate();undefined')

    def test_animation_and_idle_cancel_do_not_touch_timers(self):
        result=self.c.eval('''(() => {
          const frame=a.requestAnimationFrame(()=>events.push('frame'));
          const timer=a.setTimeout(()=>events.push('timer'),0);
          const idle=a.requestIdleCallback(()=>events.push('idle'));
          a.cancelAnimationFrame(timer);a.cancelIdleCallback(timer);
          return [frame,timer,idle];
        })()''')
        self.assertEqual(result,[1,1,1])
        self.c.advance(40)
        self.assertEqual(self.c.eval('events'),['timer'])

    def test_borrowed_raf_has_receiver_namespace(self):
        result=self.c.eval('''(() => {
          const first=a.requestAnimationFrame.call(b,()=>events.push('b'));
          const second=a.requestAnimationFrame(()=>events.push('a'));
          a.cancelAnimationFrame.call(b,first);
          return [first,second];
        })()''')
        self.assertEqual(result,[1,1])
        self.c.advance(40)
        self.assertEqual(self.c.eval('events'),['a'])


class PythonTimerHandles(TimerCases,unittest.TestCase):
    client=staticmethod(lambda:Context(shell=ROOT/'dist/js.exe'))


class CTimerHandles(TimerCases,unittest.TestCase):
    client=staticmethod(CClient)


if __name__=='__main__':unittest.main()
