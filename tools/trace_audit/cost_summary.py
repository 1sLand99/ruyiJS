"""Summarize paired cost measurements without hiding sparse trace coverage."""
import argparse
import json
import math
from pathlib import Path
import statistics


def quantile(values, fraction):
    values = sorted(values)
    at = (len(values)-1)*fraction
    low = int(at);high = math.ceil(at)
    return values[low]*(high-at)+values[high]*(at-low) if low != high else values[low]


def summarize(report):
    runs = report['runs'];groups = {}
    expected_modes = {'off','core','calls','detail'}
    for row in runs:
        identity = row['round'],row['mode']
        if identity in groups: raise ValueError('duplicate paired run')
        if len(row['samples']) != report['samples_per_run']: raise ValueError('missing timing samples')
        groups[identity] = row
    for repetition in range(report['rounds']):
        if {mode for number,mode in groups if number==repetition} != expected_modes:
            raise ValueError('incomplete paired modes')
    reference = groups[0,'off']['surface']
    checksum = groups[0,'off']['samples'][0]['page']['checksum']
    if not all(row['surface']==reference for row in runs): raise ValueError('surface changed')
    if not all(s['page']['checksum']==checksum for row in runs for s in row['samples']):
        raise ValueError('workload checksum changed')
    for row in runs:
        capture = row['capture']
        if capture['dict_errors']: raise ValueError('malformed capture dictionary')
        if row['mode'] in ('calls','detail') and (not capture['stats'] or not capture['call_records']):
            raise ValueError('expected capture is empty')
        if row['mode']=='detail' and not capture['detail_bytes']: raise ValueError('missing value detail')
        if row['mode']=='off' and capture['trace_bytes']: raise ValueError('off mode unexpectedly wrote trace')
        if row['mode']!='off' and not capture['trace_bytes']: raise ValueError('enabled capture wrote no bytes')
        if sum(s['recorded'] for s in capture['stats']) != capture['call_records']:
            raise ValueError('writer and binary call counts differ')
        for sample in row['samples']:
            for name in ('wall_ms','cpu_ms','peak_sum_rss_bytes'):
                value=sample['process'][name]
                if type(value) not in (int,float) or not math.isfinite(value) or value<0:
                    raise ValueError('invalid process measurement')
            if sample['process']['wall_ms']<=0: raise ValueError('zero wall duration')
    result = {'surface_equal': True,'checksums_equal': True,'modes': {},'paired_ratios': {},
              'full_call_coverage': all(row['capture']['leaf_records']==report['known_calls_per_process']['leaf']
                  and row['capture']['bytes_records']==report['known_calls_per_process']['bytes']
                  for row in runs if row['mode'] in ('calls','detail')),
              'zero_overhead_proven': False}
    for mode in sorted(expected_modes):
        selected = [row for row in runs if row['mode']==mode]
        metrics = {}
        for name in ('wall_ms','cpu_ms','peak_sum_rss_bytes'):
            values = [s['process'][name] for row in selected for s in row['samples']]
            metrics[name] = {'median': statistics.median(values),'p95_interpolated': quantile(values,.95)}
        metrics['sample_errors'] = sum(s['process']['sample_errors'] for row in selected for s in row['samples'])
        metrics['trace_bytes'] = [r['capture']['trace_bytes'] for r in selected]
        metrics['call_records'] = [r['capture']['call_records'] for r in selected]
        metrics['leaf_coverage'] = [r['capture']['leaf_records']/report['known_calls_per_process']['leaf'] for r in selected]
        metrics['bytes_coverage'] = [r['capture']['bytes_records']/report['known_calls_per_process']['bytes'] for r in selected]
        metrics['writer_gap_counts'] = {key: sum(s.get(key,0) for r in selected for s in r['capture']['stats'])
            for key in ('dropped_limit','dropped_gate','dropped_no_func_id','dropped_chunks','io_errors')}
        result['modes'][mode] = metrics
        if mode!='off':
            result['paired_ratios'][mode] = {}
            for name in ('wall_ms','cpu_ms'):
                ratios=[]
                for repetition in range(report['rounds']):
                    base=statistics.median(s['process'][name] for s in groups[repetition,'off']['samples'])
                    value=statistics.median(s['process'][name] for s in groups[repetition,mode]['samples'])
                    ratios.append(value/base if base else None)
                valid=[v for v in ratios if v is not None]
                result['paired_ratios'][mode][name]={'per_round':ratios,
                    'median':statistics.median(valid) if valid else None}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args=parser.parse_args()
    print(json.dumps(summarize(json.loads(args.report.read_text('utf-8'))),indent=2))


if __name__=='__main__':main()
