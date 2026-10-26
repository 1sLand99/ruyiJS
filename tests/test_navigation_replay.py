"""Recorded navigation inputs flow through the original native Performance owner."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context, JSError
from iframe_client import CClient

URL = 'https://navigation.test/frame'
SCRIPT = '''window.originalPerformance=performance;
window.entry=performance.getEntriesByType('navigation')[0];
window.readNav=()=>[entry.responseEnd,entry.transferSize,entry.encodedBodySize,entry.duration,entry.loadEventEnd];
window.before=readNav();window.delivered=[];
new PerformanceObserver(list=>delivered.push([list.getEntries()[0]===entry,...readNav()]))
 .observe({entryTypes:['navigation']});'''
HTML = '<!doctype html><script>' + SCRIPT + '</script>'


class NavigationReplayCases:
    def setUp(self):
        self.c = self.client()
        self.addCleanup(self.c.close)
        self.c.configure_clock('logical', epoch_ms=1700000000000)

    def configure(self, documents):
        if isinstance(self.c, Context): return self.c.configure_navigation_replay(documents)
        return self.c.call('event_loop', action='configure_navigation_replay', documents=documents)

    def status(self):
        if isinstance(self.c, Context): return self.c.navigation_replay_status()
        return self.c.call('event_loop', action='navigation_replay_status')

    def plan(self, url=URL, **fields):
        return {'url': url, 'fields': fields or {'responseEnd': 69, 'transferSize': 0,
            'encodedBodySize': 0, 'loadEventEnd': 249}}

    def load(self, count=1):
        self.c.put_resource(URL, HTML, headers=[['Content-Type', 'text/html']])
        self.c.load_page('https://navigation.test/', '<!doctype html>' + '<iframe src="/frame"></iframe>' * count)
        self.c.advance(10)
        self.c.eval('window.child=document.querySelector("iframe").contentWindow;undefined')

    def test_initial_and_completed_fields_share_native_identity(self):
        self.configure([self.plan()]); self.load()
        self.assertEqual(self.c.eval('child.before'), [69, 0, 0, 0, 0])
        self.assertEqual(self.c.eval('child.readNav()'), [69, 0, 0, 249, 249])
        self.assertEqual(self.c.eval('child.delivered'), [[True, 69, 0, 0, 249, 249]])
        result = self.c.eval('''(() => {const c=child,e=c.entry,p=c.originalPerformance;
          return [e.toJSON().duration,e.toJSON().responseEnd,p.timing.loadEventEnd-p.timeOrigin,
            p.timing.responseEnd-p.timeOrigin,Object.getPrototypeOf(e)===c.PerformanceNavigationTiming.prototype,
            p.getEntriesByType('navigation')[0]===e,typeof configure_navigation_replay]})()''')
        self.assertEqual(result, [249, 69, 249, 69, True, True, 'undefined'])
        self.assertTrue(self.status()[0]['bound'])

    def test_partial_fields_preserve_other_measurements_and_clock(self):
        self.configure([self.plan(requestStart=0, encodedBodySize=7)])
        self.load()
        data = self.c.eval('[child.entry.encodedBodySize,child.entry.decodedBodySize,child.entry.transferSize,'
                           'child.entry.duration,child.entry.fetchStart,Date.now()]')
        self.assertEqual(data, [7, len(HTML.encode()), len(HTML.encode()) + 300, 0, 0, 1700000000010])

    def test_occurrences_and_unknown_url_isolation(self):
        self.configure([self.plan(responseEnd=11), self.plan(responseEnd=22),
                        self.plan(URL+'?unloaded', responseEnd=99)])
        self.load(2)
        self.assertEqual(self.c.eval('Array.from(document.querySelectorAll("iframe"),f=>f.contentWindow.entry.responseEnd)'), [11,22])
        self.assertEqual([r['bound'] for r in self.status()], [True,True,False])
        self.assertEqual(self.c.eval('performance.getEntriesByType("navigation")[0].responseEnd'), 0)

    def test_invalid_configuration_preserves_previous_plan(self):
        self.configure([self.plan()])
        bad = [self.plan(responseEnd=-1), self.plan(encodedBodySize=1.5), self.plan(responseEnd=True),
               self.plan(responseEnd='69'), self.plan(responseStart=5,responseEnd=4),
               self.plan(responseEnd=70,loadEventEnd=69), self.plan(URL+'#fragment', responseEnd=1),
               self.plan('relative', responseEnd=1), self.plan(unknown=1), {'url':URL,'fields':{}}]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(JSError): self.configure([item])
        with self.assertRaises(JSError): self.configure([self.plan()]*33)
        self.load()
        self.assertEqual(self.c.eval('child.readNav()'), [69,0,0,249,249])

    def test_execution_freeze_and_main_document_binding(self):
        self.configure([self.plan('https://navigation.test/', responseEnd=3,loadEventEnd=10)])
        self.c.load_page('https://navigation.test/', HTML)
        self.c.advance(0)
        self.assertEqual(self.c.eval('readNav()[0]'), 3)
        with self.assertRaises(JSError): self.configure([])
        self.assertEqual(self.c.eval('entry.duration'), 10)

    def test_global_overwrite_and_gc_keep_original_record(self):
        self.configure([self.plan()]); self.load()
        self.c.eval('child.performance={};child.PerformanceNavigationTiming=function(){};undefined')
        if isinstance(self.c, Context): self.c.collect_garbage()
        else: self.c.call('collect')
        self.assertEqual(self.c.eval('child.readNav()'), [69,0,0,249,249])

    def test_no_configuration_leaves_measured_values(self):
        self.load()
        self.assertEqual(self.c.eval('child.readNav()'), [0,len(HTML.encode())+300,len(HTML.encode()),0,0])
        self.assertEqual(self.status(), [])

    def test_known_document_exhaustion_is_an_error(self):
        main='https://navigation.test/'
        self.configure([self.plan(main, responseEnd=1)])
        self.c.load_page(main, HTML)
        self.c.put_resource(main, HTML, headers=[['Content-Type','text/html']])
        self.c.eval('location.reload();undefined')
        with self.assertRaisesRegex(JSError, 'occurrences exhausted'):
            self.c.advance(10)
        self.assertEqual(len(self.status()), 1)
        self.assertTrue(self.status()[0]['bound'])

    def test_request_start_does_not_overwrite_fetch_start(self):
        self.configure([self.plan(requestStart=5,responseEnd=69,loadEventEnd=100)])
        self.load()
        self.assertEqual(self.c.eval('[child.entry.requestStart,child.entry.fetchStart,'
            'child.originalPerformance.timing.fetchStart-child.originalPerformance.timeOrigin]'), [5,0,0])


class PythonNavigationReplay(NavigationReplayCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT/'dist/js.exe'))


class CNavigationReplay(NavigationReplayCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__': unittest.main()
