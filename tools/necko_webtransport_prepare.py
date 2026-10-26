"""Prepare the original Neqo bridge with owned WebTransport command extensions."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DONOR = Path('D:/firefox/src/firefox/obj-necko/source-v20/quic')
BASE = ROOT / 'vendor/necko-native/h3'
BUILD = ROOT / 'build/native-webtransport'
SOURCE = BUILD / 'source'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Neqo bridge base drift: ' + repr(old[:100]))
    return text.replace(old, new, 1)


def prepare():
    baseline = json.loads((BASE / 'source-baseline.json').read_text('utf8'))
    baseline.update(json.loads((BASE / 'patch-manifest.json').read_text('utf8'))['outputs'])
    sources = {}
    for name, digest in baseline.items():
        source = BASE / 'source' / name
        if not source.is_file():
            source = DONOR / name
        if sha(source) != digest:
            raise ValueError('Neqo accepted input changed: ' + name)
        sources[name] = {'source':str(source),'sha256':digest}
    for name, record in sources.items():
        target = SOURCE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or sha(target) != record['sha256']:
            shutil.copyfile(record['source'], target)
    path = SOURCE / 'src/lib.rs'
    text = path.read_text('utf8')
    text = replace(text, 'mod bridge_events;', 'mod bridge_events;\nmod webtransport_commands;\nmod webtransport_events;')
    text = replace(text, '        ech: String,\n', '        ech: String,\n        #[serde(default)]\n        webtransport: bool,\n')
    text = replace(text, '    Info,\n', '    Info,\n    Webtransport { #[serde(flatten)] command: webtransport_commands::Command },\n')
    text = replace(text, '    ech: String,\n)', '    ech: String,\n    webtransport: bool,\n)')
    text = replace(text, '.webtransport(false)', '.webtransport(webtransport)')
    text = replace(text, '    resource_error: bool,', '    resource_error: bool,\n    bytes_sent: u64,')
    text = replace(text, '        resource_error: false,', '        resource_error: false,\n        bytes_sent: 0,')
    text = replace(text, '            Ok(()) => {}', '            Ok(()) => { client.bytes_sent = client.bytes_sent.saturating_add(packet.data().len() as u64); }')
    text = replace(text, '        ech,\n    }', '        ech,\n        webtransport,\n    }')
    text = replace(text, 'create(host, local, remote, token, ech)?', 'create(host, local, remote, token, ech, webtransport)?')
    text = replace(text, '            Command::Info =>', '''            Command::Webtransport { command } => {
                let is_info = matches!(command, webtransport_commands::Command::Info { .. });
                let mut value = webtransport_commands::dispatch(http, command, now)?;
                if is_info { value["bytesSent"] = json!(client.bytes_sent); }
                Ok(value)
            },
            Command::Info =>''')
    path.write_text(text, 'utf8')
    path = SOURCE / 'src/bridge_events.rs'
    text = replace(path.read_text('utf8'), '            _ => continue,',
                   '            Http3ClientEvent::WebTransport(event) => super::webtransport_events::value(event),\n            _ => continue,')
    path.write_text(text, 'utf8')
    path = SOURCE / 'src/event_json_cost.rs'
    text = replace(path.read_text('utf8'), '        _ => 512,',
                   '        Http3ClientEvent::WebTransport(event) => super::webtransport_events::cost(event),\n        _ => 512,')
    path.write_text(text, 'utf8')
    for name in ('webtransport_commands.rs','webtransport_events.rs'):
        source = ROOT / 'transport/necko/native' / name
        shutil.copyfile(source, SOURCE / 'src' / name)
        sources['owned/' + name] = {'source':str(source),'sha256':sha(source)}
    report = {'sourceInputs':sources, 'preparedInputs':{
        p.relative_to(SOURCE).as_posix():sha(p) for p in SOURCE.rglob('*') if p.is_file()},
        'generatorSHA256':sha(Path(__file__))}
    (BUILD / 'prepare.json').write_text(json.dumps(report,indent=2),'utf8')
    return report


if __name__ == '__main__':
    result = prepare()
    print(json.dumps({'prepared':len(result['preparedInputs']),'path':str(SOURCE)}))
