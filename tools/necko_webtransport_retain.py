"""Retain the verified original H3 bridge candidate and inspectable build inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'vendor/necko-native'
BUILD=ROOT/'build/native-webtransport'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report_path=args.report.resolve()
    report=json.loads(report_path.read_text('utf8'))
    binary=Path(report['candidate']['path'])
    if not report['passed'] or report['candidate']['sha256']!=sha(binary):
        raise ValueError('WebTransport build identity changed')
    probes=['bridge-probe.json','session-probe.json','certificate-probe.json','helper-probe.json']
    evidence={}
    for name in probes:
        path=ROOT/'artifacts/native-four/webtransport'/name
        data=json.loads(path.read_text('utf8'))
        if not all(data['checks'].values()):raise ValueError('WebTransport acceptance failed: '+name)
        if 'candidateSHA256' in data and data['candidateSHA256']!=sha(binary):
            raise ValueError('Protocol probe used another binary')
        evidence[name]=sha(path)
    manifest=BASE/'manifest.json';data=json.loads(manifest.read_text('utf8'))
    old=data['components']['h3'].copy()
    if old['binary_sha256']==sha(binary):
        print(json.dumps({'retained':True,'sha256':sha(binary),'unchanged':True}));return
    backup=BUILD/('retained-before-'+sha(binary)[:12])
    backup.mkdir(exist_ok=True)
    shutil.copyfile(manifest,backup/'manifest.json')
    shutil.copyfile(BASE/old['binary'],backup/'necko_quic.dll')
    additions={}
    for name in ('src/lib.rs','src/bridge_events.rs','src/event_json_cost.rs',
                 'src/webtransport_commands.rs','src/webtransport_events.rs'):
        additions['h3/webtransport/source/'+name]=BUILD/'source'/name
    for name in ('necko_webtransport_prepare.py','necko_webtransport_build.py','necko_webtransport_retain.py'):
        additions['h3/webtransport/tools/'+name]=ROOT/'tools'/name
    additions['h3/webtransport/prepare.json']=BUILD/'prepare.json'
    additions['h3/webtransport/build.json']=report_path
    additions['h3/webtransport/build.log']=Path(report['log'])
    for name in probes:additions['h3/webtransport/evidence/'+name]=ROOT/'artifacts/native-four/webtransport'/name
    record=BASE/'h3/webtransport/accepted.json';record.parent.mkdir(parents=True,exist_ok=True)
    record.write_text(json.dumps({'schema':1,'previousComponent':old,'binarySHA256':sha(binary),
        'buildSHA256':sha(report_path),'evidence':evidence,
        'scope':'Original Neqo bridge and Python helper; JS API acceptance follows product build'},indent=2)+'\n','utf8')
    additions['h3/webtransport/accepted.json']=record
    for name,source in additions.items():
        dest=BASE/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if source.resolve()!=dest.resolve():shutil.copyfile(source,dest)
        data['files'][name]={'component':'h3','kind':'source' if '/source/' in name else 'build-record',
            'output':'provenance/necko-native/'+name,'sha256':sha(dest)}
    shutil.copyfile(binary,BASE/old['binary'])
    data['files'][old['binary']]['sha256']=sha(binary)
    data['components']['h3'].update(binary_sha256=sha(binary),
        historical_manifest='h3/webtransport/accepted.json',historical_manifest_sha256=sha(record))
    manifest.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n','utf8')
    print(json.dumps({'retained':True,'sha256':sha(binary),'manifestSHA256':sha(manifest),'backup':str(backup)}))

if __name__=='__main__':main()
