"""Exercise example navigation, form submission and fresh dashboard verification locally."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
spec = importlib.util.spec_from_file_location('turnstile_example_session', ROOT / 'examples/turnstile/session.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, headers=()):
        payload = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == '/login/cf-turnstile':
            self.respond(200, '''<!doctype html><title>Local login fixture</title>
              <form method="post"><input id="email" name="email"><input id="password" name="password" type="password">
              <input name="_token" value="local-csrf" type="hidden">
              <input name="cf-turnstile-response" value="local-test-response" type="hidden">
              <button type="submit">Submit</button></form>''', [('Set-Cookie','session=local; Path=/; HttpOnly')])
        elif self.path == '/dashboard' and 'authenticated=yes' in self.headers.get('Cookie', ''):
            self.server.dashboard_reads += 1
            self.respond(200, '<!doctype html><title>Success Page - ScrapingCourse.com</title><p class="product-name">Fixture product</p>')
        else:
            self.respond(403, '<title>Forbidden</title>')

    def do_POST(self):
        form = parse_qs(self.rfile.read(int(self.headers.get('Content-Length', '0'))).decode())
        self.server.forms.append(form)
        valid = form == {'email':['admin@example.com'], 'password':['password'],
                        '_token':['local-csrf'], 'cf-turnstile-response':['local-test-response']}
        if not valid or 'session=local' not in self.headers.get('Cookie', ''):
            self.respond(403, '<title>Forbidden</title>')
            return
        self.respond(302, '', [('Location','/dashboard'), ('Set-Cookie','authenticated=yes; Path=/; HttpOnly')])

    def log_message(self, *_):
        pass


class ExampleTests(unittest.TestCase):
    def test_live_runtime_submits_and_refetches_with_same_cookie_jar(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.dashboard_reads, server.forms = 0, []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            args = SimpleNamespace(shell=ROOT/'dist/js.exe', request_timeout=20, proxy=None,
                profile=None, url=f'http://127.0.0.1:{server.server_port}/login/cf-turnstile',
                email='admin@example.com', password='password', timeout=20)
            with tempfile.TemporaryDirectory(prefix='ruyijs-example-') as directory:
                output = Path(directory)/'attempt'
                report = session.execute(args, output)
                self.assertTrue(report['passed'], report.get('errors'))
                self.assertTrue(report['submitted'])
                self.assertEqual(len(server.forms), 1)
                self.assertGreaterEqual(server.dashboard_reads, 2)
                self.assertEqual(report['final_state']['products'], ['Fixture product'])
                self.assertTrue((output/'dashboard.html').is_file())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_success_requires_expected_host_path_title_and_products(self):
        url = 'https://www.scrapingcourse.com/login/cf-turnstile'
        valid = {'url':'https://www.scrapingcourse.com/dashboard', 'title':'Success Page - ScrapingCourse.com', 'products':['x']}
        self.assertTrue(session.successful(valid, url))
        for key, value in [('url','https://other.test/dashboard'), ('url',url), ('title','Forbidden'), ('products',[])]:
            self.assertFalse(session.successful({**valid, key:value}, url))


if __name__ == '__main__':
    unittest.main()
