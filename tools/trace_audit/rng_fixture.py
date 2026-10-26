"""Local realm/script-boundary RNG workload, including a gate-paused prefix."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread

FIRST = '''globalThis.result={first:[],surface:Math.random.toString(),own:Object.getOwnPropertyDescriptor(Math,'random')};
for(let i=0;i<8;i++)result.first.push(Math.random());'''
SECOND = '''result.last=[];result.values=[];let total=0;function draw(){return Math.random()}
for(let i=0;i<20000;i++){const n=draw();total+=n;result.values.push(n);if(i>=19992)result.last.push(n)}
result.sum=total;result.done=true;'''
RESOURCES={
 '/':('text/html','<!doctype html><script src="/rng-main-first.js"></script><script src="/rng-main-second.js"></script><iframe src="/frame"></iframe><iframe src="/frame"></iframe><script src="/rng-start-worker.js"></script>'),
 '/frame':('text/html','<!doctype html><script src="/rng-frame-first.js"></script><script src="/rng-frame-second.js"></script>'),
 '/gate':('text/html','<!doctype html><script src="/rng-gate-first.js"></script>'),
 '/rng-main-first.js':('text/javascript',FIRST),
 '/rng-main-second.js':('text/javascript',SECOND),
 '/rng-frame-first.js':('text/javascript',FIRST),
 '/rng-frame-second.js':('text/javascript',SECOND),
 '/rng-gate-first.js':('text/javascript',FIRST),
 '/rng-gate-second.js':('text/javascript',SECOND),
 '/rng-worker-first.js':('text/javascript',FIRST+";importScripts('/rng-worker-second.js');delete result.own;postMessage(result)"),
 '/rng-worker-second.js':('text/javascript',SECOND),
 '/rng-start-worker.js':('text/javascript',"window.workerResult=null;window.worker=new Worker('/rng-worker-first.js');worker.onmessage=e=>workerResult=e.data;"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        mime,body=RESOURCES.get(self.path,('text/plain','not found'))
        encoded=body.encode();self.send_response(200)
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(encoded)))
        self.end_headers();self.wfile.write(encoded)
    def log_message(self,*_):pass


class Fixture:
    def __enter__(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        return self
    def __exit__(self,*_):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
