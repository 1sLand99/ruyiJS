"""Parent/child acknowledgement state machine negative cases."""
import unittest

from tools.trace_audit.worker_replay_state import Ack, StateError, WorkerReplayState


class WorkerReplayStateTests(unittest.TestCase):
    def state(self):
        state = WorkerReplayState(7); state.child_ready(7, 1); return state

    def test_ready_select_acknowledge(self):
        state = self.state(); selected = state.select(7, 1, 31)
        self.assertEqual(selected['status'], 'selected')
        self.assertTrue(state.acknowledge(Ack(7, 1, 31, 'checkpointed')))

    def test_equal_payloads_use_sequence(self):
        state = self.state(); self.assertEqual(state.select(7, 1, 31)['sequence'], 1)
        self.assertTrue(state.acknowledge(Ack(7, 1, 31, 'checkpointed')))
        self.assertEqual(state.select(7, 2, 32)['sequence'], 2)

    def test_wrong_worker_ready_rejected(self):
        with self.assertRaisesRegex(StateError, 'identity'):
            WorkerReplayState(7).child_ready(8, 1)

    def test_duplicate_ready_rejected(self):
        state = self.state()
        with self.assertRaisesRegex(StateError, 'stale|duplicated'):
            state.child_ready(7, 2)

    def test_select_before_ready_rejected(self):
        with self.assertRaisesRegex(StateError, 'ready'):
            WorkerReplayState(7).select(7, 1, 31)

    def test_sequence_gap_rejected(self):
        state = self.state()
        with self.assertRaisesRegex(StateError, 'sequence'):
            state.select(7, 2, 31)

    def test_wrong_task_ack_rejected(self):
        state = self.state(); state.select(7, 1, 31)
        with self.assertRaisesRegex(StateError, 'close'):
            state.acknowledge(Ack(7, 1, 99, 'checkpointed'))

    def test_duplicate_ack_rejected(self):
        state = self.state(); state.select(7, 1, 31); ack = Ack(7, 1, 31, 'checkpointed'); state.acknowledge(ack)
        with self.assertRaisesRegex(StateError, 'close'):
            state.acknowledge(ack)

    def test_terminate_clears_pending_and_rejects_late_ack(self):
        state = self.state(); state.select(7, 1, 31); state.terminate()
        with self.assertRaisesRegex(StateError, 'termination'):
            state.acknowledge(Ack(7, 1, 31, 'checkpointed'))
        with self.assertRaisesRegex(StateError, 'ready'):
            state.select(7, 2, 32)

    def test_failure_ack_is_terminal(self):
        state = self.state(); state.select(7, 1, 31)
        self.assertTrue(state.acknowledge(Ack(7, 1, 31, 'failed')))


if __name__ == '__main__': unittest.main()
