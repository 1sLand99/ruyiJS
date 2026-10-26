"""Compare stored request bodies without substituting recorded responses."""
import hashlib
import json


def packet_requests(run):
    rows={}
    for path in (run/'http_packet').glob('*.http_packet.json'):
        packet=json.loads(path.read_text('utf-8'))
        urlhash=hashlib.sha256(packet['url'].encode()).hexdigest()
        params=packet.get('params',{})
        text=params.get('postText')
        body=text.encode('utf-8') if isinstance(text,str) else None
        rows.setdefault((packet['method'],urlhash),[]).append(
            {'file':path.name,'post_sha256':params.get('postSha256'),'body':body})
    return rows


def compare_body(actual,candidates):
    data=actual.encode('utf-8')
    digest=hashlib.sha256(data).hexdigest()
    comparisons=[]
    for candidate in candidates:
        expected=candidate['body']
        row={'file':candidate['file'],'post_sha256':candidate['post_sha256']}
        if expected is not None:
            prefix=0
            for left,right in zip(data,expected):
                if left!=right:break
                prefix+=1
            row.update(recorded_bytes=len(expected),common_prefix_bytes=prefix,
                       actual_body_equal=data==expected,
                       recorded_body_hash_valid=hashlib.sha256(expected).hexdigest()==candidate['post_sha256'])
        comparisons.append(row)
    return {'body_bytes':len(data),'recorded_candidates':comparisons,
            'recorded_body_hash_match':any(x['post_sha256']==digest for x in candidates),
            'comparison_scope':'stored postText UTF-8 bytes; encrypted-body prefix is not semantic similarity'}
