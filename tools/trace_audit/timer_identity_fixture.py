"""Local resources for timer lifecycle, frame isolation, cap and gate probes."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

MAPPING = Path(__file__).with_name('async_mapping.js').read_bytes()
EDGES = b'''window.timerProof={events:[],done:false,errors:[]};
function mark(s){timerProof.events.push(s);document.documentElement.setAttribute('data-timer-proof',s)}
addEventListener('error',e=>timerProof.errors.push(e.message));
window.runTimerEdges=function(){
 const a=document.querySelectorAll('iframe')[0].contentWindow;
 const b=document.querySelectorAll('iframe')[1].contentWindow;
 const aId=a.setTimeout(()=>mark('a'),0),bId=b.setTimeout(()=>mark('b'),0);
 timerProof.handles=[aId,bId];
 let n=0;const repeat=setInterval(()=>{mark('tick-'+(++n));if(n===3)clearInterval(repeat)},5);
 setTimeout("mark('string')",0);
 setTimeout(()=>{mark('end');timerProof.done=true},50);
 const doomed=document.querySelectorAll('iframe')[2];
 doomed.contentWindow.setTimeout(()=>mark('retired-ran'),1000);doomed.remove();
};'''
BENCH = b'''window.timerBench=function(n){
 let total=0;const start=performance.now();
 for(let i=0;i<n;i++){const id=setTimeout(()=>{},60000);clearTimeout(id);total+=i;}
 return {ms:performance.now()-start,checksum:total,count:n};
};'''
GATE = b'''window.gateProof={events:[],done:false};
window.runGate=function(label){setTimeout(()=>{gateProof.events.push(label);document.title=label;gateProof.done=true},0)};'''
RESOURCES = {
 '/mapping': ('text/html', b'<!doctype html><script src="/async-mapping.js"></script>'),
 '/async-mapping.js': ('text/javascript', MAPPING),
 '/edges': ('text/html', b'<!doctype html><iframe src="/blank"></iframe><iframe src="/blank"></iframe><iframe src="/blank"></iframe><script src="/async-timer-edges.js"></script>'),
 '/blank': ('text/html', b'<!doctype html><title>blank</title>'),
 '/async-timer-edges.js': ('text/javascript', EDGES),
 '/async-timer-start.js': ('text/javascript', b'runTimerEdges();'),
 '/bench': ('text/html', b'<!doctype html><script src="/async-timer-bench.js"></script>'),
 '/async-timer-bench.js': ('text/javascript', BENCH),
 '/async-timer-cost.js': ('text/javascript', b'window.benchResult={warmup:timerBench(200),samples:[timerBench(2000),timerBench(2000),timerBench(2000)]};'),
 '/gate': ('text/html', b'<!doctype html><script src="/async-timer-gate.js"></script>'),
 '/async-timer-gate.js': ('text/javascript', GATE),
 '/async-gate-closed.js': ('text/javascript', b"runGate('closed');"),
 '/async-gate-open.js': ('text/javascript', b"runGate('open');"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        mime, body = RESOURCES.get(self.path, ('text/plain', b'not found'))
        self.send_response(200 if self.path in RESOURCES else 404)
        self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass


class Fixture:
    def __enter__(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        return self
    def __exit__(self, *_):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
