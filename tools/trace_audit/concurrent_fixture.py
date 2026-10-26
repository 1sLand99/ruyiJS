"""One loopback server presented as three distinct sites for a Fission message test."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

PARENT = Path(__file__).with_name('concurrent_parent.js').read_bytes()
FRAME_SCRIPT = b'''(() => {
  const worker = new Worker('/async-concurrent-worker.js');
  const state = window.frameProof = {received:0, returned:0};
  const parentOrigin = new URL(document.referrer).origin;
  function mark(label) {document.documentElement.setAttribute('data-concurrent-proof', label)}
  addEventListener('message', function frameReceive(event) {
    if(event.source!==parent || event.origin!==parentOrigin || event.data!=='ping')return;
    mark('frame:receive:'+(++state.received));
    Promise.resolve().then(function sendToWorker(){worker.postMessage('ping')});
  });
  worker.onmessage = function frameWorkerReceive(event) {
    if(event.data!=='pong')return;
    mark('frame:worker-receive:'+(++state.returned));
    Promise.resolve().then(function sendToParent(){parent.postMessage('pong', parentOrigin)});
  };
  parent.postMessage('ready', parentOrigin);
})();'''
WORKER_SCRIPT = b'''onmessage = function workerReceive(event) {
  if(event.data==='ping')Promise.resolve().then(function workerReply(){postMessage('pong')});
};'''
FRAME = b'<!doctype html><script src="/async-concurrent-frame.js"></script>'
START = b'startConcurrentProof();'
SCRIPT_RESOURCES = {'/async-concurrent-parent.js': PARENT,
    '/async-concurrent-frame.js': FRAME_SCRIPT, '/async-concurrent-worker.js': WORKER_SCRIPT,
    '/async-concurrent-start.js': START}
HOSTS = ('main.causal.test', 'one.causal-one.test', 'two.causal-two.test')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlsplit(self.path).path
        if path in SCRIPT_RESOURCES: mime,body='text/javascript',SCRIPT_RESOURCES[path]
        elif path=='/frame': mime,body='text/html',FRAME
        elif path=='/':
            port=self.server.server_port
            body=('<!doctype html><script src="/async-concurrent-parent.js" defer></script>'+
                ''.join(f'<iframe src="http://{host}:{port}/frame"></iframe>' for host in HOSTS[1:])).encode()
            mime='text/html'
        else:
            self.send_response(404);self.end_headers();return
        self.send_response(200);self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)
    def log_message(self,*_):pass


class Fixture:
    def __enter__(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origins=[f'http://{host}:{self.server.server_port}' for host in HOSTS]
        return self
    def __exit__(self,*_):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
