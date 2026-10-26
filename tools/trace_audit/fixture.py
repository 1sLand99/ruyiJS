"""Loopback-only workload server for paired native-capture measurements."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

HTML = '<!doctype html><html><body><script src="/workload.js"></script></body></html>'
SCRIPT = Path(__file__).with_name('workload.js').read_bytes()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = SCRIPT if self.path == '/workload.js' else HTML.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/javascript' if self.path == '/workload.js' else 'text/html')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


class Fixture:
    def __enter__(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/'
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
