"""Local ordinary HTTP and trustworthy localhost documents for surface evidence."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

HTML = '<!doctype html><html><head><title>Surface parity</title></head><body><iframe src="/frame"></iframe></body></html>'
FRAME = '<!doctype html><html><head><title>Frame parity</title></head><body></body></html>'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (FRAME if self.path == "/frame" else HTML).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class Fixture:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origins = {"http": f"http://parity.test:{self.server.server_port}",
                        "secure": f"http://localhost:{self.server.server_port}"}
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
