"""Exercise RNG filtering, bounded records and replaced frame identities."""
import argparse
import json
from pathlib import Path
import time

from tools.firefox_parity.browser import Firefox
from .rng_fixture import Fixture, RESOURCES
from .rng_probe import digest, records
from .verify_rng import advance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firefox', type=Path,
                        default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'xul_sha256': digest(args.firefox.with_name('xul.dll')), 'modes': {}}
    RESOURCES['/life'] = ('text/html', '<!doctype html><script src="/rng-frame-first.js"></script>')
    RESOURCES['/rng-limit-page'] = ('text/html', '<!doctype html>' + '<script>Math.random()</script>' * 4200)
    with Fixture() as fixture:
        for mode in ('unset', 'excluded', 'core-off', 'frames', 'limit'):
            folder = output / mode
            folder.mkdir()
            env = {'MOZ_DOM_TRACE': '0' if mode == 'core-off' else '1',
                   'MOZ_DOM_TRACE_FILE': str(folder / 'run.jsonl'), 'MOZ_DOM_TRACE_OPERATORS': '0'}
            if mode != 'unset':
                env['MOZ_DOM_RNG_TRACE_URL'] = '/absent-rng-source/' if mode == 'excluded' else '/rng-'
            with Firefox(args.firefox, folder / 'profile', extra_environment=env) as browser:
                browser.navigate(fixture.origin + ('/rng-limit-page' if mode == 'limit' else '/gate'))
                values = None
                if mode == 'frames':
                    browser.evaluate('''(() => {
                      window.edgeValues=[];
                      function next(){
                        const f=document.createElement('iframe');f.src='/life';
                        f.onload=()=>{edgeValues.push(f.contentWindow.result.first[0]);f.remove();
                          if(edgeValues.length<24)next()};
                        document.body.appendChild(f);
                      }
                      next();return null;
                    })()''')
                    deadline = time.monotonic() + 30
                    while browser.evaluate('edgeValues.length') < 24:
                        if time.monotonic() > deadline:
                            raise TimeoutError('frame replacement fixture')
                        time.sleep(.05)
                    values = browser.evaluate('edgeValues')
                elif mode == 'limit':
                    values = browser.evaluate('document.scripts.length')
                    assert values == 4200
                else:
                    values = browser.evaluate('result.first')
            report['modes'][mode] = {'settings': env, 'page': values, 'records': records(folder)}
            (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
            print(json.dumps({'mode': mode, 'records': len(report['modes'][mode]['records'])}), flush=True)
    for mode in ('unset', 'excluded', 'core-off'):
        assert not report['modes'][mode]['records'], mode
    frame = report['modes']['frames']
    rows = [r for r in frame['records'] if r['type'] == 'realm_rng'
            and r['phase'] == 'initial' and '/rng-frame-first.js' in r['script_url']]
    assert len(rows) == 24
    assert len({(r['process_instance_id'], r['realm_id']) for r in rows}) == 24
    expected = []
    for row in rows:
        state = int(row['state0'], 16), int(row['state1'], 16)
        _, values = advance(state, 1)
        expected.append(values[0])
    assert sorted(expected) == sorted(frame['page'])
    limits = report['modes']['limit']['records']
    assert sum(r['type'] == 'realm_rng' for r in limits) == 4096
    gaps = [r for r in limits if r['type'] == 'rng_trace_gap']
    assert len(gaps) == 1 and gaps[0]['reason'] == 'record-limit' and gaps[0]['records'] == 4096
    report['validation'] = {'passed': True, 'frame_realms': 24, 'record_limit': 4096,
        'limitation': 'Frames are detached, but GC/address reuse and 1024 simultaneous capacity are not forced.'}
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps(report['validation']))


if __name__ == '__main__':
    main()
