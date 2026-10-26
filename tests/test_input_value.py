"""Input state uses one native owner across Python, C, form data and typing."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient

PROBE = (Path(__file__).with_name('input_value_probe.js')).read_text('utf-8')
EXPECTED = json.loads(Path(__file__).with_name('input_value_firefox.json').read_text('utf-8'))


class InputCases:
    def setUp(self):
        self.context = self.client()
        self.addCleanup(self.context.close)
        self.context.load_page('https://input.example.test/', '<!doctype html><body>')

    def test_firefox_same_input_contract(self):
        actual = self.context.eval('(' + PROBE + ')(window)')
        for key, expected in EXPECTED.items():
            with self.subTest(case=key):
                self.assertEqual(actual[key], expected)

    def test_native_typing_updates_current_value_only(self):
        self.context.eval('''document.body.innerHTML='<form><input id="x" name="x" value="A"></form>';undefined''')
        if isinstance(self.context, Context):
            self.context.type('B', target="document.querySelector('#x')", interval_ms=0)
        else:
            self.context.call('user', action='type', text='B', target="document.querySelector('#x')", interval_ms=0)
        self.assertEqual(self.context.eval('''(()=>{const e=document.querySelector('#x');return [e.value,
          e.defaultValue,e.getAttribute('value'),new FormData(e.form).get('x')]})()'''), ['AB','A','A','AB'])

    def test_reset_button_and_checked_state(self):
        self.assertEqual(self.context.eval('''(()=>{
          const f=document.createElement('form');f.innerHTML='<input name="x" value="seed"><input name="c" type="checkbox" checked><button type="reset">R</button>';
          document.body.append(f);f.elements.x.value='live';f.elements.c.checked=false;f.elements.c.indeterminate=true;
          f.querySelector('button').click();return [f.elements.x.value,f.elements.x.defaultValue,
            f.elements.c.checked,f.elements.c.indeterminate];})()'''), ['seed','seed',True,True])

    def test_empty_dirty_value_and_cross_realm_adoption(self):
        self.assertEqual(self.context.eval('''(()=>{
          const f=document.createElement('iframe');document.body.append(f);const w=f.contentWindow;
          const e=w.document.createElement('input');e.defaultValue='seed';e.value='';
          const adopted=document.adoptNode(e);adopted.defaultValue='next';
          const copy=document.importNode(adopted);copy.defaultValue='copy';
          return [e===adopted,e.ownerDocument===document,e.value,e.defaultValue,copy.value,copy.defaultValue];})()'''),
          [True,True,'','next','','copy'])


class PythonInput(InputCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CInput(InputCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__':
    unittest.main()
