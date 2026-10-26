"""One declaration store for transform aliases through Python and the C ABI."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context
from iframe_client import CClient
PROBE=Path(__file__).with_name('css_transform_alias_probe.js').read_text('utf8')
EXPECTED=json.loads(Path(__file__).with_name('css_transform_alias_firefox.json').read_text('utf8'))

class AliasCases:
    def setUp(self):
        self.context=self.client();self.addCleanup(self.context.close)
        self.context.load_page('https://style.example.test/','<!doctype html><body>')
    def test_firefox_declaration_order_and_identity(self):
        self.assertEqual(self.context.eval('('+PROBE+')(window)'),EXPECTED)
    def test_firefox_iframe_declarations(self):
        actual=self.context.eval('''(()=>{const f=document.createElement('iframe');document.body.append(f);
          return f.contentWindow.eval('''+json.dumps('('+PROBE+')(window)')+''');})()''')
        self.assertEqual(actual,EXPECTED)
    def test_attribute_source_mutation_and_borrowed_method(self):
        self.assertEqual(self.context.eval('''(()=>{
          const f=document.createElement('iframe');document.body.append(f);const w=f.contentWindow;
          const e=w.document.createElement('div');w.document.body.append(e);
          e.setAttribute('style','-moz-transform:translateX(7px);transform:translateX(2px)');
          const style=e.style;const first=style.transform;
          CSSStyleDeclaration.prototype.setProperty.call(style,'-webkit-transform','translateX(9px)','important');
          const values=[first,style.transform,style.getPropertyValue('-moz-transform'),style.length,
            style instanceof w.CSSStyleProperties,style instanceof CSSStyleProperties,e.style===style];
          e.setAttribute('style','transform:translateX(3px)');values.push(style.MozTransform);
          style.setProperty('--transform','literal');values.push(style.getPropertyValue('--transform'));
          return values;})()'''),['translateX(2px)','translateX(9px)','translateX(9px)',1,True,False,True,'translateX(3px)','literal'])

class PythonAliases(AliasCases,unittest.TestCase):
    client=staticmethod(lambda:Context(shell=ROOT/'dist/js.exe'))
class CAliases(AliasCases,unittest.TestCase):
    client=staticmethod(CClient)
if __name__=='__main__':unittest.main()
