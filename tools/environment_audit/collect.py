"""Compare native browser behavior on identical local inputs; no API overlays."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / 'tools/firefox_parity'))
from ruyijs import Context, JSError
from browser import Firefox
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture import Fixture

HERE = Path(__file__).resolve().parent
PROBES = ('dom', 'graphics', 'platform', 'realms', 'errors', 'network', 'worker', 'rtc',
          'storage', 'scheduling', 'security', 'observers')


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def begin(source, realm):
    script = "globalThis.__environmentAuditResult={done:false};Promise.resolve((" + source + ")(window)).then(" \
        "value=>{globalThis.__environmentAuditResult={done:true,value}}," \
        "error=>{globalThis.__environmentAuditResult={done:true,error:{name:error.name,message:error.message}}});undefined"
    target = 'window' if realm == 'main' else "document.querySelector('iframe').contentWindow"
    return '(w=>{const s=w.document.createElement("script");s.textContent=' + json.dumps(script) + \
        ';w.document.head.appendChild(s);s.remove();return true;})(' + target + ')'


def read(realm):
    target = 'window' if realm == 'main' else "document.querySelector('iframe').contentWindow"
    return target + '.__environmentAuditResult'


def profile(browser):
    return browser.evaluate('''({navigator:{userAgent:navigator.userAgent,platform:navigator.platform,
      language:navigator.language,languages:Array.from(navigator.languages),hardwareConcurrency:navigator.hardwareConcurrency,
      maxTouchPoints:navigator.maxTouchPoints,webdriver:navigator.webdriver,oscpu:navigator.oscpu},
      screen:{width:screen.width,height:screen.height,availWidth:screen.availWidth,availHeight:screen.availHeight,
      availLeft:screen.availLeft,availTop:screen.availTop,colorDepth:screen.colorDepth,pixelDepth:screen.pixelDepth},
      viewport:{width:innerWidth,height:innerHeight,devicePixelRatio},
      locale:{timezone:Intl.DateTimeFormat().resolvedOptions().timeZone}})''')


def wait_result(evaluate, advance, realm, seconds=15):
    deadline = time.monotonic() + seconds
    errors = []
    while time.monotonic() < deadline:
        try:
            advance()
        except JSError as error:
            if len(errors) < 5:
                errors.append({'name':error.name, 'message':error.message[:500]})
        result = evaluate(read(realm))
        if isinstance(result, dict) and result.get('done'):
            if errors:
                result['runtimeErrors'] = errors
            return result
    return {'done':False, 'error':{'name':'TimeoutError', 'message':'Probe deadline exceeded'}, 'runtimeErrors':errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--probes', nargs='+', choices=PROBES, default=list(PROBES))
    parser.add_argument('--firefox', type=Path, default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'artifacts'):
        parser.error('Output must be under artifacts')
    output.mkdir(parents=True, exist_ok=False)
    sources = {name:(HERE / (name + '.js')).read_text('utf-8') for name in args.probes}
    if 'worker' in sources:
        sources['worker'] = sources['worker'].replace('__WORKER_SURFACE__', json.dumps((HERE/'worker_surface.js').read_text('utf-8')))
    metadata = {'scope':'secure localhost main and same-origin iframe; live local HTTP; native APIs',
                'shell_sha256':hashlib.sha256((ROOT/'dist/js.exe').read_bytes()).hexdigest(),
                'client_sha256':hashlib.sha256((ROOT/'dist/ruyijs_client.dll').read_bytes()).hexdigest(),
                'firefox_sha256':hashlib.sha256(args.firefox.read_bytes()).hexdigest(),
                'probes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()}}
    failures = []
    with Fixture() as fixture:
        url = fixture.origins['secure'] + '/'
        metadata['url'] = url
        with Firefox(args.firefox, output / 'profile') as browser:
            browser.navigate(url)
            environment = profile(browser)
            metadata['environment'] = environment
            metadata['browser_capabilities'] = browser.capabilities
            for name, source in sources.items():
                for realm in ('main', 'frame'):
                    label = f'firefox-{name}-{realm}'
                    try:
                        browser.navigate(url)
                        browser.evaluate(begin(source, realm))
                        result = wait_result(browser.evaluate, lambda:time.sleep(.05), realm)
                    except Exception as error:
                        result = {'done':False, 'error':{'name':type(error).__name__, 'message':str(error)[:1200]}}
                    save(output/(label+'.json'), result)
                    print(json.dumps({'capture':label,'done':result.get('done'), 'error':result.get('error')}), flush=True)
                    if result.get('error'):
                        failures.append(label)
        for name, source in sources.items():
            for realm in ('main', 'frame'):
                label = f'ruyijs-{name}-{realm}'
                try:
                    with Context(shell=ROOT/'dist/js.exe', timeout=30, environment=environment) as context:
                        context.navigate(url)
                        deadline = time.monotonic() + 10
                        while time.monotonic() < deadline:
                            context.advance(50, max_tasks=1000)
                            if context.eval("document.readyState==='complete' && !!document.querySelector('iframe')?.contentDocument?.body"):
                                break
                        context.eval(begin(source, realm))
                        result = wait_result(context.eval, lambda:context.advance(50,max_tasks=1000), realm)
                except Exception as error:
                    result = {'done':False,'error':{'name':type(error).__name__,'message':str(error)[:1200]}}
                save(output/(label+'.json'), result)
                print(json.dumps({'capture':label,'done':result.get('done'),'error':result.get('error')}), flush=True)
                if result.get('error'):
                    failures.append(label)
    metadata['incomplete_captures'] = failures
    save(output/'metadata.json',metadata)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
