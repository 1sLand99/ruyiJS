"""Build the original Neqo WebTransport candidate offline without deploying it."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import time
from necko_webtransport_prepare import BUILD, SOURCE, ROOT, prepare, sha


def environment():
    env = dict(os.environ)
    for name in ('RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER'):
        env.pop(name, None)
    tools = Path('C:/Users/Administrator/.mozbuild')
    msvc = tools / 'vs/VC/Tools/MSVC/14.50.35717'
    sdk = tools / 'vs/Windows Kits/10'
    rust = Path('C:/Users/Administrator/.rustup/toolchains/stable-x86_64-pc-windows-msvc/bin')
    for key, suffix in (('CARGO_HOME','cargo-home'),('CARGO_TARGET_DIR','target'),('TEMP','temp'),('TMP','temp')):
        path = BUILD / suffix
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env['LIB'] = os.pathsep.join(map(str,[msvc/'lib/x64',sdk/'Lib/10.0.26100.0/ucrt/x64',sdk/'Lib/10.0.26100.0/um/x64']))
    env['LIBCLANG_PATH'] = str(tools/'clang/bin')
    env['BINDGEN_EXTRA_CLANG_ARGS'] = ' '.join('-isystem "'+str(p)+'"' for p in (
        msvc/'include',sdk/'Include/10.0.26100.0/ucrt',sdk/'Include/10.0.26100.0/shared',sdk/'Include/10.0.26100.0/um'))
    env['NECKO_NSS_DIST'] = 'D:/firefox/src/firefox/obj-necko/nss-sdk-v20'
    env['RUSTC'] = str(rust/'rustc.exe')
    env['CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER'] = str(tools/'clang/bin/lld-link.exe')
    env['PATH'] = str(ROOT/'vendor/necko-derived/python/Lib/site-packages/necko')+os.pathsep+env.get('PATH','')
    return env, rust/'cargo.exe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    inputs = prepare()
    env, cargo = environment()
    command = [str(cargo),'check' if args.check else 'build','--offline','--locked','--release',
               '--target','x86_64-pc-windows-msvc','--jobs','4']
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    log = BUILD/(stamp+'-build.log')
    start = time.monotonic()
    with log.open('w',encoding='utf8') as stream:
        result = subprocess.run(command,cwd=SOURCE,env=env,stdout=stream,stderr=subprocess.STDOUT)
    changed = [p for p,digest in inputs['preparedInputs'].items() if sha(SOURCE/p)!=digest]
    dll = BUILD/'target/x86_64-pc-windows-msvc/release/necko_quic.dll'
    report = {'command':command,'exitCode':result.returncode,'seconds':round(time.monotonic()-start,3),
              'changedInputs':changed,'log':str(log),'logSHA256':sha(log),
              'passed':result.returncode==0 and not changed,'deployed':False}
    if dll.is_file():
        report['candidate'] = {'path':str(dll),'sha256':sha(dll)}
    (BUILD/(stamp+'-build.json')).write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(report),flush=True)
    if result.returncode:
        print(log.read_text('utf8',errors='replace')[-12000:])
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
