"""Verify actual Firefox object snapshot capture, omissions and budget evidence."""
import argparse
import json
from pathlib import Path


def nodes(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from nodes(child)
    elif isinstance(value,list):
        for child in value:yield from nodes(child)


def verify(report):
    modes=report['modes'];baseline=modes['off']['page']
    assert report['capture_present'] and report['page_results_equal']
    assert all(mode['page']==baseline for mode in modes.values())
    assert baseline['gets']==baseline['traps']==baseline['jsonCalls']==0
    assert baseline['descriptorsEqual']
    assert not modes['off']['snapshots'] and not modes['detail']['snapshots'] and not modes['excluded']['snapshots']
    snapshots=modes['objects']['snapshots']
    assert len(snapshots)==16
    assert len(modes['independent']['snapshots'])==16
    assert len(modes['limit']['snapshots'])==3
    assert all(any(b['value']=='0102fe' for b in modes[m]['buffers'])
               for m in ['detail','objects','limit','small','independent','excluded'])
    assert all(s['bytes']<=16384 and s['value']['schema']=='jscall.object.v1' for s in snapshots)
    assert all(s['function'] in ('snapshotTarget','snapshotReturn') for s in snapshots)
    assert any(s['function']=='snapshotReturn' and s['slot']=='return' for s in snapshots)
    values=[n for s in snapshots for n in nodes(s['value'])]
    assert any(n.get('t')=='number' and n.get('v')==42 for n in values)
    assert any(n.get('t')=='string' and n.get('v')=='kept' for n in values)
    assert any(n.get('t')=='string' and n.get('v')=='numeric-slot' for n in values)
    assert any(n.get('t')=='string' and '\ud800' in n.get('v','') for n in values)
    assert any(n.get('t')=='string' and n.get('cut') and len(n['v'])==128 for n in values)
    assert any(n.get('t')=='negative-zero' for n in values)
    assert any(n.get('t')=='undefined' for n in values)
    assert any(n.get('t')=='ref' for n in values)
    reasons={n['reason'] for n in values if n.get('t')=='omitted'}
    assert {'accessor-or-custom','non-plain-object','hole','depth','dictionary-shape','symbol-key'}<=reasons,reasons
    assert any(n.get('propertiesCut') for n in values)
    assert all(s['truncated'] for s in modes['small']['snapshots'])
    assert all(s['bytes']<=256 for s in modes['small']['snapshots'])
    stats=modes['limit']['stats']
    assert sum(s.get('object_snapshots',0) for s in stats)==3
    assert sum(s.get('object_limited',0) for s in stats)==13
    return {'page_results_equal':True,'getter_calls':0,'proxy_traps':0,'to_json_calls':0,
            'snapshots':len(snapshots),'limited_snapshots':3,'limited_fallbacks':13,
            'explicit_omission_reasons':sorted(reasons),'return_snapshot_verified':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('report',type=Path)
    args=parser.parse_args();report=json.loads(args.report.read_text('utf-8'));result=verify(report)
    result.update(firefox_sha256=report['firefox_sha256'],xul_sha256=report['xul_sha256'])
    args.report.with_name('validation.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
