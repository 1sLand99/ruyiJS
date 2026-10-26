"""Trace every captured HTTP request backwards through its observed call ancestors."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from .chain_index import key


def ancestors(db, pid, identity, nonce=None, maximum=256):
    process = db.execute('SELECT nonce FROM processes WHERE pid=?', (pid,)).fetchone()
    if not process:
        return {'status': 'missing_process', 'calls': []}
    if nonce and process[0] != nonce:
        return {'status': 'process_instance_mismatch', 'calls': []}
    chain, seen = [], set()
    while identity:
        if identity in seen:
            return {'status': 'cycle', 'calls': chain}
        if len(chain) >= maximum:
            return {'status': 'depth_limit', 'calls': chain}
        seen.add(identity)
        row = db.execute('SELECT parent,function,duration,depth,argc,flags,entry FROM calls WHERE pid=? AND id=?',
                         (pid, key(identity))).fetchone()
        if not row:
            return {'status': 'missing_call', 'missing_call_id': str(identity), 'calls': chain}
        parent, func, duration, depth, argc, flags, entry = row
        record = db.execute('SELECT data FROM functions WHERE pid=? AND id=?', (pid, func)).fetchone()
        function = json.loads(record[0]) if record else {}
        url = function.get('url', '')
        parsed = urlsplit(url)
        chain.append({'call_id': str(identity), 'parent_call_id': str(int.from_bytes(parent, 'big')) if parent else None,
                      'function_id': func, 'name': function.get('name'), 'kind': function.get('kind'),
                      'script_host': parsed.netloc, 'script_url_sha256': hashlib.sha256(url.encode()).hexdigest(),
                      'line': function.get('line'), 'column': function.get('column'),
                      'caller_jit_gap': bool(flags & 64), 'ok': bool(flags & 2),
                      'entry_path': entry, 'duration_us': duration, 'depth': depth, 'argc': argc})
        identity = int.from_bytes(parent, 'big') if parent else 0
    return {'status': 'observed_root', 'calls': chain,
            'has_jit_gap': any(row['caller_jit_gap'] for row in chain),
            'meaning': 'nearest recorded ancestors, not a complete direct-call stack'}


def build_report(run, database):
    db = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        metadata = dict(db.execute('SELECT name,value FROM metadata'))
        if metadata.get('status') != 'complete' or Path(metadata['run']).resolve() != run.resolve():
            raise ValueError('index is incomplete or belongs to a different run')
        for name, expected in metadata.items():
            if name.startswith('process_declaration:'):
                pid = int(name.split(':', 1)[1])
                with (run / 'domtrace' / f'trace_process_{pid}.jsonl').open('rb') as stream:
                    if hashlib.sha256(stream.readline()).hexdigest() != expected:
                        raise ValueError('indexed process declaration changed: ' + str(pid))
        for relative, size, expected in db.execute('SELECT path,bytes,sha256 FROM files'):
            source = (run / relative).resolve()
            if not source.is_relative_to(run.resolve()) or source.stat().st_size != size:
                raise ValueError('indexed input changed: ' + relative)
            with source.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError('indexed input changed: ' + relative)
        packets = []
        for path in sorted((run / 'http_packet').glob('*.http_packet.json')):
            obj = json.loads(path.read_text('utf-8'))
            meta = obj['meta']
            identity = meta.get('originCallId', 0)
            chain = ancestors(db, meta.get('originPid', 0), identity,
                              meta.get('originProcessInstanceId')) if identity else {'status': 'no_origin_call', 'calls': []}
            packets.append({'file': path.name, 'method': obj['method'], 'http_status': obj['status'],
                            'host': urlsplit(obj['url']).netloc,
                            'request_kind': meta.get('requestKind'), 'origin_pid': meta.get('originPid'),
                            'origin_execution_context_id': meta.get('originExecutionContextId'),
                            'origin_async_context_id': meta.get('originAsyncContextId'),
                            'packet_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), **chain})
        return {'schema': 'ruyijs.http-observed-ancestry.v1', 'index': str(database.resolve()),
                'run': str(run.resolve()), 'packets': packets,
                'complete_execution_chain_verified': False,
                'counts': {status: sum(p['status'] == status for p in packets)
                           for status in sorted({p['status'] for p in packets})}}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.run, args.index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps(report['counts']))


if __name__ == '__main__':
    main()
