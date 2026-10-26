"""Validate factorial coverage evidence and separate tier cost from tracing cost."""
import argparse
import json
import math
from pathlib import Path
import statistics

TIERS = ('normal', 'interpreter')
MODES = ('off', 'calls', 'detail')
PREFERENCES = ('javascript.options.blinterp','javascript.options.baselinejit','javascript.options.ion')


def summarize(report):
    expected = {(n,tier,mode) for n in range(report['rounds']) for tier in TIERS for mode in MODES}
    runs = {}
    known = report['known_calls']
    if known != {'measuredLeaf': report['warmup'] + report['samples']*report['iterations'],
                 'measuredBytes': (1+report['samples'])*report['byte_calls']}:
        raise ValueError('workload invocation denominator differs')
    reference = None
    checksum = None
    for row in report['runs']:
        identity = row['round'],row['tier'],row['mode']
        if identity not in expected or identity in runs: raise ValueError('duplicate or unknown cell')
        runs[identity] = row
        wanted = row['tier']=='normal'
        if row['preferences'] != {name:wanted for name in PREFERENCES}:
            raise ValueError('requested and observed runtime preferences differ')
        if reference is None: reference=row['surface']
        if row['surface']!=reference: raise ValueError('selected page surface changed')
        if row['surface']['gets'] or row['surface']['traps']: raise ValueError('page probe side effects')
        if len(row['samples'])!=report['samples']: raise ValueError('missing repeated samples')
        for sample in row['samples']:
            if checksum is None: checksum=sample['checksum']
            if sample['checksum']!=checksum: raise ValueError('workload result differs')
            for field in ('host_ms','page_ms'):
                value=sample[field]
                if type(value) not in (int,float) or not math.isfinite(value) or value<0:
                    raise ValueError('invalid timing sample')
            if not sample['host_ms']: raise ValueError('zero host duration')
        capture=row['capture']
        if capture['call_records']!=capture['writer_records']: raise ValueError('writer count mismatch')
        if any(capture['writer_drops'].values()): raise ValueError('capture reported drops or I/O errors')
        if row['mode']=='off':
            if capture['trace_bytes'] or capture['call_records'] or capture['functions']:
                raise ValueError('trace-off mode emitted capture')
        else:
            if not capture['call_records'] or not capture['dictionary_count']:
                raise ValueError('missing expected capture')
            for function,denominator in known.items():
                count=capture['functions'].get(function,0)
                if not 0<count<=denominator: raise ValueError('invalid known-function count')
            if row['mode']=='detail':
                if not capture['detail_bytes'] or not capture['detail'].get('records'):
                    raise ValueError('missing value detail')
                if capture['detail'].get('truncated') or capture['detail'].get('unreadable'):
                    raise ValueError('fixture values not captured completely')
    if set(runs)!=expected: raise ValueError('incomplete factorial cells')
    for n in range(report['rounds']):
        order = [tuple(x) for x in runs[n,'normal','off']['order']]
        if len(order)!=6 or set(order)!={(t,m) for t in TIERS for m in MODES}:
            raise ValueError('invalid per-round execution order')
        if any([tuple(x) for x in runs[n,t,m]['order']]!=order for t in TIERS for m in MODES):
            raise ValueError('inconsistent per-round order metadata')
    result={'behavior_equal':True,'cells':{},'ratios':{},'zero_overhead_proven':False,
        'opcode_measured':False,'fixture_calls_complete_in_interpreter':all(
            runs[n,'interpreter',mode]['capture']['functions'].get(fn)==count
            for n in range(report['rounds']) for mode in ('calls','detail') for fn,count in known.items())}
    for tier in TIERS:
        for mode in MODES:
            rows=[runs[n,tier,mode] for n in range(report['rounds'])]
            result['cells'][tier+'/'+mode]={
                'host_median_ms':statistics.median(s['host_ms'] for r in rows for s in r['samples']),
                'page_median_ms':statistics.median(s['page_ms'] for r in rows for s in r['samples']),
                'zero_page_samples':sum(s['page_ms']==0 for r in rows for s in r['samples']),
                'trace_bytes':[r['capture']['trace_bytes'] for r in rows],
                'call_records':[r['capture']['call_records'] for r in rows],
                'caller_jit_gaps':[r['capture']['caller_jit_gaps'] for r in rows],
                'coverage':{fn:[r['capture']['functions'].get(fn,0)/count for r in rows] for fn,count in known.items()}}
    comparisons = {'tier_without_trace':(('interpreter','off'),('normal','off'))}
    for tier in TIERS:
        for mode in ('calls','detail'):
            comparisons[tier+'_'+mode+'_vs_off']=((tier,mode),(tier,'off'))
    comparisons['interpreter_detail_vs_normal_off']=(('interpreter','detail'),('normal','off'))
    for name,(numerator,denominator) in comparisons.items():
        ratios=[]
        for n in range(report['rounds']):
            a=statistics.median(s['page_ms'] for s in runs[(n,*numerator)]['samples'])
            b=statistics.median(s['page_ms'] for s in runs[(n,*denominator)]['samples'])
            ratios.append(a/b if b else None)
        available=[value for value in ratios if value is not None]
        result['ratios'][name]={'per_round':ratios,'median':statistics.median(available) if available else None}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=summarize(json.loads(args.report.read_text('utf-8')))
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
