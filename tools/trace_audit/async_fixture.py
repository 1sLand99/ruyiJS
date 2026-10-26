"""Local explicit asynchronous workload, with separate frame and worker sources."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

SCRIPT = Path(__file__).with_name('async_workload.js').read_bytes()
FRAME = b'''<!doctype html><script src="/async-frame.js"></script>'''
FRAME_SCRIPT = b'''addEventListener('message', function frameRequest(event) {
  if(event.source===parent && event.data==='frame-request')
    Promise.resolve().then(function framePromise(){parent.postMessage('frame-response',event.origin)});
});'''
WORKER_SCRIPT = b'''onmessage = function workerRequest(event) {
  if(event.data==='worker-request')
    Promise.resolve().then(function workerPromise(){postMessage('worker-response')});
};'''
HTML = b'<!doctype html><iframe src="/frame"></iframe><script src="/async-workload.js"></script>'
RESOURCES = {'/':('text/html',HTML),'/frame':('text/html',FRAME),
    '/async-workload.js':('text/javascript',SCRIPT),'/async-frame.js':('text/javascript',FRAME_SCRIPT),
    '/async-worker.js':('text/javascript',WORKER_SCRIPT),
    '/async-start.js':('text/javascript',b'startAsyncProof();')}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        found=self.path in RESOURCES
        mime,body=RESOURCES.get(self.path,('text/plain',b'not found'))
        self.send_response(200 if found else 404)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def log_message(self,*_):pass


class Fixture:
    def __enter__(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        return self
    def __exit__(self,*_):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
