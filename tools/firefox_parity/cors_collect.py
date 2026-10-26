"""Real-network CORS parity for Window, iframe and dedicated Worker."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from browser import Firefox
from cors_fixture import CorsFixture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def start(probe, target, same_origin):
    args = json.dumps(target) + ',' + json.dumps(same_origin)
    direct = '(' + probe + ')(window,' + args + ')'
    worker = '(' + probe + ')(self,' + args + ').then(value=>postMessage(value))'
    return '''(() => {
      const top = window.top;
      top.corsResults = {};
      top.corsDone = false;
      const frame = document.querySelector('iframe').contentWindow;
      Promise.all([
        window.eval(DIRECT).then(value => top.corsResults.window = value),
        frame.eval(DIRECT).then(value => top.corsResults.iframe = value).catch(error => top.corsResults.iframeError=String(error)),
        new Promise(resolve => {
          const url = URL.createObjectURL(new Blob([WORKER], {type:'text/javascript'}));
          top.corsWorker = new Worker(url);
          top.corsWorker.onmessage = event => {top.corsResults.worker = event.data; resolve();};
          top.corsWorker.onerror = event => {top.corsResults.workerError = event.message; resolve();};
        })
      ]).then(() => top.corsDone = true, error => {top.corsResults.error = String(error); top.corsDone = true;});
      return true;
    })()'''.replace('DIRECT', json.dumps(direct)).replace('WORKER', json.dumps(worker))


def collect(evaluate, advance=None, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if advance:
            advance(20, max_tasks=100)
        value = json.loads(evaluate('JSON.stringify({done:corsDone,results:corsResults})'))
        if value['done']:
            return value['results']
        time.sleep(.02)
    raise TimeoutError('CORS probes exceeded deadline: ' + json.dumps(value))


def difference(expected, actual, path=''):
    if type(expected) is not type(actual):
        return [{'path':path, 'firefox':expected, 'ruyijs':actual}]
    if isinstance(expected, dict):
        output = []
        for key in sorted(set(expected) | set(actual)):
            output += difference(expected.get(key), actual.get(key), path + '/' + key)
        return output
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [{'path':path, 'firefox':expected, 'ruyijs':actual}]
        output = []
        for index, (left, right) in enumerate(zip(expected, actual)):
            output += difference(left, right, path + '/' + str(index))
        return output
    return [] if expected == actual else [{'path':path, 'firefox':expected, 'ruyijs':actual}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firefox', type=Path,
                        default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    parser.add_argument('--shell', type=Path, default=ROOT/'dist/js.exe')
    parser.add_argument('--assert-equal', action='store_true')
    args = parser.parse_args()
    folder = args.output.resolve()
    if not folder.is_relative_to(ROOT/'artifacts'):
        parser.error('output must be below artifacts')
    folder.mkdir(parents=True, exist_ok=False)
    probe_path = Path(__file__).with_name('cors_probe.js')
    probe = probe_path.read_text(encoding='utf8')
    metadata = {'createdUTC':datetime.now(timezone.utc).isoformat(),
                'shell':str(args.shell.resolve()), 'shellSha256':hashlib.sha256(args.shell.read_bytes()).hexdigest(),
                'firefox':str(args.firefox.resolve()), 'probeSha256':hashlib.sha256(probe_path.read_bytes()).hexdigest()}
    with CorsFixture() as fixture:
        metadata['origins'] = {'page':fixture.page, 'target':fixture.target}
        expression = start(probe, fixture.target, fixture.page)
        with Firefox(args.firefox, folder/'profile') as browser:
            browser.navigate(fixture.page+'/')
            browser.evaluate(expression)
            expected = collect(browser.evaluate)
            save(folder/'firefox.json', expected)
            metadata['capabilities'] = browser.capabilities
        with Context(shell=args.shell, timeout=45) as context:
            context.put_resource(fixture.page+'/frame', '<!doctype html><title>CORS frame</title>',
                                 headers=[['Content-Type','text/html; charset=utf-8']])
            context.load_page(fixture.page+'/', '<!doctype html><title>CORS parity</title><iframe src="/frame"></iframe>')
            context.eval(expression)
            actual = collect(context.eval, context.advance)
            save(folder/'ruyijs.json', actual)
            save(folder/'network.json', context.net_log())
    diffs = difference(expected, actual)
    save(folder/'metadata.json', metadata)
    save(folder/'differences.json', diffs)
    print(json.dumps({'output':str(folder), 'differences':len(diffs),
                      'casesPerRealm':10, 'realms':['window','iframe','worker']}, indent=2))
    if args.assert_equal and diffs:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
