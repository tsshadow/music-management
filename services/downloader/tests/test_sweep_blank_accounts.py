import unittest
from datetime import datetime

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateLimited, RateState
from services.downloader.sweep import SweepPolicy
from services.downloader.timing import load_timing

NOW = datetime(2026, 8, 2, 12, 0, 0)


class StubNotifier:
    """Stub notifier for test isolation — prevents sweep.py lazy import."""

    def notify(self, message, title='Music Management'):
        return True


class BlankAccountRunTest(unittest.TestCase):
    """An account can give nothing back without SoundCloud having blocked us.

    One account whose only track is Go+ looks exactly like a block of one. Only a
    run of empty-handed accounts is evidence worth parking the whole source over.
    """

    def setUp(self):
        self.timing = load_timing(
            'soundcloud',
            overrides={
                'backoff_403_base': 240,
                'backoff_403_factor': 4,
                'backoff_403_cap': 3600,
                'block_threshold': 3,
            },
        )
        self.store = InMemoryRateStateStore()

    def _policy(self):
        return SweepPolicy(
            'soundcloud',
            timing=self.timing,
            rate_state=RateState('soundcloud', self.timing, store=self.store, now=lambda: NOW, jitter=lambda: 1.0),
            schedule=AccountSchedule('soundcloud', store=InMemoryCheckStore(), now=lambda: NOW),
            notifier=StubNotifier(),
        )

    def test_a_single_blank_account_does_not_park_the_source(self):
        policy = self._policy()
        self.assertIsNone(policy.note_blank('dj_a'))

    def test_a_single_blank_account_leaves_no_cooldown(self):
        policy = self._policy()
        policy.note_blank('dj_a')
        self.assertEqual(policy.rate_state.cooldown_remaining(), 0)

    def test_blank_accounts_below_the_threshold_do_not_park_the_source(self):
        policy = self._policy()
        self.assertIsNone(policy.note_blank('dj_a'))
        self.assertIsNone(policy.note_blank('dj_b'))

    def test_the_threshold_blank_account_parks_the_source(self):
        policy = self._policy()
        policy.note_blank('dj_a')
        policy.note_blank('dj_b')
        self.assertIsInstance(policy.note_blank('dj_c'), RateLimited)

    def test_parking_on_blanks_stops_the_rest_of_the_sweep(self):
        policy = self._policy()
        for name in ('dj_a', 'dj_b', 'dj_c'):
            policy.note_blank(name)
        self.assertTrue(policy.stop.is_set())

    def test_parking_on_blanks_writes_a_cooldown(self):
        policy = self._policy()
        for name in ('dj_a', 'dj_b', 'dj_c'):
            policy.note_blank(name)
        self.assertEqual(policy.rate_state.cooldown_remaining(), 240)

    def test_an_account_that_gave_something_back_clears_the_run(self):
        policy = self._policy()
        policy.note_blank('dj_a')
        policy.note_blank('dj_b')
        policy.note_progress()
        self.assertIsNone(policy.note_blank('dj_c'))

    def test_a_cleared_run_has_to_build_up_again_from_scratch(self):
        policy = self._policy()
        policy.note_blank('dj_a')
        policy.note_progress()
        policy.note_blank('dj_b')
        policy.note_blank('dj_c')
        self.assertIsInstance(policy.note_blank('dj_d'), RateLimited)

    def test_a_threshold_of_one_parks_on_the_first_blank_account(self):
        self.timing = load_timing(
            'soundcloud',
            overrides={
                'backoff_403_base': 240,
                'block_threshold': 1,
            },
        )
        self.assertIsInstance(self._policy().note_blank('dj_a'), RateLimited)


if __name__ == '__main__':
    unittest.main()
