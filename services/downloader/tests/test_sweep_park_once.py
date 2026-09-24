"""One refusal is one rung of the ladder and one push, however many workers meet it.

A sweep runs its accounts on several worker threads. When the service starts refusing,
every one of them meets the same 403 and used to call `SweepPolicy.park` on its own:
four workers climbed the 403 ladder four rungs and sent four notifications for a single
incident. The first caller now records it; everyone after it, until the next sweep
begins, gets the same `RateLimited` back.
"""

import threading
import unittest
from datetime import datetime, timedelta

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.sweep import SweepPolicy
from services.downloader.timing import load_timing

START = datetime(2026, 9, 24, 12, 0, 0)


class RecordingNotifier:
    """Stands in for the ntfy service and remembers what it was asked to send."""

    def __init__(self):
        self.sent = []
        self._lock = threading.Lock()

    def notify(self, message, title='Music Management'):
        """Remember one notification."""
        with self._lock:
            self.sent.append((title, message))
        return True


class ParkOnceTest(unittest.TestCase):
    def setUp(self):
        self.now = START
        self.notifier = RecordingNotifier()
        timing = load_timing('soundcloud', overrides={'backoff_403_base': 240, 'backoff_403_factor': 4})
        self.rate_state = RateState(
            'soundcloud', timing, store=InMemoryRateStateStore(), now=lambda: self.now, jitter=lambda: 1.0
        )
        self.policy = SweepPolicy(
            'soundcloud',
            timing=timing,
            rate_state=self.rate_state,
            schedule=AccountSchedule('soundcloud', store=InMemoryCheckStore()),
            notifier=self.notifier,
        )
        self.assertTrue(self.policy.begin())

    def test_workers_meeting_the_same_403_climb_one_rung_and_push_once(self):
        workers = 8
        barrier = threading.Barrier(workers)
        results = []
        lock = threading.Lock()

        def worker(n):
            barrier.wait()
            parked = self.policy.park('403', f'account-{n}')
            with lock:
                results.append(parked)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(self.rate_state.snapshot().consecutive_403, 1)
        self.assertEqual(len(self.notifier.sent), 1)
        self.assertEqual(len({id(parked) for parked in results}), 1, 'every worker gets the first answer back')
        self.assertEqual(results[0].wait, 240)

    def test_a_later_call_in_the_same_sweep_is_not_counted_again(self):
        first = self.policy.park('403', 'a')
        second = self.policy.park('429', 'b')
        self.assertIs(second, first)
        snapshot = self.rate_state.snapshot()
        self.assertEqual((snapshot.consecutive_403, snapshot.consecutive_429), (1, 0))

    def test_the_next_sweep_counts_its_own_refusal(self):
        self.policy.park('403', 'a')
        self.now = START + timedelta(seconds=241)
        self.assertTrue(self.policy.begin())
        again = self.policy.park('403', 'a')
        self.assertEqual(self.rate_state.snapshot().consecutive_403, 2)
        self.assertEqual(again.wait, 960)
        self.assertEqual(len(self.notifier.sent), 2)


if __name__ == '__main__':
    unittest.main()
