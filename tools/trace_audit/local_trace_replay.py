"""Replay recovered local fixture inputs through the existing Python and C runtimes."""
import argparse
import json
from pathlib import Path
import sys

from .rng_probe import digest
from .tier_fixture import HTML, SCRIPT

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
sys.path.insert(0,str(ROOT/'tests'))
from ruyijs import Context
from iframe_client import CClient


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('proof',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    proof=json.loads(args.proof.read_text('utf-8'))
    if proof.get('verified') is not True:raise ValueError('trace proof not complete')
    source=Path(__file__).with_name('tier_workload.js')
    if digest(source)!=proof['workload_sha256']:raise ValueError('source differs from verified capture')
    runs=[row for row in proof['runs'] if row['complete_sequence_checked']]
    if len(runs)!=3 or any(len(row['recovered_runs'])!=4 for row in runs):
        raise ValueError('expected three independently verified captures with four inputs each')
    for row in runs:
        if row['run_checksums']!=len(row['recovered_runs']):raise ValueError('unverified recovered run')
        for recovered in row['recovered_runs']:
            a=recovered['arguments']
            if len(a)!=2 or any(type(v) is not int or v<0 or v>500000 for v in a):
                raise ValueError('recovered workload exceeds local replay bound')
    if any(row['recovered_runs'] for row in proof['runs'] if not row['complete_sequence_checked']):
        raise ValueError('sparse capture was promoted to recovered full inputs')
    report={'schema':'local.static-trace-replay.v1','scope':'Only the fixed local integer/buffer fixture; no browser task replay.',
        'proof_sha256':digest(args.proof),'source_sha256':digest(source),
        'shell_sha256':digest(ROOT/'dist/js.exe'),'client_sha256':digest(ROOT/'dist/ruyijs_client.dll'),
        'cases':[],'full_goal_complete':False}
    args.output.mkdir(parents=True,exist_ok=False)
    url='http://localhost/local-trace-proof/'
    for row in runs:
        for adapter in ('Python','C'):
            client=Context(shell=ROOT/'dist/js.exe') if adapter=='Python' else CClient()
            try:
                client.configure_clock('logical',epoch_ms=1700000000000)
                client.put_resource('http://localhost/tier-workload.js',SCRIPT.decode('utf-8'),headers=[['Content-Type','application/javascript']])
                client.load_page(url,HTML.decode('utf-8'))
                outputs=[]
                for recovered in row['recovered_runs']:
                    a,b=recovered['arguments'];value=client.eval(f'tierBench.run({a},{b})')
                    if value['checksum']!=recovered['checksum']:raise ValueError('replay result differs from trace-derived checksum')
                    outputs.append({'arguments':[a,b],'checksum':value['checksum'],
                                    'recorded_call_id':recovered['run_call_id']})
                surface=client.eval('tierBench.surface()')
                if surface['gets'] or surface['traps'] or surface['types']!=['object','object']:
                    raise ValueError('local surface probe changed')
                report['cases'].append({'round':row['round'],'adapter':adapter,'outputs':outputs})
            finally:client.close()
    report['verified']=True
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps({'verified':True,'contexts':len(report['cases']),
        'trace_derived_runs':sum(len(c['outputs']) for c in report['cases']),'full_goal_complete':False}))


if __name__=='__main__':main()
