"""Host realm lookup must use installed globals without consuming timer handles."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient


class RealmCases:
    def setUp(self):
        self.c = self.client(); self.addCleanup(self.c.close)
        self.c.configure_clock('logical', epoch_ms=1700000000000)
        self.rpc('configure_timer_replay', enabled=True)
        self.c.load_page('http://timer-realm.test/', '<!doctype html><iframe></iframe><iframe></iframe>')

    def rpc(self, action, **fields):
        return self.c._event_loop(action, **fields) if isinstance(self.c, Context) else self.c.call('event_loop', action=action, **fields)

    def realm(self, target):
        return self.c.timer_realm(target) if isinstance(self.c, Context) else self.c.call('timer_realm', target=target)

    def test_prebinding_preserves_public_handles_and_identity(self):
        owner = self.realm('window'); a = self.realm("document.querySelectorAll('iframe')[0].contentWindow")
        b = self.realm("document.querySelectorAll('iframe')[1].contentWindow")
        self.assertEqual(len({owner, a, b}), 3)
        self.assertEqual(self.realm('globalThis'), owner)
        self.assertEqual(self.rpc('pending_timers'), [])
        ids = self.c.eval("[setTimeout(()=>{},100),document.querySelectorAll('iframe')[0].contentWindow.setTimeout(()=>{},100),document.querySelectorAll('iframe')[1].contentWindow.setTimeout(()=>{},100)]")
        self.assertEqual(ids, [1, 1, 1])
        self.assertEqual({r['realm_id'] for r in self.rpc('pending_timers')}, {owner, a, b})
        self.assertEqual(self.realm('self'), owner)

    def test_queries_after_cancellation_retain_realm_identity(self):
        identity = self.realm('window')
        self.c.eval('const id=setTimeout(()=>{},100);clearTimeout(id);undefined')
        self.assertEqual(self.realm('window'), identity)
        if isinstance(self.c, Context): self.c.collect_garbage()
        else: self.c.call('collect')
        self.assertEqual(self.realm('window'), identity)
        self.assertEqual(self.c.eval('setTimeout(()=>{},100)'), 2)

    def test_object_prototype_and_user_proxy_are_not_globals(self):
        for expression in ('({})', 'document', 'Window.prototype', 'Object.create(window)', 'new Proxy(window,{})', 'null', '1'):
            with self.assertRaises(Exception): self.realm(expression)
        self.assertEqual(self.rpc('pending_timers'), [])

    def test_retired_window_does_not_rebind_to_live_window(self):
        self.c.eval("window.saved=document.querySelector('iframe').contentWindow;undefined")
        old = self.realm('saved')
        self.c.eval("document.querySelector('iframe').remove();undefined")
        with self.assertRaises(Exception): self.realm('saved')
        self.assertNotEqual(self.realm("document.querySelector('iframe').contentWindow"), old)

    def test_expression_is_explicit_evaluation_with_side_effects(self):
        self.c.eval('window.reads=0;undefined')
        identity = self.realm('(reads++, window)')
        self.assertEqual(self.c.eval('reads'), 1)
        self.assertEqual(self.realm('window'), identity)
        with self.assertRaisesRegex(Exception, 'intentional'):
            self.realm("(()=>{reads++;throw new Error('intentional')})()")
        self.assertEqual(self.c.eval('reads'), 2)

    def test_target_validation_before_evaluation_and_configuration_freeze(self):
        for value in (None, 12, '', ' ' * 65537):
            with self.assertRaises(Exception): self.realm(value)
        with self.assertRaises(Exception): self.rpc('configure_timer_replay', enabled=False)
        other = self.client()
        try:
            def query():
                if isinstance(other, Context): return other.timer_realm('window.side=1;window')
                return other.call('timer_realm', target='window.side=1;window')
            with self.assertRaises(Exception): query()
            self.assertEqual(other.eval('typeof side'), 'undefined')
        finally: other.close()


class PythonTimerRealm(RealmCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CTimerRealm(RealmCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__': unittest.main()
