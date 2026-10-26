"""Two real loopback origins for Fetch response filtering evidence."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

HTML = '<!doctype html><title>CORS parity</title><iframe src="/frame"></iframe>'
FRAME = '<!doctype html><title>CORS frame</title>'
BODY = b'cors-fixture'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != '/resource':
            body = (FRAME if url.path == '/frame' else HTML).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        case = parse_qs(url.query).get('case', ['explicit'])[0]
        self.send_response(200)
        headers = [
            ('Access-Control-Allow-Origin', self.server.page_origin),
            ('Access-Control-Allow-Credentials', 'true'),
            ('Cache-Control', 'no-store'), ('Content-Language', 'en'),
            ('Content-Length', str(len(BODY))), ('Content-Type', 'text/plain'),
            ('Expires', 'Wed, 21 Oct 2015 07:28:00 GMT'),
            ('Last-Modified', 'Wed, 21 Oct 2015 07:28:00 GMT'), ('Pragma', 'no-cache'),
            ('X-Visible', 'visible'), ('X-Hidden', 'hidden'),
            ('X-Alpha', 'alpha'), ('X-Bravo', 'bravo'), ('CF-Chl-Peek', 'fixture'),
            ('X-Cookie-Seen', 'yes' if self.headers.get('Cookie') else 'no'),
            ('Set-Cookie', 'cors_probe=fixture; Path=/; SameSite=Lax'),
            ('Set-Cookie2', 'legacy_probe=fixture; Path=/')]
        if case == 'explicit':
            headers.append(('Access-Control-Expose-Headers', 'X-Visible, CF-Chl-Peek'))
        elif case == 'multiline':
            headers += [('Access-Control-Expose-Headers', 'X-Alpha, x-BrAvO'),
                        ('aCcEsS-CoNtRoL-ExPoSe-HeAdErS', 'CF-Chl-Peek, X-ALPHA')]
        elif case == 'wildcard':
            headers.append(('Access-Control-Expose-Headers', '*'))
        elif case == 'cookie-expose':
            headers.append(('Access-Control-Expose-Headers', 'Set-Cookie, SeT-CoOkIe2, X-Visible, X-Cookie-Seen'))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *_):
        pass


class CorsFixture:
    def __enter__(self):
        self.servers = [ThreadingHTTPServer(('127.0.0.1', 0), Handler) for _ in range(2)]
        self.page = 'http://localhost:' + str(self.servers[0].server_port)
        self.target = 'http://localhost:' + str(self.servers[1].server_port)
        self.threads = []
        for server in self.servers:
            server.page_origin = self.page
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        return self

    def __exit__(self, *_):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)
