"""Export HttpOnly cookies and send the selected header through external Necko."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / 'examples/google'))
from ruyijs import Context
from google_search import NeckoSession


class CookieEcho(BaseHTTPRequestHandler):
    def do_GET(self):
        body = self.headers.get('Cookie', '').encode('latin-1')
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ExternalNeckoCookies(unittest.TestCase):
    def test_http_only_header_reaches_external_necko_server(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), CookieEcho)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 3)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}'
        with Context(shell=ROOT / 'dist/js.exe') as context:
            context.load_page(url + '/', '')
            context.put_resource(url + '/seed', '', headers=[
                ['Set-Cookie', 'sid=root; HttpOnly; Path=/'],
                ['Set-Cookie', 'sid=deep; HttpOnly; Path=/account'],
                ['Set-Cookie', 'unrelated=hidden; HttpOnly; Path=/other']])
            context.eval("(()=>{const x=new XMLHttpRequest();x.open('GET','/seed',false);x.send()})()")
            self.assertEqual(context.eval('document.cookie'), '')
            self.assertEqual(len(context.export_cookies()), 3)
            transport = NeckoSession()
            self.addCleanup(transport.process.stdout.close)
            self.addCleanup(transport.close)
            target = url + '/account/check'
            header = context.cookie_header(target, source_url=url)
            status, _, body, _ = transport.send('GET', target, [('Cookie', header)])
            self.assertEqual(status, 200)
            self.assertEqual(body, b'sid=deep; sid=root')


if __name__ == '__main__':
    unittest.main()
