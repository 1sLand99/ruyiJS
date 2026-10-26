"""Factorial local coverage/cost study: normal JIT vs explicit interpreter diagnosis."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time

from tools.firefox_parity.browser import Firefox
from .tier_fixture import Fixture, SCRIPT
from .tier_capture import collect
from .rng_probe import digest

PREF_KEYS = ('javascript.options.blinterp','javascript.options.baselinejit','javascript.options.ion')


def read_preferences(browser):
    browser.command('Marionette:SetContext',{'value':'chrome'})
    try:
        expression = 'Object.fromEntries('+json.dumps(PREF_KEYS)+'.map(k=>[k,Services.prefs.getBoolPref(k)]))'
        return browser.evaluate(expression)
    finally:
        browser.command('Marionette:SetContext',{'value':'content'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,default=3)
    parser.add_argument('--samples',type=int,default=3)
    parser.add_argument('--iterations',type=int,default=250000)
    parser.add_argument('--warmup',type=int,default=10000)
    parser.add_argument('--byte-calls',type=int,default=1000)
    parser.add_argument('--firefox',type=Path,default=Path('D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe'))
    args=parser.parse_args()
    if not (1<=args.rounds<=10 and 1<=args.samples<=10 and 1000<=args.iterations<=500000
            and 0<=args.warmup<=50000 and 1<=args.byte_calls<=10000):
        parser.error('workload exceeds bounded experiment limits')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    report={'schema':'local.tier-cost.v1','runs':[],'rounds':args.rounds,'samples':args.samples,
        'iterations':args.iterations,'warmup':args.warmup,'byte_calls':args.byte_calls,'seed':20261024,
        'firefox_sha256':digest(args.firefox),'xul_sha256':digest(args.firefox.with_name('xul.dll')),
        'workload_sha256':hashlib.sha256(SCRIPT).hexdigest(),
        'known_calls':{'measuredLeaf':args.warmup+args.samples*args.iterations,
                       'measuredBytes':(1+args.samples)*args.byte_calls},
        'limits':['JIT policy is changed explicitly only for diagnostic cells; no default runtime modification.',
            'No opcode instrumentation is implemented or timed; this measures prerequisites and call coverage.',
            'Host duration includes Marionette; short page timings may be below clock resolution.',
            'Identical instrumented binary used for every mode; no upstream uninstrumented control.',
            'Full known-function coverage applies only to this bounded fixture, not a whole browser.']}
    order_rng=random.Random(report['seed'])
    with Fixture() as fixture:
        for repetition in range(args.rounds):
            order=[(tier,mode) for tier in ('normal','interpreter') for mode in ('off','calls','detail')]
            order_rng.shuffle(order)
            for tier,mode in order:
                folder=output/f'{repetition}-{tier}-{mode}';folder.mkdir()
                prefs={} if tier=='normal' else {name:False for name in PREF_KEYS}
                env={} if mode=='off' else {'MOZ_DOM_TRACE':'0','MOZ_DOM_TRACE_FILE':str(folder/'run.jsonl'),
                    'MOZ_DOM_JSCALL_TRACE':'1','MOZ_DOM_JSCALL_SCRIPT_URL':'/tier-workload.js',
                    'MOZ_DOM_JSCALL_LIMIT':'0'}
                if mode=='detail':env['MOZ_DOM_JSCALL_DETAIL_SCRIPT_URL']='/tier-workload.js'
                samples=[]
                with Firefox(args.firefox,folder/'profile',prefs=prefs,extra_environment=env,
                             extra_args=('--remote-allow-system-access',),timeout=50) as browser:
                    actual_prefs=read_preferences(browser)
                    if tier=='interpreter' and any(actual_prefs.values()):raise ValueError('interpreter preferences not active')
                    if tier=='normal' and not all(actual_prefs.values()):raise ValueError('normal preferences unexpectedly disabled')
                    browser.navigate(fixture.url)
                    surface=browser.evaluate('tierBench.surface()')
                    warmup=browser.evaluate(f'tierBench.run({args.warmup},{args.byte_calls})')
                    for _ in range(args.samples):
                        start=time.perf_counter()
                        value=browser.evaluate(f'tierBench.run({args.iterations},{args.byte_calls})')
                        samples.append({'host_ms':(time.perf_counter()-start)*1000,**value})
                capture=collect(folder)
                report['runs'].append({'round':repetition,'tier':tier,'mode':mode,'order':order,
                    'preferences':actual_prefs,'settings':env,'surface':surface,'warmup':warmup,
                    'samples':samples,'capture':capture})
                (output/'results.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
                print(json.dumps({'round':repetition,'tier':tier,'mode':mode,
                    'page_ms':[s['page_ms'] for s in samples],
                    'leaf':capture['functions'].get('measuredLeaf',0),'trace_bytes':capture['trace_bytes']}),flush=True)


if __name__=='__main__':main()
