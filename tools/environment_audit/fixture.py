"""Local deterministic HTTP/CORS fixtures for browser environment comparison."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

HTML = '<!doctype html><html lang="en-US"><head><title>Environment audit</title></head><body><iframe src="/frame"></iframe></body></html>'
FRAME = '<!doctype html><html lang="en-US"><head><title>Audit frame</title></head><body></body></html>'


class Handler(BaseHTTPRequestHandler):
    def serve(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length else ''
        if self.path.startswith('/echo') or self.path.startswith('/cors'):
            data = json.dumps({'method':self.command, 'body':body, 'contentType':self.headers.get('Content-Type', '')}).encode()
            content_type = 'application/json'
        else:
            data = (FRAME if self.path.startswith('/frame') else HTML).encode()
            content_type = 'text/html; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Audit-Visible', 'yes')
        self.send_header('X-Audit-Hidden', 'private')
        if self.path.startswith('/cors'):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Expose-Headers', 'X-Audit-Visible')
        self.end_headers()
        self.wfile.write(data)

    do_GET = serve
    do_POST = serve

    def log_message(self, *_):
        pass


class Fixture:
    def __enter__(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_port
        self.origins = {'http':f'http://parity.test:{port}', 'secure':f'http://localhost:{port}'}
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
