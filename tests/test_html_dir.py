"""HTMLElement.dir semantics through the actual Python and C ABI runtime paths."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient

PROBE = Path(__file__).with_name('dir_probe.js').read_text('utf-8')


class DirectionCases:
    def setUp(self):
        self.context = self.client()
        self.addCleanup(self.context.close)
        self.context.load_page('https://direction.test/', '<!doctype html><iframe></iframe>')

    def test_enumeration_and_attribute_identity(self):
        for target in ('window', "document.querySelector('iframe').contentWindow"):
            with self.subTest(target=target):
                result = self.context.eval('(' + PROBE + ')(' + target + ')')
                self.assertEqual(result['assignments'], [
                    ['ltr', 'ltr'], ['rtl', 'RTL'], ['auto', 'AuTo'], ['', ''],
                    ['', 'invalid'], ['', ' ltr'], ['', 'rtl '], ['', '\u212a'],
                    ['', 'null'], ['', 'undefined'], ['', '42']])
                self.assertEqual(result['direct'], ['rtl', 'RtL'])
                self.assertEqual(result['absent'], ['', False])
                self.assertEqual(result['inherited'], '')
                self.assertEqual(result['cloned'], ['auto', 'auto', True])
                self.assertEqual(result['conversion'], ['ltr', 'LtR', 1])
                self.assertEqual(result['atomic'], ['TypeError', 'ltr', 'LtR'])
                self.assertEqual(result['brands'], [['TypeError', True]] * 4)
                self.assertEqual(result['writeConversions'], 0)
                self.assertEqual(result['descriptor'], dict(enumerable=True, configurable=True,
                    getLength=0, setLength=1, own=False, shared=True))

    def test_borrowed_accessor_uses_receiver_document(self):
        self.assertEqual(self.context.eval('''(() => {
          const w = document.querySelector('iframe').contentWindow;
          const a = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'dir');
          const b = Object.getOwnPropertyDescriptor(w.HTMLElement.prototype, 'dir');
          const p = document.createElement('div'), c = w.document.createElement('div');
          a.set.call(c, 'RTL'); b.set.call(p, 'AUTO');
          const adopted = document.adoptNode(c);
          return [a.get.call(c), b.get.call(p), c.getAttribute('dir'), p.getAttribute('dir'),
                  adopted === c, adopted.ownerDocument === document, adopted.dir,
                  a.get !== b.get, p.dir];
        })()'''), ['rtl', 'auto', 'RTL', 'AUTO', True, True, 'rtl', True, 'auto'])


class PythonDirection(DirectionCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CDirection(DirectionCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__':
    unittest.main()
