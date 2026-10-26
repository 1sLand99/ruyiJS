"""Compile an observed checkpoint contract for the hash-identified serial fixture."""
from collections import defaultdict
import hashlib
import json

from .async_evidence import analyze, context_key, load_rows
from .async_fixture import RESOURCES
from .rng_probe import digest
from .verify_async_probe import check_call_ids, verify_case

MICROTASKS = {'promise_reaction', 'queue_microtask'}


def marker_groups(rows):
    contexts = {}; schedules = {}; marked = []
    for row in rows:
        kind = row['type']
        if (kind in ('script_root', 'async_resume') and row.get('phase') == 'start') or kind == 'message_receive':
            field = 'receiver_execution_context_id' if kind == 'message_receive' else 'execution_context_id'
            key = context_key(row, field)
            if not key[-1] or key in contexts:
                raise ValueError('ambiguous or zero execution context')
            contexts[key] = row
        if kind == 'async_schedule':
            key = context_key(row, 'async_context_id')
            if key in schedules:
                raise ValueError('ambiguous schedule')
            schedules[key] = row
        if kind == 'call' and row.get('interface') == 'Element' and row.get('member') == 'setAttribute':
            args = row.get('args', [])
            if len(args) == 2 and args[0] == 'data-causal-proof':
                marked.append(row)
    if not marked or len({row['file'] for row in marked}) != 1:
        raise ValueError('contract requires markers from one observed main-page file')
    if [row['file_line'] for row in marked] != sorted({row['file_line'] for row in marked}):
        raise ValueError('marker file order changed or duplicated')
    groups = []; closed = set()
    for marker in marked:
        key = context_key(marker); chain = []; seen = set()
        while True:
            if key in seen or len(seen) >= 64:
                raise ValueError('cycle or excessive checkpoint ancestry')
            seen.add(key)
            row = contexts.get(key)
            if row is None:
                raise ValueError('checkpoint context undeclared')
            chain.append(list(key))
            if row['type'] != 'async_resume' or row['async_cause'] not in MICROTASKS:
                break
            schedule_key = (key[0], row.get('schedule_session', row.get('session', 0)), row['async_context_id'])
            schedule = schedules.get(schedule_key)
            if schedule is None or schedule['async_cause'] != row['async_cause']:
                raise ValueError('missing or mismatched microtask schedule')
            key = context_key(schedule, 'parent_execution_context_id')
        if not groups or groups[-1]['root_context'] != list(key):
            if key in closed:
                raise ValueError('checkpoint group reappeared after another group')
            closed.add(key)
            groups.append({'root_context': list(key), 'kind': row['type'],
                           'cause': row.get('async_cause', row.get('message_kind')),
                           'labels': [], 'observations': []})
        groups[-1]['labels'].append(marker['args'][1])
        groups[-1]['observations'].append({'file': marker['file'], 'line': marker['file_line'],
                                         'context_ancestry': chain})
    return groups


def compile_contract(report_path, case):
    report = json.loads(report_path.read_text('utf-8'))
    actual_hashes = {url: hashlib.sha256(body).hexdigest() for url, (_, body) in RESOURCES.items()}
    if report['fixture_hashes'] != actual_hashes:
        raise ValueError('checkpoint assumptions do not apply to different fixture source')
    if case not in report['cases'] or case['mode'] not in ('core', 'calls'):
        raise ValueError('case is not an enabled recorded fixture case')
    rows, sources = load_rows(report_path.parent / case['folder'])
    proof = analyze(rows)
    verify_case(case, proof, True)
    if case['mode'] == 'calls':
        check_call_ids(report_path.parent / case['folder'], proof)
    groups = marker_groups(rows)
    return {'schema': 'local.async-checkpoint-contract.v1', 'round': case['round'], 'mode': case['mode'],
            'capture_report': str(report_path.resolve()), 'capture_sha256': digest(report_path),
            'fixture_hashes': actual_hashes, 'sources': sources, 'groups': groups,
            'labels': [label for group in groups for label in group['labels']],
            'assumptions': ['Fixed fixture uses immediately resolved Promises and explicit queueMicrotask.',
                            'Only recorded main-page marker groups are consumed.',
                            'No capture clock, ready-task selection, or worker execution is controlled.'],
            'full_goal_complete': False}


class ContractCursor:
    def __init__(self, contract):
        self.groups = contract['groups']
        self.labels = contract['labels']
        if not self.groups or any(not g['labels'] for g in self.groups):
            raise ValueError('empty checkpoint contract')
        if [label for g in self.groups for label in g['labels']] != self.labels:
            raise ValueError('group labels and full sequence differ')
        self.consumed = []; self.position = 0

    def observe(self, labels):
        if labels[:len(self.consumed)] != self.consumed:
            raise ValueError('previously observed output changed')
        added = labels[len(self.consumed):]
        if not added:
            return None
        if self.position >= len(self.groups):
            raise ValueError('extra output after final checkpoint')
        group = self.groups[self.position]
        if added != group['labels']:
            raise ValueError(f'checkpoint {self.position} differs: expected {group["labels"]}, observed {added}')
        self.consumed = list(labels); self.position += 1
        return self.position - 1

    def finish(self):
        if self.position != len(self.groups) or self.consumed != self.labels:
            raise ValueError('recorded checkpoint contract not fully consumed')
        return True
