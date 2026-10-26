"""Build a reusable SQLite index of observed call ancestry from JSCT v1."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .binary import CALL, HEADER, header
from .jsonlines import dictionary


def key(value):
    return value.to_bytes(8, 'big')


def index(run, output):
    if output.exists():
        raise ValueError('index output already exists; use a new artifact path')
    output.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output)
    try:
        connection.executescript('''
            CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE processes(pid INTEGER PRIMARY KEY, nonce TEXT, run_id TEXT);
            CREATE TABLE functions(pid INTEGER, id INTEGER, data TEXT, PRIMARY KEY(pid,id));
            CREATE TABLE calls(pid INTEGER, id BLOB, parent BLOB, function INTEGER,
                duration INTEGER, depth INTEGER, argc INTEGER, flags INTEGER, entry INTEGER,
                PRIMARY KEY(pid,id)) WITHOUT ROWID;
            CREATE TABLE files(path TEXT PRIMARY KEY, bytes INTEGER, sha256 TEXT);
        ''')
        connection.execute('INSERT INTO metadata VALUES(?,?)', ('status', 'incomplete'))
        connection.execute('INSERT INTO metadata VALUES(?,?)', ('run', str(run.resolve())))
        connection.commit()
        total = 0
        for path in sorted((run / 'jscall').glob('*.bin')):
            if path.name.endswith('.detail.bin'):
                continue
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                pid = header(stream, b'JSCT', CALL.size)
                stream.seek(0)
                digest.update(stream.read(HEADER.size))
                init_file = run / 'domtrace' / f'trace_process_{pid}.jsonl'
                init = {}
                if init_file.exists():
                    with init_file.open('rb') as source:
                        declaration = source.readline()
                        init = json.loads(declaration)
                    if init.get('type') != 'trace_init' or init.get('pid') != pid:
                        raise ValueError('invalid process declaration: ' + str(init_file))
                    connection.execute('INSERT INTO metadata VALUES(?,?)',
                        ('process_declaration:' + str(pid), hashlib.sha256(declaration).hexdigest()))
                connection.execute('INSERT INTO processes VALUES(?,?,?)',
                    (pid, init.get('process_instance_id'), init.get('trace_run_id')))
                dict_path = path.with_name(path.stem + '.dict.jsonl')
                if not dict_path.exists():
                    raise ValueError('missing dictionary: ' + str(dict_path))
                funcs, stats, errors = dictionary(dict_path)
                if errors:
                    raise ValueError('malformed dictionary: ' + str(dict_path))
                connection.executemany('INSERT INTO functions VALUES(?,?,?)',
                    ((pid, identity, json.dumps(row)) for identity, row in funcs.items()))
                connection.execute('INSERT INTO files VALUES(?,?,?)', (dict_path.relative_to(run).as_posix(),
                    dict_path.stat().st_size, hashlib.sha256(dict_path.read_bytes()).hexdigest()))
                records = 0
                while data := stream.read(CALL.size * 16384):
                    if len(data) % CALL.size:
                        raise ValueError('incomplete call record: ' + str(path))
                    digest.update(data)
                    batch = [(pid, key(call), key(parent) if parent else None, func, duration, depth, argc, flags, entry)
                             for call, parent, func, duration, depth, argc, flags, entry, _ in CALL.iter_unpack(data)]
                    connection.executemany('INSERT INTO calls VALUES(?,?,?,?,?,?,?,?,?)', batch)
                    records += len(batch)
                if stats is None or records != stats.get('recorded'):
                    raise ValueError('writer record count mismatch or missing terminal stats: ' + str(path))
                connection.execute('INSERT INTO files VALUES(?,?,?)',
                    (path.relative_to(run).as_posix(), path.stat().st_size, digest.hexdigest()))
                connection.commit()
                total += records
                print(json.dumps({'pid': pid, 'records': records}), flush=True)
        connection.execute('INSERT INTO metadata VALUES(?,?)', ('created_utc', datetime.now(timezone.utc).isoformat()))
        connection.execute('INSERT INTO metadata VALUES(?,?)', ('records', str(total)))
        connection.execute("UPDATE metadata SET value='complete' WHERE name='status'")
        connection.commit()
        return total
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print('indexed_records:', index(args.run, args.output))


if __name__ == '__main__':
    main()
