"""Observe real Necko send/header boundaries through the shared Performance owner."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from ruyijs import Context
from iframe_client import CClient


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def handle(self):
        try:super().handle()
        except ConnectionResetError:pass  # Context shutdown closes pooled sockets.
    def do_GET(self):
        if self.path.startswith('/redirect'):
            self.send_response(302);self.send_header('Location','/slow');self.send_header('Content-Length','0');self.end_headers();return
        if self.path.startswith('/slow') or self.path.startswith('/tao'):
            time.sleep(.12)
        payload=b'fixture-body'
        self.send_response(200)
        self.send_header('Content-Type','text/plain')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Access-Control-Allow-Origin','*')
        if self.path.startswith('/tao'):
            self.send_header('Timing-Allow-Origin','*')
        self.end_headers();self.wfile.flush()
        time.sleep(.08)
        self.wfile.write(payload)
    def log_message(self,*_):pass


class BoundaryCases:
    def setUp(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.context=self.client()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.context.load_page(self.origin+'/', '<!doctype html><body>')
    def tearDown(self):
        self.context.close();self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
    def fetch(self,url,frame=False):
        target='w' if frame else 'window'
        script='''globalThis.reply=null;fetch('''+json.dumps(url)+''').then(r=>r.text()).then(body=>{
          const e=performance.getEntriesByType('resource').find(x=>x.name==='''+json.dumps(url)+''');
          globalThis.reply={body,entry:e.toJSON(),identity:e===performance.getEntriesByName(e.name)[0],
            prototype:Object.getPrototypeOf(e)===PerformanceResourceTiming.prototype};
        }).catch(e=>{globalThis.reply={error:String(e)}});undefined'''
        self.context.eval(target+'.eval('+json.dumps(script)+')')
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            self.context.advance(25)
            value=self.context.eval(target+'.reply')
            if value is not None:return value
        self.fail('fetch deadline')
    def assert_measured(self,value):
        self.assertNotIn('error',value);self.assertEqual(value['body'],'fixture-body')
        self.assertTrue(value['identity']);self.assertTrue(value['prototype'])
        e=value['entry']
        self.assertGreater(e['requestStart'],0)
        self.assertGreaterEqual(e['requestStart'],e['fetchStart'])
        self.assertGreaterEqual(e['responseStart']-e['requestStart'],90)
        self.assertGreaterEqual(e['finalResponseHeadersStart'],e['responseStart'])
        self.assertGreaterEqual(e['responseEnd']-e['responseStart'],50)
        self.assertLessEqual(e['responseStart'],e['responseEnd'])
    def test_delayed_headers_and_body(self):self.assert_measured(self.fetch(self.origin+'/slow'))
    def test_redirect_final_request(self):
        value=self.fetch(self.origin+'/redirect');self.assert_measured(value)
        self.assertGreater(value['entry']['redirectEnd'],0)
        self.assertGreaterEqual(value['entry']['requestStart'],value['entry']['redirectEnd'])
    def test_iframe_uses_its_timeline(self):
        self.context.eval("globalThis.f=document.createElement('iframe');document.body.append(f);globalThis.w=f.contentWindow;undefined")
        self.assert_measured(self.fetch(self.origin+'/slow?frame',True))
    def test_cross_origin_tao_filters_measurements(self):
        other='http://localhost:'+str(self.server.server_port)
        hidden=self.fetch(other+'/slow')['entry']
        self.assertEqual([hidden[x] for x in ('requestStart','responseStart','finalResponseHeadersStart')],[0,0,0])
        self.assert_measured(self.fetch(other+'/tao'))
    def test_stored_resource_has_no_transport_measurements(self):
        url=self.origin+'/stored';self.context.put_resource(url,'fixture-body')
        e=self.fetch(url)['entry']
        self.assertEqual([e[x] for x in ('requestStart','responseStart','finalResponseHeadersStart')],[0,0,0])
    def test_synchronous_xhr_uses_same_measurements(self):
        value=self.context.eval('''(()=>{const x=new XMLHttpRequest();x.open('GET','/slow?xhr',false);x.send();
          const e=performance.getEntriesByType('resource').find(e=>e.initiatorType==='xmlhttprequest');
          return {body:x.responseText,entry:e.toJSON(),identity:e===performance.getEntriesByName(e.name)[0],
            prototype:Object.getPrototypeOf(e)===PerformanceResourceTiming.prototype};})()''')
        self.assert_measured(value)
    def test_logical_clock_does_not_import_physical_timestamps(self):
        self.context.close();self.context=self.client()
        self.context.configure_clock('logical',epoch_ms=1700000000000)
        self.context.load_page(self.origin+'/', '<!doctype html><body>')
        value=self.context.eval('''(()=>{const x=new XMLHttpRequest();x.open('GET','/slow?logical',false);x.send();
          const e=performance.getEntriesByType('resource')[0];
          return [e.requestStart,e.responseStart,e.finalResponseHeadersStart];})()''')
        self.assertEqual(value,[0,0,0])


class PythonBoundaries(BoundaryCases,unittest.TestCase):
    client=staticmethod(lambda:Context(shell=ROOT/'dist/js.exe',timeout=20))
class CBoundaries(BoundaryCases,unittest.TestCase):
    client=staticmethod(CClient)

if __name__=='__main__':unittest.main()
