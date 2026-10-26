"""Exercise get/set/static/native nesting and gate boundaries for deferred async evidence."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import time

from tools.firefox_parity.browser import Firefox
from .async_evidence import load_rows,analyze
from .rng_probe import digest

SETUP = b'window.edgeResult={done:false,order:[],value:null};'
CASES = {
    'get':"Promise.resolve().then(()=>{edgeResult.value=document.title;edgeResult.order.push('get');edgeResult.done=true})",
    'set':"Promise.resolve().then(()=>{document.title='set-value';edgeResult.order.push('set');edgeResult.done=true})",
    'static':"Promise.resolve().then(()=>{edgeResult.value=URL.canParse('https://example.test/x');edgeResult.order.push('static');edgeResult.done=true})",
    'nested':"""const target=new EventTarget();
      target.addEventListener('edge-local',()=>{document.title='inside';edgeResult.order.push('inside');
        queueMicrotask(()=>{document.title='micro';edgeResult.order.push('micro');edgeResult.done=true})});
      Promise.resolve().then(()=>{document.title='before';edgeResult.order.push('before');
        target.dispatchEvent(new Event('edge-local'));document.title='after';edgeResult.order.push('after')});"""
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        script=self.path.startswith('/async-')
        if self.path=='/async-setup.js':body=SETUP
        elif self.path=='/async-gate-before.js':body=b"Promise.resolve().then(()=>{document.title='closed';edgeResult.order.push('closed')});"
        elif script:body=CASES[self.path.removeprefix('/async-').removesuffix('.js')].encode()
        else:body=b'<!doctype html><title>probe-title</title><script src="/async-setup.js"></script>'
        self.send_response(200);self.send_header('Content-Type','text/javascript' if script else 'text/html')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*_):pass


def inject(browser,path):
    browser.evaluate("(()=>{const s=document.createElement('script');s.src="+json.dumps(path)+";document.head.appendChild(s);return null})()")


def wait_for(browser,expression):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if browser.evaluate(expression):return
        time.sleep(.02)
    raise TimeoutError('local async edge probe did not settle')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    executable=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe')
    report={'xul_sha256':digest(executable.with_name('xul.dll')),'cases':{}}
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for mode in ('get','set','static','nested','gate'):
            folder=output/mode;folder.mkdir()
            env={'MOZ_DOM_TRACE':'1','MOZ_DOM_TRACE_FILE':str(folder/'run.jsonl'),'MOZ_DOM_TRACE_OPERATORS':'0'}
            gate=folder/'gate'
            if mode=='gate':env.update(MOZ_DOM_TRACE_GATE=str(gate),MOZ_DOM_TRACE_GATE_POLL_MS='20')
            with Firefox(executable,folder/'profile',extra_environment=env) as browser:
                browser.navigate(f'http://127.0.0.1:{server.server_port}/')
                if mode=='gate':
                    inject(browser,'/async-gate-before.js');wait_for(browser,"edgeResult.order.includes('closed')")
                    gate.write_text('open','utf-8');time.sleep(.2)
                inject(browser,'/async-'+('set' if mode=='gate' else mode)+'.js')
                wait_for(browser,'edgeResult.done');page=browser.evaluate('edgeResult')
            rows,sources=load_rows(folder);proof=analyze(rows)
            visible=[row for row in rows if row.get('interface')=='Document' and
                     row.get('member') in ('get title','set title')]
            if mode=='static':visible=[row for row in rows if row.get('interface')=='URL' and row.get('member')=='canParse']
            assert visible,(mode,'no matching native observation')
            assert all(row.get('execution_context_id') and row.get('async_context_id') for row in visible)
            assert not proof['gaps'],proof['gaps']
            if mode=='nested':
                assert page['order']==['before','inside','after','micro']
                assert len({row['execution_context_id'] for row in visible[:3]})==1
                assert visible[-1]['execution_context_id']!=visible[0]['execution_context_id']
            if mode=='gate':
                assert page['order']==['closed','set']
                assert not any(row.get('value')=='closed' for row in visible)
                assert len(visible)==1
                admitted=[row for row in rows if row['type'] in ('get','set','call')
                          and row.get('execution_context_id')==0]
                assert admitted,'gate case needs observations outside a traced script root'
                assert all(row.get('trace_session')==1 for row in admitted)
                assert visible[0]['trace_session']==1
            if mode=='get':assert page['value']=='probe-title'
            if mode=='static':assert page['value'] is True
            report['cases'][mode]={'page':page,'proof':proof,'observations':visible,'sources':sources}
            (output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
            print(json.dumps({'mode':mode,'observations':len(visible),'gaps':len(proof['gaps'])}),flush=True)
        report['verified']=True
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':main()
