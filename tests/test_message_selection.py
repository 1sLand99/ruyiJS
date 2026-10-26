"""Same-payload Window messages are selected by explicit source/target metadata."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient


class MessageCases:
    def setUp(self):
        self.c = self.client(); self.addCleanup(self.c.close)
        self.c.configure_clock('logical', epoch_ms=1700000000000)
        self.rpc('configure_message_replay', enabled=True)
        self.c.put_resource('http://message.test/frame.js',
            "addEventListener('message',e=>{parent.events.push(location.pathname+':'+e.data)});",
            headers=[['Content-Type', 'text/javascript']])
        self.c.put_resource('http://message.test/frame.html',
            '<!doctype html><script src="/frame.js"></script>', headers=[['Content-Type', 'text/html']])
        self.c.load_page('http://message.test/', '<!doctype html><script>window.events=[]</script>'
                         '<iframe src="/frame.html"></iframe><iframe src="/frame.html"></iframe>')
        self.c.eval("window.events=[];document.querySelectorAll('iframe')[0].contentWindow.postMessage('same','*');document.querySelectorAll('iframe')[1].contentWindow.postMessage('same','*');undefined")

    def rpc(self, action, **fields):
        return self.c._event_loop(action, **fields) if isinstance(self.c, Context) else self.c.call('event_loop', action=action, **fields)

    def pending(self): return self.c.pending_messages() if isinstance(self.c, Context) else self.rpc('pending_messages')

    def select_message(self, row, **override):
        values = {'task_id': row['task_id'], 'source_realm': row['source_realm'],
                  'target_realm': row['target_realm'], 'sequence': row['sequence'],
                  'kind': row['kind'], 'at_ms': row['due_ms']}
        values.update(override)
        return self.c.run_message(**values) if isinstance(self.c, Context) else self.rpc('run_message', **values)

    def test_same_payloads_have_distinct_source_sequence_and_targets(self):
        rows = sorted(self.pending(), key=lambda r: r['sequence']); self.assertEqual(len(rows), 2)
        self.assertEqual([r['sequence'] for r in rows], [1, 2])
        self.assertEqual(len({r['target_realm'] for r in rows}), 2)
        self.assertEqual(len({r['task_id'] for r in rows}), 2)
        self.select_message(rows[1]); self.assertEqual(self.c.eval('events'), ['/frame.html:same'])
        self.select_message(rows[0]); self.assertEqual(self.c.eval('events'), ['/frame.html:same', '/frame.html:same'])
        self.assertEqual(self.pending(), [])

    def test_wrong_message_identity_does_not_consume_task(self):
        row = self.pending()[0]; before = self.rpc('status')
        for key, value in [('source_realm', row['source_realm'] + 1), ('target_realm', row['target_realm'] + 1),
                           ('sequence', row['sequence'] + 10), ('kind', row['kind'] + 1), ('task_id', row['task_id'] + 100)]:
            with self.assertRaises(Exception): self.select_message(row, **{key: value})
            self.assertEqual(self.rpc('status'), before); self.assertEqual(self.pending(), [row, self.pending()[1]])
        self.assertEqual(self.c.eval('events'), [])

    def test_message_replay_rejects_pending_microtask_and_unknown_field(self):
        row = self.pending()[0]
        self.c.eval("queueMicrotask(()=>events.push('micro'));undefined")
        # The request boundary may already checkpoint this native microtask;
        # selection remains valid after that checkpoint.
        with self.assertRaises(Exception): self.rpc('run_message', task_id=row['task_id'], source_realm=row['source_realm'],
                                                     target_realm=row['target_realm'], sequence=row['sequence'], kind=row['kind'],
                                                     at_ms=row['due_ms'], unknown=1)
        if isinstance(self.c, Context): self.c.checkpoint()
        else: self.c.call('checkpoint')
        self.select_message(row); self.assertIn('/frame.html:same', self.c.eval('events'))

    def test_default_message_path_is_unchanged_in_new_context(self):
        other = self.client()
        try:
            other.configure_clock('logical', epoch_ms=1700000000000)
            other.put_resource('http://message.test/frame.js', "addEventListener('message',e=>parent.got=e.data);",
                               headers=[['Content-Type', 'text/javascript']])
            other.put_resource('http://message.test/frame.html', '<script src="/frame.js"></script>', headers=[['Content-Type', 'text/html']])
            other.load_page('http://message.test/', '<iframe src="/frame.html"></iframe><script>window.got=null</script>')
            other.eval("document.querySelector('iframe').contentWindow.postMessage('default','*');undefined")
            other.advance(1); self.assertEqual(other.eval('got'), 'default')
        finally: other.close()


class PythonMessages(MessageCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CMessages(MessageCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__': unittest.main()
