"""Explicit recorded parser-async order through the real load_page path."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context, JSError
from iframe_client import CClient

BASE = 'https://order.test/'
HTML = '''<!doctype html><script>window.events=[];</script>
<script async src="a.js"></script><script async src="b.js"></script>
<script>events.push('inline:'+document.readyState);</script>
<script defer src="d.js"></script>'''


class OrderCases:
    def setUp(self):
        self.c = self.client()
        self.addCleanup(self.c.close)
        self.c.configure_clock('logical', epoch_ms=1700000000000)
        self.c.put_resource(BASE+'a.js', "events.push('a:'+document.readyState);setTimeout(()=>events.push('timer'),0)")
        self.c.put_resource(BASE+'b.js', "events.push('b:'+document.readyState+':'+document.currentScript.src)")
        self.c.put_resource(BASE+'d.js', "events.push('defer:'+document.readyState)")

    def load(self, order=None, html=HTML):
        if isinstance(self.c, Context):
            return self.c.load_page(BASE, html, replay_async_scripts=order)
        args = {} if order is None else {'replay_async_scripts':order}
        return self.c.call('page', action='load', url=BASE, html=html, **args)

    def test_explicit_order_and_due_timer(self):
        self.load([BASE+'a.js', BASE+'b.js'])
        self.assertEqual(self.c.eval('events'), ['inline:loading','a:interactive','timer',
            'b:interactive:'+BASE+'b.js','defer:interactive'])
        self.assertEqual(self.c.eval('document.readyState'), 'complete')

    def test_reverse_order_and_no_global_hook(self):
        self.load([BASE+'b.js', BASE+'a.js'])
        self.assertEqual(self.c.eval('events'), ['inline:loading','b:interactive:'+BASE+'b.js',
            'a:interactive','timer','defer:interactive'])
        self.assertEqual(self.c.eval('typeof replay_async_scripts'), 'undefined')

    def test_absent_plan_preserves_default_order(self):
        self.load()
        self.assertEqual(self.c.eval('events.slice(0,3)'), ['a:loading','b:loading:'+BASE+'b.js','inline:loading'])

    def test_invalid_and_unmatched_plans_fail(self):
        for order in ('wrong', [''], ['a.js'], [BASE+'a.js']*2, [BASE+'missing.js'], [BASE+'d.js']):
            with self.subTest(order=order), self.assertRaises(JSError):
                self.load(order)

    def test_plan_is_not_inherited_by_child_document(self):
        markup = HTML + '<iframe src="child"></iframe>'
        self.c.put_resource(BASE+'child', '<script>window.events=[]</script><script async src="a.js"></script>')
        self.load([BASE+'a.js',BASE+'b.js'], html=markup)
        self.assertEqual(self.c.eval("document.querySelector('iframe').contentWindow.events[0]"), 'a:loading')

    def test_duplicate_occurrences_fail_explicitly(self):
        with self.assertRaises(JSError):
            self.load([BASE+'a.js',BASE+'b.js'], html=HTML+'<script async src="a.js"></script>')

    def test_module_keeps_original_owner_after_recorded_boundary(self):
        self.c.put_resource(BASE+'module.js', "events.push('module:'+document.readyState+':'+(document.currentScript===null));export const answer=42",
                            headers=[['Content-Type','text/javascript']])
        self.load([BASE+'a.js',BASE+'b.js'], html=HTML+'<script type="module" src="module.js"></script>')
        self.assertEqual(self.c.eval('events.slice(-2)'), ['defer:interactive','module:interactive:true'])

    def test_existing_timer_quota_is_preserved(self):
        self.c.put_resource(BASE+'a.js', "for(let i=0;i<10002;i++) setTimeout(()=>{},0)")
        with self.assertRaisesRegex(JSError, 'Pending timer limit'):
            self.load([BASE+'a.js',BASE+'b.js'])


class PythonOrder(OrderCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class COrder(OrderCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__':
    unittest.main()
