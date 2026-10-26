"""WebGL clear mutates the real readback buffer through both client interfaces."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient

PROBE = Path(__file__).with_name('webgl_clear_probe.js').read_text('utf-8')
EXPECTED = json.loads(Path(__file__).with_name('webgl_clear_firefox.json').read_text('utf-8'))


class ClearCases:
    def setUp(self):
        self.context = self.client()
        self.addCleanup(self.context.close)
        self.context.load_page('https://graphics.example.test/', '<!doctype html><body>')

    def test_same_inputs_as_firefox(self):
        actual = self.context.eval('(' + PROBE + ')(window)')
        for version, cases in EXPECTED.items():
            for name, value in cases.items():
                with self.subTest(version=version, case=name):
                    self.assertEqual(actual[version][name], value)

    def test_cross_context_framebuffer_and_webgl2_bindings(self):
        self.assertEqual(self.context.eval('''(()=>{
          const make=()=>document.createElement('canvas').getContext('webgl2');const a=make(),b=make();
          const f=a.createFramebuffer();b.bindFramebuffer(b.FRAMEBUFFER,f);const foreign=b.getError();
          a.bindFramebuffer(a.READ_FRAMEBUFFER,f);a.clearColor(1,0,0,1);a.clear(a.COLOR_BUFFER_BIT);
          const drawError=a.getError(), p=new Uint8Array([7,7,7,7]);
          a.readPixels(0,0,1,1,a.RGBA,a.UNSIGNED_BYTE,p);const readError=a.getError();
          const binding=[a.getParameter(a.READ_FRAMEBUFFER_BINDING)===f,a.getParameter(a.DRAW_FRAMEBUFFER_BINDING)];
          a.bindFramebuffer(a.READ_FRAMEBUFFER,null);a.readPixels(0,0,1,1,a.RGBA,a.UNSIGNED_BYTE,p);
          return [foreign,drawError,readError,binding,Array.from(p)];})()'''),
          [1282,0,1286,[True,None],[255,0,0,255]])

    def test_borrowed_clear_and_distinct_realm(self):
        self.assertEqual(self.context.eval('''(()=>{
          const f=document.createElement('iframe');document.body.append(f);const w=f.contentWindow;
          const g=w.document.createElement('canvas').getContext('webgl');g.clearColor(1,0,1,1);
          WebGLRenderingContext.prototype.clear.call(g,g.COLOR_BUFFER_BIT);
          const p=new Uint8Array(4);g.readPixels(0,0,1,1,g.RGBA,g.UNSIGNED_BYTE,p);
          return [Array.from(p),g instanceof w.WebGLRenderingContext,g instanceof WebGLRenderingContext,
            w.WebGLRenderingContext.prototype.clear!==WebGLRenderingContext.prototype.clear];})()'''),
          [[255,0,255,255],True,False,True])


class PythonClear(ClearCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT/'dist/js.exe'))


class CClear(ClearCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__':
    unittest.main()
