"""Protocol-only parent/child Worker acknowledgement state machine."""
from dataclasses import dataclass

from .worker_token_protocol import TokenError


@dataclass(frozen=True)
class Ack:
    worker_id: int
    sequence: int
    task_id: int
    status: str


class StateError(ValueError):
    pass


class WorkerReplayState:
    def __init__(self, worker_id):
        if type(worker_id) is not int or worker_id <= 0:
            raise StateError('worker identity must be positive')
        self.worker_id = worker_id
        self.ready = False
        self.terminated = False
        self.next_sequence = 1
        self.pending = {}
        self.completed = set()

    def child_ready(self, worker_id, task_epoch):
        if worker_id != self.worker_id or type(task_epoch) is not int or task_epoch <= 0:
            raise StateError('ready identity mismatch')
        if self.terminated or self.ready:
            raise StateError('worker ready state is stale or duplicated')
        self.ready = True
        return {'worker_id': worker_id, 'task_epoch': task_epoch, 'status': 'ready'}

    def select(self, worker_id, sequence, task_id):
        if self.terminated or not self.ready:
            raise StateError('worker is not ready')
        if worker_id != self.worker_id or type(sequence) is not int or sequence != self.next_sequence:
            raise StateError('message sequence or worker identity is stale')
        if type(task_id) is not int or task_id <= 0 or task_id in self.completed:
            raise StateError('child task identity is invalid')
        self.pending[sequence] = task_id
        self.next_sequence += 1
        return {'worker_id': worker_id, 'sequence': sequence, 'task_id': task_id, 'status': 'selected'}

    def acknowledge(self, ack):
        if self.terminated or not self.ready:
            raise StateError('acknowledgement after termination or before ready')
        if not isinstance(ack, Ack) or ack.worker_id != self.worker_id:
            raise StateError('acknowledgement worker identity mismatch')
        task = self.pending.get(ack.sequence)
        if task is None or task != ack.task_id or ack.status not in ('checkpointed', 'failed'):
            raise StateError('acknowledgement does not close selected task')
        del self.pending[ack.sequence]
        self.completed.add(task)
        return True

    def terminate(self):
        if self.terminated:
            raise StateError('duplicate termination')
        self.terminated = True
        self.pending.clear()

