"""Reconstruct observed ICE objects without guessing unrecorded event metadata."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def scan(path, stop_at_send=False):
    process, first_send, final_null = None, None, None
    events, candidates, peer_ids, anomalies = {}, {}, set(), []
    with path.open('rb') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if row.get('type') == 'trace_init':
                process = row.get('process_instance_id') or f"pid:{row.get('pid')}"
            iface, member = row.get('interface'), row.get('member')
            if iface == 'XMLHttpRequest' and member == 'send' and first_send is None:
                first_send = {'line': number, 'seq': row.get('seq'), 'ts': row.get('ts')}
                if stop_at_send or final_null is not None: break
            if final_null is not None: continue
            if iface == 'RTCPeerConnection' and row.get('type') == 'call':
                identity = (row.get('thisObj') or {}).get('id')
                if identity: peer_ids.add(identity)
            if iface == 'RTCPeerConnectionIceEvent' and member == 'get candidate':
                event_id = (row.get('thisObj') or {}).get('id')
                candidate_id = (row.get('valueObj') or {}).get('id')
                if not event_id:
                    anomalies.append({'line': number, 'reason': 'event identity missing'}); continue
                event = events.setdefault(event_id, {'event_id': event_id, 'candidate_id': candidate_id,
                    'first_line': number, 'last_line': number, 'first_seq': row.get('seq'),
                    'first_observed_ts': row.get('ts'), 'getter_count': 0,
                    'before_first_send': first_send is None})
                if event['candidate_id'] != candidate_id:
                    anomalies.append({'line': number, 'reason': 'event candidate identity changed'})
                event['getter_count'] += 1; event['last_line'] = number
                if row.get('value') is None:
                    event['null'] = True
                    final_null = number
                    if first_send is not None: break
                    continue
                if not candidate_id:
                    anomalies.append({'line': number, 'reason': 'candidate identity missing'})
            if iface == 'RTCIceCandidate' and row.get('type') == 'get':
                identity = (row.get('thisObj') or {}).get('id')
                if not identity:
                    anomalies.append({'line': number, 'reason': 'candidate getter lacks receiver'});continue
                key = member.removeprefix('get ')
                if key not in ('candidate','sdpMid','sdpMLineIndex','usernameFragment'):continue
                candidate = candidates.setdefault(identity, {'fields': {}, 'reads': []})
                value = row.get('value')
                if key in candidate['fields'] and candidate['fields'][key] != value:
                    anomalies.append({'line': number, 'reason': 'candidate field changed'})
                candidate['fields'][key] = value
                candidate['reads'].append({'line': number, 'seq': row.get('seq'), 'member': key})
    phases = {'before_first_send': Counter(), 'after_first_send': Counter()}
    for event in events.values():
        if event.get('null'):
            category = 'null'
        else:
            candidate = candidates.get(event['candidate_id'], {'fields': {}, 'reads': []})
            event['candidate'] = candidate
            text = candidate['fields'].get('candidate')
            if text == '':category = 'empty'
            elif isinstance(text,str) and ' typ ' in text:category = text.split(' typ ',1)[1].split(' ')[0]
            else:category = 'unread-or-invalid'
            event['missing_fields'] = [key for key in ('sdpMid','sdpMLineIndex','usernameFragment')
                                       if key not in candidate['fields']]
        event['category'] = category
        phases['before_first_send' if event['before_first_send'] else 'after_first_send'][category] += 1
    with path.open('rb') as stream: sha = hashlib.file_digest(stream,'sha256').hexdigest()
    return {'schema':'rtc.observed-objects.v1','source':str(path),'sha256':sha,
        'process_instance_id':process,'first_send':first_send,'final_null_line':final_null,
        'observed_peer_ids':sorted(peer_ids),'events':list(events.values()),
        'phases':{key:dict(value) for key,value in phases.items()},'anomalies':anomalies,
        'limitations':['Getter observations do not establish candidate creation or dispatch timestamps.',
            'Event/candidate object joins do not prove the target peer without dispatch target evidence.',
            'Missing SDP mid/index/ufrag are not filled from candidate text or ordinal position.',
            'A recorded end marker does not prove all preceding unobserved events were captured.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stop-at-send',action='store_true')
    args=parser.parse_args()
    report=scan(args.trace,args.stop_at_send)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps({'events':len(report['events']),'phases':report['phases'],
        'anomalies':len(report['anomalies']),'missing_metadata_events':sum(bool(x.get('missing_fields')) for x in report['events'])}))


if __name__=='__main__':main()
