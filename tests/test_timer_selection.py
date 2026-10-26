"""Host selection must execute the original live timer and preserve default APIs."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient


class SelectionCases:
    def setUp(self):
        self.c = self.client(); self.addCleanup(self.c.close)
        self.c.configure_clock('logical', epoch_ms=1700000000000)
        self.rpc('configure_timer_replay', enabled=True)
        self.c.load_page('https://selection.test/', '<!doctype html><iframe></iframe><iframe></iframe>')
        self.c.eval("window.events=[];window.a=document.querySelectorAll('iframe')[0].contentWindow;window.b=document.querySelectorAll('iframe')[1].contentWindow;undefined")

    def rpc(self, action, **fields):
        return self.c._event_loop(action, **fields) if isinstance(self.c, Context) else self.c.call('event_loop', action=action, **fields)

    def pending(self):
        return self.c.pending_timers() if isinstance(self.c, Context) else self.rpc('pending_timers')

    def select_timer(self, row, at=None):
        at = row['due_ms'] if at is None else at
        if isinstance(self.c, Context): return self.c.run_timer(row['task_id'], row['firings'], at)
        return self.rpc('run_timer', task_id=row['task_id'], expected_firings=row['firings'], at_ms=at)

    def test_selected_order_differs_from_default_fifo(self):
        self.c.eval("setTimeout(()=>{events.push('a');Promise.resolve().then(()=>events.push('micro-a'))},0);setTimeout(()=>events.push('b'),0);undefined")
        rows = sorted(self.pending(), key=lambda r: r['public_handle'])
        self.assertTrue(all(type(r['ready']) is bool and type(r['repeating']) is bool for r in rows))
        self.assertEqual(self.select_timer(rows[1])['executed'], 1)
        self.assertEqual(self.c.eval('events'), ['b'])
        self.select_timer(rows[0]); self.assertEqual(self.c.eval('events'), ['b', 'a', 'micro-a'])
        self.assertEqual(self.pending(), [])

    def test_wrong_identity_or_time_has_no_effect(self):
        self.c.eval("setTimeout(()=>events.push('ran'),20);undefined")
        row = self.pending()[0]; before = self.rpc('status')
        cases = [dict(task_id=row['task_id'], expected_firings=0, at_ms=19),
                 dict(task_id=row['task_id'], expected_firings=1, at_ms=20),
                 dict(task_id=2147483647, expected_firings=0, at_ms=20),
                 dict(task_id=True, expected_firings=0, at_ms=20),
                 dict(task_id=row['task_id'], expected_firings=0, at_ms=-1),
                 dict(task_id=row['task_id'], expected_firings=0, at_ms=20, unknown=1)]
        for fields in cases:
            with self.assertRaises(Exception): self.rpc('run_timer', **fields)
            self.assertEqual(self.rpc('status'), before)
            self.assertEqual(self.pending(), [row])
        self.assertEqual(self.c.eval('events'), [])

    def test_cancelled_and_retired_snapshots_fail(self):
        self.c.eval("a.setTimeout(()=>events.push('a'),0);b.setTimeout(()=>events.push('b'),0);undefined")
        rows = self.pending(); self.c.eval("a.clearTimeout(1);document.querySelectorAll('iframe')[1].remove();undefined")
        self.assertEqual(self.pending(), [])
        for row in rows:
            with self.assertRaises(Exception): self.select_timer(row)
        self.assertEqual(self.c.eval('events'), [])

    def test_same_public_handle_has_distinct_realm_and_task(self):
        self.c.eval("a.setTimeout(function(){events.push(this===a?'a':'bad')},0);b.setTimeout(function(){events.push(this===b?'b':'bad')},0);undefined")
        rows = sorted(self.pending(), key=lambda r: r['task_id'])
        self.assertEqual([r['public_handle'] for r in rows], [1, 1])
        self.assertEqual(len({r['realm_id'] for r in rows}), 2)
        self.select_timer(rows[1]); self.select_timer(rows[0]); self.assertEqual(self.c.eval('events'), ['b', 'a'])

    def test_interval_counter_rejects_duplicate_consumption(self):
        self.c.eval("let n=0;const id=setInterval(()=>{events.push(++n);if(n===2)clearInterval(id)},10);undefined")
        first = self.pending()[0]; self.select_timer(first)
        second = self.pending()[0]; self.assertEqual(second['firings'], 1)
        with self.assertRaises(Exception): self.select_timer(first, second['due_ms'])
        self.select_timer(second); self.assertEqual(self.c.eval('events'), [1, 2]); self.assertEqual(self.pending(), [])

    def test_string_arguments_gc_and_original_surface(self):
        shape = self.c.eval("[setTimeout.toString(),Object.getOwnPropertyDescriptor(window,'setTimeout').enumerable,setTimeout===a.setTimeout]")
        self.c.eval("const obj={value:7};setTimeout(x=>events.push(x.value),0,obj);setTimeout(\"events.push('string')\",0);undefined")
        if isinstance(self.c, Context): self.c.collect_garbage()
        else: self.c.call('collect')
        for row in sorted(self.pending(), key=lambda r: r['task_id']): self.select_timer(row)
        self.assertEqual(self.c.eval('events'), [7, 'string'])
        self.assertEqual(self.c.eval("[setTimeout.toString(),Object.getOwnPropertyDescriptor(window,'setTimeout').enumerable,setTimeout===a.setTimeout]"), shape)
        self.assertEqual(shape[1:], [True, False]); self.assertIn('[native code]', shape[0])
        self.assertEqual(self.c.eval("(()=>{try{setTimeout.call({},()=>{},0)}catch(e){return e.name}})()"), 'TypeError')

    def test_internal_message_and_frame_not_exposed(self):
        self.c.eval("onmessage=()=>events.push('message');postMessage('x','*');requestAnimationFrame(()=>events.push('frame'));setTimeout(()=>events.push('timer'),0);undefined")
        rows = self.pending(); self.assertEqual(len(rows), 1); self.select_timer(rows[0])
        self.assertEqual(self.c.eval('events'), ['timer'])
        self.c.advance(20); self.assertEqual(self.c.eval('events'), ['timer', 'message', 'frame'])

    def test_disabled_and_late_configuration_rejected(self):
        with self.assertRaises(Exception): self.rpc('configure_timer_replay', enabled=False)
        other = self.client()
        try:
            other.configure_clock('logical', epoch_ms=1700000000000)
            call = other._event_loop if isinstance(other, Context) else lambda action, **f: other.call('event_loop', action=action, **f)
            with self.assertRaises(Exception): call('pending_timers')
            with self.assertRaises(Exception): call('configure_timer_replay', enabled=1)
            other.eval("window.e=[];setTimeout(()=>e.push('a'),0);setTimeout(()=>e.push('b'),0);undefined")
            other.advance(1); self.assertEqual(other.eval('e'), ['a', 'b'])
        finally: other.close()

    def test_nested_timer_and_callback_exception_keep_owner_path(self):
        self.c.eval("setTimeout(()=>{events.push('outer');setTimeout(()=>events.push('nested'),0);queueMicrotask(()=>events.push('micro'));throw new Error('expected-selection')},0);undefined")
        with self.assertRaisesRegex(Exception, 'expected-selection'):
            self.select_timer(self.pending()[0])
        self.assertEqual(self.c.eval('events'), ['outer', 'micro'])
        self.select_timer(self.pending()[0])
        self.assertEqual(self.c.eval('events'), ['outer', 'micro', 'nested'])

    def test_system_clock_requires_explicit_logical_configuration(self):
        other = self.client()
        try:
            call = other._event_loop if isinstance(other, Context) else lambda action, **f: other.call('event_loop', action=action, **f)
            call('configure_timer_replay', enabled=True)
            other.eval("window.ran=false;setTimeout(()=>ran=true,0);undefined")
            row = call('pending_timers')[0]
            with self.assertRaises(Exception): call('run_timer', task_id=row['task_id'], expected_firings=0, at_ms=row['due_ms'])
            self.assertFalse(other.eval('ran'))
        finally: other.close()


class PythonSelection(SelectionCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CSelection(SelectionCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__': unittest.main()
