"""Prepare source-validated bytecode in the existing standalone Necko Python."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess


def prepare(root):
    root=Path(root).resolve()
    runtime=(root/'vendor/necko-derived/python').resolve()
    if not runtime.is_relative_to(root):
        raise ValueError('Necko runtime must remain inside the product root')
    library=(runtime/'Lib').resolve()
    if not library.is_relative_to(runtime):
        raise ValueError('Necko library must remain inside the runtime')
    executable=runtime/'python.exe'
    sources=sorted(library.rglob('*.py'))
    before={str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in sources}
    command=[str(executable),'-I','-B','-m','compileall','-q','-f',
             '--invalidation-mode','checked-hash',str(library)]
    subprocess.run(command,check=True,timeout=120)
    if before!={str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in sources}:
        raise RuntimeError('Necko source changed during bytecode preparation')
    caches=sorted(library.rglob('*.pyc'))
    for path in caches:
        if struct.unpack('<I',path.read_bytes()[4:8])[0]!=3:
            raise ValueError('Bytecode is not checked-hash: '+str(path))
    return dict(runtime=str(runtime),pythonSHA256=sha256(executable.read_bytes()).hexdigest(),
                command=command,sourceSHA256=before,sourceCount=len(sources),
                cacheCount=len(caches),invalidation='checked-hash')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();report=prepare(args.root)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2),'utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='sourceSHA256'}))


if __name__=='__main__':main()
