"""Count known fixture functions, caller gaps and value records from binary traces."""
from collections import Counter

from .binary import CALL, VALUE, PATHS, header
from .jsonlines import dictionary


def collect(folder):
    counts, paths, detail_counts, drops = Counter(), Counter(), Counter(), Counter()
    function_tiers = []
    total_calls = writer_calls = caller_gaps = detail_bytes = 0
    files = []
    for directory in ('domtrace','jscall','descriptor','event','eval','exception','storage','cookie','wasm'):
        base = folder/directory
        if base.exists(): files += [p for p in base.rglob('*') if p.is_file()]
    dictionaries = list((folder/'jscall').glob('*.dict.jsonl'))
    for path in dictionaries:
        functions, stats, errors = dictionary(path)
        if errors or not stats: raise ValueError('missing or malformed terminal dictionary statistics')
        writer_calls += stats['recorded']
        for key in ('dropped_limit','dropped_gate','dropped_no_func_id','dropped_chunks','io_errors'):
            drops[key] += stats.get(key, 0)
        selected = {key:value for key,value in functions.items()
                    if value.get('url','').endswith('/tier-workload.js')}
        function_tiers += [{key: row.get(key) for key in ('name','tiers','warmup_max','records')}
                          for row in selected.values() if row.get('name') in ('measuredLeaf','measuredBytes')]
        prefix = path.name.removesuffix('.dict.jsonl')
        with path.with_name(prefix+'.bin').open('rb') as stream:
            pid = header(stream,b'JSCT',CALL.size)
            while block := stream.read(CALL.size*16384):
                if len(block)%CALL.size: raise ValueError('truncated call binary')
                for call,parent,function,duration,depth,argc,flags,entry,_ in CALL.iter_unpack(block):
                    total_calls += 1
                    if function not in functions: raise ValueError('unknown function id')
                    if function in selected:
                        counts[selected[function].get('name','')] += 1
                        paths[PATHS.get(entry,str(entry))] += 1
                        caller_gaps += bool(flags&64)
        detail = path.with_name(prefix+'.detail.bin')
        if detail.exists():
            size = detail.stat().st_size; detail_bytes += size
            with detail.open('rb') as stream:
                if header(stream,b'JSCV',VALUE.size) != pid: raise ValueError('value process mismatch')
                while block := stream.read(VALUE.size):
                    if len(block)!=VALUE.size: raise ValueError('truncated value header')
                    call,slot,kind,flags,length=VALUE.unpack(block)
                    if stream.tell()+length>size: raise ValueError('truncated value payload')
                    detail_counts['records']+=1
                    detail_counts['truncated']+=bool(flags&1)
                    detail_counts['unreadable']+=bool(flags&2)
                    stream.seek(length,1)
    if total_calls != writer_calls: raise ValueError('writer/call binary count mismatch')
    return {'functions':dict(counts),'call_records':total_calls,'writer_records':writer_calls,
        'dictionary_count':len(dictionaries),'entry_paths':dict(paths),'caller_jit_gaps':caller_gaps,
        'function_tiers':function_tiers,'detail':dict(detail_counts),'detail_bytes':detail_bytes,
        'writer_drops':dict(drops),'trace_bytes':sum(p.stat().st_size for p in files)}
