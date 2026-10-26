"""Location navigation through existing frame owners, via Python and the C DLL."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context, JSError
from iframe_client import CClient

ORIGIN = 'https://parent.test'
OTHER = 'https://child.test'


class NavigationCases:
    def setUp(self):
        self.c = self.client()
        self.addCleanup(self.c.close)
        self.c.configure_clock('logical', epoch_ms=1700000000000)
        for path, text in [('/a/start', 'start'), ('/b/done', 'done'), ('/c/final', 'final')]:
            self.c.put_resource(ORIGIN + path, '<p id="state">' + text + '</p>')
        self.prepare()

    def prepare(self, extra=''):
        self.c.load_page(ORIGIN + '/parent', '<iframe src="/a/start"></iframe>' + extra)
        self.c.eval("globalThis.f=document.querySelector('iframe');globalThis.w=f.contentWindow;undefined")

    def child(self, code):
        return self.c.eval('w.eval(' + json.dumps(code) + ')')

    def test_assign_replace_and_setters(self):
        for expression in ["location.assign('../b/done')", "location.replace('../b/done')",
                           "location.href='../b/done'", "window.location='../b/done'",
                           "document.location='../b/done'", "location.pathname='/b/done'"]:
            with self.subTest(expression=expression):
                self.prepare()
                self.child(expression + "; 'continued'")
                self.assertEqual(self.child('location.pathname'), '/a/start')
                self.c.advance(20)
                self.assertEqual(self.child('[location.pathname,document.body.textContent]'), ['/b/done', 'done'])
                self.assertEqual(self.c.eval('[location.pathname,f.getAttribute("src")]'), ['/parent', '/a/start'])
                self.assertTrue(self.c.eval('f.contentWindow===w && w.Array!==Array && w.document instanceof w.Document'))

    def test_reload(self):
        self.c.put_resource(ORIGIN + '/a/start', '<p>reloaded</p>')
        self.child('location.reload();undefined')
        self.c.advance(20)
        self.assertEqual(self.child('document.body.textContent'), 'reloaded')

    def test_fragments_stay_in_child(self):
        before = self.c.eval('[location.href,history.length]')
        count = len(self.c.net_log())
        self.child("window.events=[];addEventListener('hashchange',e=>events.push([e.oldURL,e.newURL,e.isTrusted,e.target===window]));undefined")
        self.child("location.hash='one';undefined")
        self.c.advance(10)
        self.assertEqual(self.child('location.hash'), '#one')
        self.assertEqual(self.child('events'), [[ORIGIN+'/a/start', ORIGIN+'/a/start#one', True, True]])
        self.child("location.replace('#two');undefined")
        self.c.advance(10)
        self.assertEqual(self.child('location.hash'), '#two')
        self.assertEqual(self.c.eval('[location.href,history.length]'), before)
        self.assertEqual(len(self.c.net_log()), count)

    def test_superseding_attribute_and_location_navigation(self):
        self.c.eval("f.src='/b/done';w.location.assign('/c/final');undefined")
        self.c.advance(20)
        self.assertEqual(self.child('location.pathname'), '/c/final')
        self.assertFalse(any('/b/done' in r['url'] for r in self.c.net_log()))

    def test_removal_cancels_queued_and_future_navigation(self):
        self.c.eval("w.location.assign('/b/done');f.remove();w.location.assign('/c/final');undefined")
        self.c.advance(20)
        self.assertFalse(any('/b/done' in r['url'] or '/c/final' in r['url'] for r in self.c.net_log()))

    def test_nested_frame_navigates_itself(self):
        self.c.put_resource(ORIGIN + '/nested', '<iframe src="/a/start"></iframe>')
        self.c.eval("f.src='/nested';undefined")
        self.c.advance(20)
        self.child("document.querySelector('iframe').contentWindow.location.assign('/b/done');undefined")
        self.c.advance(20)
        self.assertEqual(self.child("[location.pathname,document.querySelector('iframe').contentWindow.location.pathname]"), ['/nested', '/b/done'])

    def test_cross_origin_navigation_and_access(self):
        for p in ('one', 'two'):
            self.c.put_resource(OTHER + '/' + p, '<p>cross</p>')
        self.prepare("<script>function readFrame(){try{return document.querySelector('iframe').contentWindow.document.title}catch(e){return e.name}}"
                     "function moveFrame(url){document.querySelector('iframe').contentWindow.location.href=url}</script>")
        self.child('location.assign(' + json.dumps(OTHER + '/one') + ');undefined')
        self.c.advance(20)
        self.assertEqual(self.c.eval('readFrame()'), 'SecurityError')
        self.c.eval('moveFrame(' + json.dumps(OTHER + '/two') + ');undefined')
        self.c.advance(20)
        self.assertEqual(self.c.eval('f.contentWindow.location.href'), OTHER + '/two')
        self.assertEqual(self.c.eval('readFrame()'), 'SecurityError')

    def test_location_descriptor_and_invalid_receiver(self):
        self.assertEqual(self.child("(()=>{let d=Object.getOwnPropertyDescriptor(location,'href');return [d.enumerable,d.configurable,typeof d.set]})()"), [True, False, 'function'])
        with self.assertRaises(JSError) as failure:
            self.child("location.assign.call({},'/b/done')")
        self.assertEqual(failure.exception.name, 'TypeError')
        self.assertEqual(self.child('location.pathname'), '/a/start')

    def test_http_error_document_and_frame_load(self):
        self.c.put_resource(ORIGIN + '/missing', '<p>not found</p>', status=404)
        self.c.eval("window.loads=0;f.addEventListener('load',()=>loads++);undefined")
        self.child("location.assign('/missing');undefined")
        self.c.advance(20)
        self.assertEqual(self.child('document.body.textContent'), 'not found')
        self.assertEqual(self.c.eval('loads'), 1)

    def test_redirect_commits_final_url_and_fragment(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/final')
                    body = b''
                else:
                    self.send_response(200)
                    body = b'<p>redirected</p>'
                self.send_header('Content-Type', 'text/html')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = 'http://127.0.0.1:' + str(server.server_port)
        self.child('location.assign(' + json.dumps(url + '/redirect#kept') + ');undefined')
        self.c.advance(30)
        self.assertEqual(self.c.eval('f.contentWindow.location.href'), url + '/final#kept')
        self.assertEqual(self.c.eval('f.contentDocument.body.textContent'), 'redirected')

    def test_top_level_navigation_preserved(self):
        self.c.eval("location.assign('/b/done');undefined")
        self.c.advance(20)
        self.assertEqual(self.c.eval('[location.pathname,document.body.textContent]'), ['/b/done', 'done'])


class PythonNavigationTests(NavigationCases, unittest.TestCase):
    client = staticmethod(lambda: Context(timeout=15))


class CAbiNavigationTests(NavigationCases, unittest.TestCase):
    client = CClient


if __name__ == '__main__':
    unittest.main(verbosity=2)
