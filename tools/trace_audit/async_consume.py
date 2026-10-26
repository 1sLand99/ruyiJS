"""Consume local recorded output groups through existing bounded scheduler RPCs."""
import hashlib
from pathlib import Path
import sys
import time

from .async_contract import ContractCursor
from .async_fixture import Fixture, HTML, RESOURCES
from .rng_probe import digest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / 'tests'))
from ruyijs import Context
from iframe_client import CClient


def consume(contract, adapter, wall_seconds=8, max_steps=2000):
    if digest(Path(contract['capture_report'])) != contract['capture_sha256']:
        raise ValueError('capture report changed')
    for entry in contract['sources']:
        path = Path(entry['path'])
        if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise ValueError('capture file changed')
    if contract['fixture_hashes'] != {url: hashlib.sha256(body).hexdigest() for url, (_, body) in RESOURCES.items()}:
        raise ValueError('fixture source changed')
    cursor = ContractCursor(contract)
    result = {'adapter': adapter, 'round': contract['round'], 'mode': contract['mode'],
              'steps': [], 'passed': False, 'deterministic_task_replay': False}
    with Fixture() as fixture:
        client = Context(shell=ROOT / 'dist/js.exe', timeout=15) if adapter == 'Python' else CClient()
        try:
            def status():
                return client.clock_status() if adapter == 'Python' else client.call('event_loop', action='status')

            def advance(ms):
                return client.advance(ms, max_tasks=1) if adapter == 'Python' else client.call(
                    'event_loop', action='advance', ms=ms, max_tasks=1)

            client.configure_clock('logical', epoch_ms=1700000000000)
            for path, (mime, body) in RESOURCES.items():
                client.put_resource(fixture.origin + path, body.decode('utf-8'), headers=[['Content-Type', mime]])
            client.load_page(fixture.origin + '/', HTML.decode('utf-8'))
            client.eval("(()=>{const s=document.createElement('script');s.src='/async-start.js';document.head.appendChild(s);return null})()")
            initial = client.eval('asyncProof')
            result['initial'] = initial
            cursor.observe(initial['events'])
            deadline = time.monotonic() + wall_seconds
            while not initial['done'] and len(result['steps']) < max_steps:
                if time.monotonic() >= deadline:
                    raise TimeoutError('bounded asynchronous consumption deadline exceeded')
                before = status()
                due = before['next_due_ms']
                ms = max(0, (due if due is not None else before['now_ms']) - before['now_ms'])
                after = advance(ms)
                page = client.eval('asyncProof')
                step = {'before': before, 'advance_ms': ms, 'after': after, 'observed_labels': page['events']}
                result['steps'].append(step)
                if after['executed'] > 1:
                    raise ValueError('one-task host budget exceeded')
                if page['errors']:
                    raise ValueError('page reported execution error')
                step['consumed_group'] = cursor.observe(page['events'])
                initial = page
                if not page['done']:
                    time.sleep(.005)  # Give the independent Worker process wall-clock execution time.
            result['final'] = initial
            cursor.finish()
            if not initial['done'] or initial['errors'] or initial['intervalCount'] != 3:
                raise ValueError('local page did not reach its terminal state')
            result['passed'] = True
        except Exception as exc:
            result['error'] = str(exc)
        finally:
            result['groups_consumed'] = cursor.position
            client.close()
    return result
