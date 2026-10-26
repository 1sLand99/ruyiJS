"""Verify artifacts that narrow the first request mismatch to recorded measurements."""
import argparse
import json
from pathlib import Path

from .rng_probe import digest
from .navigation_observer_evidence import challenge_posts
from .serialized_payload import reconstruct, differences

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/call-alignment-20261024')
    args=parser.parse_args();out=args.output.resolve()
    load=lambda p:json.loads(p.read_text('utf-8'))
    verified=out/'verified-chain'
    report=load(verified/'result.json');origins=load(out/'numeric-origins.json')
    tests=load(out/'all-tests-result.json')
    rows=load(verified/'serializer-calls.json')
    reference=load(verified/'reference-payload.json');replay=load(verified/'replay-payload.json')
    serializer=report['reference_calls']['14553']['function']
    rebuilt,proof=reconstruct(rows,serializer['name'],serializer['column'])
    assert rebuilt==replay and proof==report['replay']
    assert differences(reference,replay)==report['differences']
    assert len(report['differences'])==len(origins['fields'])==14
    assert {r['path'] for r in report['differences']}=={r['path'] for r in origins['fields']}
    assert report['compression_roundtrip'] and len(report['matching_packets'])==1
    assert digest(verified/'reference-serialized.bin')==report['reference_raw_sha256']
    assert tests['passed'] and tests['returncode']==0
    actual=load(out/'replay/result.json');baseline=load(ROOT/'artifacts/rtc-order-20261024/replay/result.json')
    posts=challenge_posts(actual);old=challenge_posts(baseline)
    assert len(posts)==len(old)==3 and all(a['body_sha256']==b['body_sha256'] for a,b in zip(posts,old))
    trace=next(out.glob('calls-*.jsonl'))
    limit=None
    with trace.open('rb') as stream:
        for n,line in enumerate(stream,1):
            if b'"limit_reached"' in line:
                row=json.loads(line);limit={'line':n,'reason':row['reason']};break
    assert limit and limit['line']>max(r['file_line'] for r in rows)
    expected=report['sources'].get(str(trace.relative_to(ROOT)),report['sources'].get(str(trace)))
    assert expected and digest(trace)==expected
    shell=digest(ROOT/'dist/js.exe');assert shell==actual['shell_sha256']==baseline['shell_sha256']
    sources=['tools/trace_audit/serialized_payload.py','tools/trace_audit/payload_alignment.py',
        'tools/trace_audit/payload_origins.py','tools/trace_audit/payload_alignment_evidence.py',
        'tests/test_serialized_payload.py','docs/TRACE_REPLAY_20261024.md']
    files=['verified-chain/result.json','verified-chain/reference-payload.json','verified-chain/replay-payload.json',
        'verified-chain/serializer-calls.json','verified-chain/reference-serialized.bin','numeric-origins.json',
        'all-tests.log','all-tests-result.json','replay/result.json']
    result={'schema':'payload-alignment.validation.v1','full_goal_complete':False,
        'shell_sha256':shell,'client_sha256':digest(ROOT/'dist/ruyijs_client.dll'),
        'tests':tests,'serialized_reference_bytes':report['reference_bytes'],
        'json_bytes':{'reference':report['reference_json_bytes'],'replay':report['replay_json_bytes']},
        'serializer_calls_verified':proof['serializer_calls'],'numeric_differences':14,
        'message_sources':9,'child_clock_difference_sources':5,'recorded_http_body_bytes':report['recorded_encoder_bytes'],
        'compression_roundtrip':True,'unique_http_body_match':True,'diagnostic_preserves_three_bodies':True,
        'trace_limit':limit,'trace_bytes':trace.stat().st_size,
        'sources':{name:digest(ROOT/name) for name in sources},'reports':{name:digest(out/name) for name in files},
        'limitations':['A complete serialization subtree was captured before a later trace budget limit.',
            'Request measurement fields have not yet been replayed through original clock/message owners.',
            'No request body/global substitution, no full business success or overhead claim.']}
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps({k:result[k] for k in ('tests','numeric_differences','message_sources','child_clock_difference_sources','full_goal_complete')}))


if __name__=='__main__':main()
