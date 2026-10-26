"""Loopback-only server with immutable bytes for the tier coverage experiment."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

SCRIPT = Path(__file__).with_name('tier_workload.js').read_bytes()
HTML = b'<!doctype html><script src="/tier-workload.js"></script>'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        script = self.path == '/tier-workload.js'
        body = SCRIPT if script else HTML
        self.send_response(200)
        self.send_header('Content-Type', 'application/javascript' if script else 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_): pass


class Fixture:
    def __enter__(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/'
        return self
    def __exit__(self, *_):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
