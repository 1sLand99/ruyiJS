"""Execute captured GET resources in an isolated ruyijs runtime without Necko.

This is a divergence probe, not a deterministic replay: ambiguous URL responses,
input, time, RNG and asynchronous order are reported as unresolved inputs.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import urlsplit

from .network import body_bytes
from .request_diff import packet_requests, compare_body

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context


def digest(value):
    return hashlib.sha256(value).hexdigest()


def location_summary(url):
    parts = urlsplit(url)
    return {'host': parts.netloc, 'path': '/'.join(
        '{opaque}' if len(part) > 48 else part for part in parts.path.split('/'))}


def resources(run):
    packets = []
    for path in (run / 'http_packet').glob('*.http_packet.json'):
        obj = json.loads(path.read_text('utf-8'))
        obj['_file'] = path.name
        packets.append(obj)
    packets.sort(key=lambda o: (o['meta'].get('startMs', 0), o['meta'].get('seq', 0)))
    selected, conflicts = {}, []
    for obj in packets:
        if obj['method'] != 'GET':
            continue
        url = obj['url']
        if url in selected:
            previous = selected[url]
            if (previous['status'], previous['responseBody'].get('sha256')) != (obj['status'], obj['responseBody'].get('sha256')):
                conflicts.append({'url_sha256': digest(url.encode()),
                                  'first_file': previous['_file'], 'later_file': obj['_file']})
            continue
        selected[url] = obj
    documents = [o for o in packets if o['method'] == 'GET' and o['status'] == 200
                 and o['meta'].get('requestKind') == 'document']
    if not documents:
        raise ValueError('no captured top-level GET document with status 200')
    return selected, conflicts, documents[0]


def snapshot(context):
    return context.eval('''JSON.stringify({url:location.origin + location.pathname,
      ready:document.readyState, title:document.title,
      elements:document.querySelectorAll('*').length,
      frames:Array.from(document.querySelectorAll('iframe'), f => ({
        srcHashInput:f.src, loaded:!!f.contentWindow})),
      scripts:document.scripts.length})''')


def run_probe(run, output, shell, advance_ms, random_state=None, script_order=None, crypto_inputs=None,
              navigation_inputs=None, environment_inputs=None):
    output.mkdir(parents=True, exist_ok=False)
    isolated = output / 'runtime' / 'dist'
    isolated.mkdir(parents=True)
    shutil.copy2(shell, isolated / 'js.exe')
    for path in shell.parent.glob('*.dll'):
        shutil.copy2(path, isolated / path.name)
    if (isolated.parent / 'vendor').exists():
        raise ValueError('isolated runtime unexpectedly has transport helpers')
    expected_sha = digest(shell.read_bytes())
    if digest((isolated / 'js.exe').read_bytes()) != expected_sha:
        raise ValueError('isolated shell copy differs')
    selected, conflicts, document = resources(run)
    recorded_requests = packet_requests(run)
    report = {'schema': 'ruyijs.trace-replay-probe.v1', 'run': str(run.resolve()),
              'shell_sha256': expected_sha, 'status': 'incomplete',
              'network_mode': 'isolated runtime with no vendor/necko-derived/python/python.exe',
              'resource_policy': 'first observed GET response per exact URL',
              'conflicts': conflicts, 'imported_resources': 0, 'snapshots': [],
              'deterministic_replay_verified': False,
              'missing_inputs': ['recorded RNG and clocks', 'realm declarations',
                                 'input dispatch and task schedule replay',
                                 'request method/body/occurrence matching']}
    if random_state is not None:
        report['initial_random_state'] = {
            'evidence': str(random_state.resolve()),
            'evidence_sha256': digest(random_state.read_bytes()),
            'scope': 'inferred initial main-page state only; all other inputs remain unresolved'}
    order = None
    if script_order is not None:
        order = json.loads(script_order.read_text('utf-8'))['urls']
        report['replay_script_order'] = {'path': str(script_order.resolve()),
                                        'sha256': digest(script_order.read_bytes())}
    try:
        with Context(shell=isolated / 'js.exe', timeout=30) as context:
            if environment_inputs is not None:
                plan=json.loads(environment_inputs.read_text('utf-8'))
                context.configure_environment(plan['environment'])
                report['environment_inputs']={'file':str(environment_inputs.resolve()),
                    'sha256':digest(environment_inputs.read_bytes()),'scope':plan.get('scope')}
            if navigation_inputs is not None:
                plan=json.loads(navigation_inputs.read_text('utf-8'))
                context.configure_navigation_replay(plan['documents'])
                report['navigation_inputs']={'file':str(navigation_inputs.resolve()),
                    'sha256':digest(navigation_inputs.read_bytes()),'scope':plan.get('scope')}
            if crypto_inputs is not None:
                plan=json.loads(crypto_inputs.read_text('utf-8'))
                context.configure_crypto_replay(plan['documents'])
                report['crypto_inputs']={'file':str(crypto_inputs.resolve()),'sha256':digest(crypto_inputs.read_bytes())}
            if random_state is not None:
                state = json.loads(random_state.read_text('utf-8'))
                context.configure_random(state['state0'], state['state1'])
            context.configure_clock('logical', epoch_ms=document['meta']['startMs'])
            for url, obj in selected.items():
                body = obj['responseBody']
                data = body_bytes(body)
                if body.get('truncated') or digest(data) != body.get('sha256'):
                    raise ValueError('captured response is truncated or hash differs: ' + obj['_file'])
                headers = [[h['name'], h['value']] for h in obj['responseHeaders']
                           if h['name'].lower() not in ('content-encoding', 'content-length', 'transfer-encoding')]
                context.put_resource(url, data, status=obj['status'], headers=headers)
                report['imported_resources'] += 1
            try:
                context.load_page(document['url'], body_bytes(document['responseBody']).decode('utf-8'),
                                  replay_async_scripts=order)
            except Exception:
                if crypto_inputs is not None and not context.closed:
                    report['crypto_consumption']=context.crypto_replay_status()
                raise
            for tick in range(0, advance_ms + 1, 100):
                if tick:
                    context.advance(100, max_tasks=10000)
                data = json.loads(snapshot(context))
                for frame in data['frames']:
                    frame['src_sha256'] = digest(frame.pop('srcHashInput').encode())
                report['snapshots'].append({'logical_advance_ms': tick, **data})
            log = context.net_log()
            report['requests'] = [{'method': row['method'], **location_summary(row['url']),
                                   'url_sha256': digest(row['url'].encode()),
                                   'body_sha256': digest(row.get('requestBody', '').encode()),
                                   'status': row['status'], 'matched': row['matched']}
                                  for row in log]
            report['request_counts'] = dict(Counter('matched' if r['matched'] else 'unmatched' for r in log))
            for row,raw in zip(report['requests'],log):
                candidates = recorded_requests.get((row['method'], row['url_sha256']), [])
                row.update(compare_body(raw.get('requestBody',''),candidates))
            report['console'] = context.console_log()
            if crypto_inputs is not None:
                report['crypto_consumption']=context.crypto_replay_status()
            if navigation_inputs is not None:
                report['navigation_binding']=context.navigation_replay_status()
            report['status'] = 'probe_finished'
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)[:2000]}
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', 'utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--shell', type=Path, default=ROOT / 'dist/js.exe')
    parser.add_argument('--advance-ms', type=int, default=1000)
    parser.add_argument('--random-state', type=Path, help='inferred/recorded state JSON with state0 and state1 hex words')
    parser.add_argument('--script-order', type=Path, help='recorded async classic order JSON with urls list')
    parser.add_argument('--crypto-inputs',type=Path,help='document-bound recorded random byte inputs')
    parser.add_argument('--navigation-inputs',type=Path,help='document-bound recorded navigation measurements')
    parser.add_argument('--environment-inputs',type=Path,help='explicit existing native environment profile inputs')
    args = parser.parse_args()
    report = run_probe(args.run, args.output.resolve(), args.shell.resolve(), args.advance_ms,
                       args.random_state, args.script_order, args.crypto_inputs, args.navigation_inputs,
                       args.environment_inputs)
    print(json.dumps({k: report[k] for k in ('status', 'imported_resources', 'request_counts', 'error') if k in report}, indent=2))


if __name__ == '__main__':
    main()
