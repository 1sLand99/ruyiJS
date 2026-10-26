"""Absolute auto-inset boxes retain their original position in normal flow."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context
from iframe_client import CClient
PROBE=Path(__file__).with_name('static_position_probe.js').read_text('utf8')
EXPECTED=json.loads(Path(__file__).with_name('static_position_firefox.json').read_text('utf8'))

class StaticCases:
    def setUp(self):
        self.c=self.client();self.addCleanup(self.c.close)
        self.c.load_page('https://position.example.test/','<!doctype html><body>')
    def compare(self,actual):
        for key,value in EXPECTED.items():
            if key.startswith('inlineBefore'):continue # Separate pre-existing inline baseline descent.
            with self.subTest(case=key):self.assertEqual(actual[key],value)
        self.assertEqual(actual['inlineBefore'][0][1]-20,actual['inlineBefore|height'])
    def test_native_firefox_static_positions(self):self.compare(self.c.eval('('+PROBE+')(window)'))
    def test_iframe_static_positions(self):
        self.compare(self.c.eval('''(()=>{const f=document.createElement('iframe');document.body.append(f);
          return f.contentWindow.eval('''+json.dumps('('+PROBE+')(window)')+''');})()'''))
    def test_resize_reflows_and_snapshots_keep_identity(self):
        self.assertEqual(self.c.eval('''(()=>{
          const p=document.createElement('div');p.style.cssText='position:fixed;left:0;top:0;width:100px';
          p.innerHTML='<div id="normal" style="height:30px"></div><div id="abs" style="position:absolute;width:10px;height:10px"></div>';
          document.body.append(p);const n=p.firstElementChild,a=p.lastElementChild;
          const first=a.getBoundingClientRect();n.style.height='50px';
          const next=Element.prototype.getBoundingClientRect.call(a);
          const parent=p.getBoundingClientRect();p.remove();
          return [first.y,next.y,parent.height,Object.getPrototypeOf(first)===DOMRect.prototype,
            first!==next,first.y];})()'''),[30,50,50,True,True,30])

class PythonStatic(StaticCases,unittest.TestCase):
    client=staticmethod(lambda:Context(shell=ROOT/'dist/js.exe'))
class CStatic(StaticCases,unittest.TestCase):
    client=staticmethod(CClient)
if __name__=='__main__':unittest.main()
