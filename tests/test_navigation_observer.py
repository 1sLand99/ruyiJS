"""Native navigation entry identity, lifecycle notification and Python/C parity."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient

SCRIPT = (ROOT / 'tests/navigation_observer_fixture.js').read_text('utf-8')
FRAME = '<!doctype html><script>' + SCRIPT + '</script>'


class NavigationObserverCases:
    def setUp(self):
        self.c = self.client()
        self.addCleanup(self.c.close)
        self.c.configure_clock('logical', epoch_ms=1700000000000)
        self.c.put_resource('https://navigation.test/frame', FRAME, headers=[['Content-Type', 'text/html']])
        self.c.load_page('https://navigation.test/', FRAME + '<iframe src="/frame"></iframe>')
        self.c.advance(10)
        self.c.eval('globalThis.child=document.querySelector("iframe").contentWindow;undefined')

    def collect(self):
        if isinstance(self.c, Context):
            self.c.collect_garbage()
        else:
            self.c.call('collect')

    def assert_summary(self, result):
        self.assertEqual(result['events'], ['load', 'navigation'])
        self.assertEqual(result['initial'], ['navigation', 0, 0])
        self.assertEqual(result['beforeLoadTake'], 1)
        self.assertEqual(result['lateTake'], 1)
        self.assertTrue(result['lateTakenIdentity'])
        self.assertEqual(result['measures'], ['measure'])
        for name in ('navigation', 'buffered', 'late'):
            self.assertEqual(len(result[name]), 1, name)
            row = result[name][0]
            self.assertEqual(row['initiator'], 'navigation')
            self.assertTrue(all(v is True for k, v in row.items() if k != 'initiator'), row)

    def test_production_delivery_and_buffered_identity_match_firefox(self):
        self.c.eval('startLateNavigationObserver();child.startLateNavigationObserver();undefined')
        self.c.advance(10)
        for result in self.c.eval('[navResult,child.navResult]'):
            self.assert_summary(result)

    def test_logical_zero_completion_not_lost_or_repeated(self):
        self.assertEqual(self.c.eval('[performance.getEntriesByType("navigation")[0].duration,'
                                     'performance.getEntriesByType("navigation")[0].loadEventEnd]'), [0, 0])
        self.c.advance(100)
        self.assertEqual(self.c.eval('[navResult.navigation.length,child.navResult.navigation.length]'), [1, 1])

    def test_duration_follows_nonzero_completion(self):
        other = self.client()
        try:
            if isinstance(other, Context):
                other.configure_clock('system')
            else:
                other.call('event_loop', action='configure', mode='system')
            other.put_resource('https://navigation.test/delayed', '<!doctype html><script>'
                'window.firstEntry=performance.getEntriesByType("navigation")[0];'
                'const t=performance.now();while(performance.now()-t<5){};'
                '</script>', headers=[['Content-Type', 'text/html']])
            other.load_page('https://navigation.test/', '<iframe src="/delayed"></iframe>')
            value = other.eval('''(() => {const e=document.querySelector('iframe').contentWindow.firstEntry;
              return [e.duration>0,e.duration===e.loadEventEnd,e.toJSON().duration===e.loadEventEnd]})()''')
            self.assertEqual(value, [True, True, True])
        finally:
            other.close()

    def test_borrowed_observe_routes_to_observer_realm(self):
        self.c.eval('''globalThis.borrowed=[];globalThis.foreign=new child.PerformanceObserver(function(list,o){
          borrowed.push([o===foreign,this===foreign,Object.getPrototypeOf(list)===child.PerformanceObserverEntryList.prototype,
            list.getEntriesByType('navigation')[0]===child.performance.getEntriesByType('navigation')[0]])});
          PerformanceObserver.prototype.observe.call(foreign,{type:'navigation',buffered:true});undefined''')
        self.collect()
        self.c.advance(10)
        self.assertEqual(self.c.eval('borrowed'), [[True, True, True, True]])

    def test_disconnect_retains_records_without_delivering(self):
        value = self.c.eval('''(() => {window.disconnectedCalls=0;
          window.disconnected=new PerformanceObserver(()=>disconnectedCalls++);
          disconnected.observe({type:'navigation',buffered:true});disconnected.disconnect();
          return [disconnected.takeRecords().length,disconnected.takeRecords().length]})()''')
        self.assertEqual(value, [1, 0])
        self.c.advance(10)
        self.assertEqual(self.c.eval('disconnectedCalls'), 0)

    def test_overridden_globals_and_queries_do_not_change_buffer_source(self):
        self.c.eval('''globalThis.overrideResult=[];const originalPerformance=performance;
          const originalQuery=performance.getEntriesByType;const originalCtor=PerformanceObserver;
          const originalEntry=originalQuery.call(originalPerformance,'navigation')[0];
          const observer=new originalCtor(list=>overrideResult.push(list.getEntriesByType('navigation')[0]===originalEntry));
          window.performance={};window.PerformanceObserver=function(){throw 1};
          originalPerformance.getEntriesByType=()=>{throw 2};
          observer.observe({type:'navigation',buffered:true});undefined''')
        self.collect()
        self.c.advance(10)
        self.assertEqual(self.c.eval('overrideResult'), [True])

    def test_invalid_receivers_and_original_descriptors(self):
        value = self.c.eval('''(() => {let invalid=0;
          for(const receiver of [{},new Proxy(navObserver,{})]){
            try{PerformanceObserver.prototype.observe.call(receiver,{type:'navigation',buffered:true})}
            catch(e){if(e instanceof TypeError)invalid++}}
          const d=Object.getOwnPropertyDescriptor(PerformanceObserver.prototype,'observe');
          return [invalid,d.writable,d.enumerable,d.configurable,d.value.length,
            d.value.toString().includes('[native code]'),
            Object.getPrototypeOf(PerformanceNavigationTiming.prototype)===PerformanceResourceTiming.prototype]})()''')
        self.assertEqual(value, [2, True, True, True, 0, True, True])


class PythonNavigationObserver(NavigationObserverCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CNavigationObserver(NavigationObserverCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__':
    unittest.main()
