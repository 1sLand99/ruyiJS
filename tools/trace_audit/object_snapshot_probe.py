"""Compare native object snapshots and no-snapshot behavior on local page objects."""
import argparse
from collections import Counter
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import struct
import random
import statistics
from threading import Thread

from tools.firefox_parity.browser import Firefox

SCRIPT=Path(__file__).with_name('object_snapshot_fixture.js').read_bytes()
ROOT=Path(__file__).resolve().parents[2]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data=SCRIPT if self.path=='/snapshot.js' else b'<!doctype html><script src="/snapshot.js"></script>'
        self.send_response(200)
        self.send_header('Content-Type','text/javascript' if self.path=='/snapshot.js' else 'text/html')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)
    def log_message(self,*_):pass


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def decode(folder,decoder):
    snapshots=[];stats=[];kinds=Counter();buffers=[]
    for path in (folder/'jscall').glob('*.dict.jsonl'):
        functions,summary=decoder.load_dict(path)
        if summary:stats.append(summary)
        prefix=path.name.removesuffix('.dict.jsonl')
        calls={}
        binary=path.with_name(prefix+'.bin')
        if binary.exists():
            with binary.open('rb') as stream:
                stream.read(16)
                for row in struct.iter_unpack('<QQIIHHBBH',stream.read()):calls[row[0]]=row[2]
        detail=path.with_name(prefix+'.detail.bin')
        if not detail.exists():continue
        for call,slots in decoder.load_detail(detail).items():
            for slot,value in slots.items():
                kinds[value['type']]+=1
                if value['type']=='typedarray':buffers.append(value)
                if value['type']=='object_snapshot':
                    function=functions.get(calls.get(call),{})
                    snapshots.append({'call_id':str(call),'slot':slot,'function':function.get('name'),**value})
    return {'snapshots':snapshots,'types':dict(kinds),'stats':stats,'buffers':buffers}


def main():
    global SCRIPT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--firefox',type=Path,default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    parser.add_argument('--decoder',type=Path,default=Path('D:/firefox/src/firefox/dom/bindings/domtrace/jscall_decode.py'))
    parser.add_argument('--benchmark',action='store_true')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    if args.benchmark:SCRIPT=Path(__file__).with_name('object_snapshot_bench.js').read_bytes()
    spec=importlib.util.spec_from_file_location('jscall_decoder',args.decoder);decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    report={'firefox_sha256':digest(args.firefox),'xul_sha256':digest(args.firefox.with_name('xul.dll')),
            'source_sha256':hashlib.sha256(SCRIPT).hexdigest(),'modes':{}}
    cases=[(mode,mode) for mode in ['off','detail','objects','limit','small','independent','excluded']]
    if args.benchmark:
        cases=[];rng=random.Random(20261024)
        for repeat in range(3):
            order=['off','detail','objects'];rng.shuffle(order)
            cases.extend((str(repeat)+'-'+mode,mode) for mode in order)
    try:
        for label,mode in cases:
            folder=output/label;folder.mkdir()
            env={} if mode=='off' else {'MOZ_DOM_TRACE':'1','MOZ_DOM_TRACE_FILE':str(folder/'run.jsonl'),
                'MOZ_DOM_TRACE_OPERATORS':'0',
                'MOZ_DOM_JSCALL_TRACE':'1','MOZ_DOM_JSCALL_SCRIPT_URL':'web','MOZ_DOM_JSCALL_DETAIL_SCRIPT_URL':'web'}
            if mode in ['objects','limit','small','independent','excluded']:
                env['MOZ_DOM_JSCALL_OBJECT_FUNCS']='missingName' if mode=='excluded' else 'snapshotTarget;snapshotReturn'
                env['MOZ_DOM_JSCALL_OBJECT_LIMIT']='3' if mode=='limit' else '64'
            if mode=='small':env['MOZ_DOM_JSCALL_MAX_VALUE_BYTES']='256'
            if mode=='independent':env['MOZ_DOM_TRACE']='0'
            with Firefox(args.firefox,folder/'profile',extra_environment=env) as browser:
                browser.navigate(f'http://127.0.0.1:{server.server_port}/')
                result=browser.evaluate('snapshotResult')
            records=decode(folder,decoder)
            report['modes'][label]={'page':result,'settings':env,'mode':mode,**records}
            (output/'result.json').write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n','utf-8')
            print(json.dumps({'mode':label,'snapshots':len(records['snapshots']),'traps':result['traps'],'getters':result['gets']}),flush=True)
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
    canonical=lambda value:{k:v for k,v in value.items() if k!='samples'}
    reference=canonical(next(iter(report['modes'].values()))['page'])
    report['page_results_equal']=all(canonical(x['page'])==reference for x in report['modes'].values())
    report['capture_present']=all(value['stats'] for value in report['modes'].values() if value['mode']!='off')
    if args.benchmark:
        report['median_ms']={mode:statistics.median(sample for v in report['modes'].values() if v['mode']==mode
            for sample in v['page']['samples']) for mode in ['off','detail','objects']}
        report['limitations']=['local microbenchmark; JIT call coverage must be assessed separately',
                              'each timing is quantized by page clock precision; no zero-overhead claim']
        report['expected_target_invocations_per_process']=12000000
    (output/'result.json').write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n','utf-8')
    print('page_results_equal:',report['page_results_equal'])
    if not report['capture_present']:raise RuntimeError('capture missing; behavior equality is not validation')


if __name__=='__main__':main()
