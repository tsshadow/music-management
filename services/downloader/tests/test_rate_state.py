import unittest
from datetime import datetime, timedelta

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.rate_state import (
    InMemoryRateStateStore,
    RateSnapshot,
    RateState,
    backoff_403_wait,
    next_multiplier_on_429,
    recover,
    wait_after_429,
)
from services.downloader.timing import load_timing

START = datetime(2026, 7, 30, 12, 0, 0)


class LadderMathTest(unittest.TestCase):

    def test_first_429_doubles_the_multiplier(self):
        self.assertEqual(next_multiplier_on_429(1, max_multiplier=16), 2)

    def test_multiplier_stops_at_the_ceiling(self):
        self.assertEqual(next_multiplier_on_429(16, max_multiplier=16), 16)

    def test_multiplier_never_overshoots_the_ceiling(self):
        self.assertEqual(next_multiplier_on_429(12, max_multiplier=16), 16)

    def test_429_wait_is_base_times_multiplier_times_jitter(self):
        self.assertEqual(wait_after_429(base=3600, multiplier=4, jitter=1.25), 18000)

    def test_first_403_waits_the_base(self):
        self.assertEqual(backoff_403_wait(1, base=240, factor=4, cap=86400), 240)

    def test_403_wait_grows_by_the_factor(self):
        self.assertEqual(backoff_403_wait(3, base=240, factor=4, cap=86400), 3840)

    def test_403_wait_stops_at_the_cap(self):
        self.assertEqual(backoff_403_wait(9, base=240, factor=4, cap=86400), 86400)

    def test_403_count_below_one_is_treated_as_the_first(self):
        self.assertEqual(backoff_403_wait(0, base=240, factor=4, cap=86400), 240)

    def test_recovery_needs_enough_clean_runs(self):
        self.assertEqual(recover(multiplier=8, clean_runs=1, recovery_runs=3), (8, 2))

    def test_recovery_halves_the_multiplier_and_resets_the_counter(self):
        self.assertEqual(recover(multiplier=8, clean_runs=2, recovery_runs=3), (4, 0))

    def test_recovery_never_drops_below_one(self):
        self.assertEqual(recover(multiplier=1, clean_runs=2, recovery_runs=3), (1, 0))


class RateStateTest(unittest.TestCase):

    def setUp(self):
        self.store = InMemoryRateStateStore()
        self.now = START
        self.timing = load_timing('soundcloud', overrides={
            'backoff_429_base': 3600,
            'backoff_403_base': 240,
            'backoff_403_factor': 4,
            'backoff_403_cap': 86400,
            'max_multiplier': 16,
            'recovery_runs': 3,
        })

    def _state(self):
        return RateState('soundcloud', self.timing, store=self.store,
                         now=lambda: self.now, jitter=lambda: 1.0)

    def test_a_fresh_source_starts_at_multiplier_one(self):
        self.assertEqual(self._state().multiplier, 1)

    def test_a_fresh_source_has_no_cooldown(self):
        self.assertEqual(self._state().cooldown_remaining(), 0)

    def test_429_sets_a_cooldown_of_base_times_the_new_multiplier(self):
        state = self._state()
        wait = state.record_429()
        self.assertEqual(wait, 7200)
        self.assertEqual(state.cooldown_remaining(), 7200)

    def test_429_raises_the_multiplier(self):
        state = self._state()
        state.record_429()
        self.assertEqual(state.multiplier, 2)

    def test_the_multiplier_survives_a_restart(self):
        self._state().record_429()
        self.assertEqual(self._state().multiplier, 2)

    def test_the_cooldown_survives_a_restart(self):
        self._state().record_429()
        self.assertEqual(self._state().cooldown_remaining(), 7200)

    def test_the_cooldown_shrinks_as_time_passes(self):
        self._state().record_429()
        self.now = START + timedelta(seconds=3600)
        self.assertEqual(self._state().cooldown_remaining(), 3600)

    def test_the_cooldown_is_gone_once_it_has_elapsed(self):
        self._state().record_429()
        self.now = START + timedelta(seconds=7201)
        self.assertEqual(self._state().cooldown_remaining(), 0)

    def test_consecutive_403s_climb_the_ladder(self):
        state = self._state()
        self.assertEqual(state.record_403(), 240)
        self.assertEqual(state.record_403(), 960)
        self.assertEqual(state.record_403(), 3840)

    def test_the_403_count_survives_a_restart(self):
        self._state().record_403()
        self.assertEqual(self._state().record_403(), 960)

    def test_403_also_parks_the_source_for_the_wait_time(self):
        state = self._state()
        state.record_403()
        self.assertEqual(state.cooldown_remaining(), 240)

    def test_a_403_cooldown_survives_a_restart(self):
        self._state().record_403()
        self.assertEqual(self._state().cooldown_remaining(), 240)

    def test_success_clears_the_403_count(self):
        state = self._state()
        state.record_403()
        state.record_success()
        self.assertEqual(state.record_403(), 240)

    def test_the_multiplier_drops_after_enough_clean_runs(self):
        state = self._state()
        state.record_429()
        state.record_429()
        self.assertEqual(state.multiplier, 4)
        for _ in range(3):
            state.record_success()
        self.assertEqual(state.multiplier, 2)

    def test_a_429_wipes_the_progress_towards_recovery(self):
        state = self._state()
        state.record_429()
        state.record_success()
        state.record_success()
        state.record_429()
        state.record_success()
        self.assertEqual(state.multiplier, 4)

    def test_reset_clears_multiplier_and_cooldown(self):
        state = self._state()
        state.record_429()
        state.reset()
        self.assertEqual(state.multiplier, 1)
        self.assertEqual(state.cooldown_remaining(), 0)

    def test_reset_survives_a_restart(self):
        self._state().record_429()
        self._state().reset()
        self.assertEqual(self._state().multiplier, 1)

    def test_snapshot_reports_when_the_last_429_happened(self):
        state = self._state()
        state.record_429()
        self.assertEqual(state.snapshot().last_429_at, START)

    def test_snapshot_reports_the_cooldown_end(self):
        state = self._state()
        state.record_429()
        self.assertEqual(state.snapshot().cooldown_until, START + timedelta(seconds=7200))


class RateStateSurvivesStorageFailureTest(unittest.TestCase):

    class BrokenStore:

        def load(self, source):
            raise RuntimeError('database is down')

        def save(self, snapshot):
            raise RuntimeError('database is down')

    def test_a_broken_store_falls_back_to_neutral_state(self):
        timing = load_timing('soundcloud', overrides={})
        state = RateState('soundcloud', timing, store=self.BrokenStore(), now=lambda: START)
        self.assertEqual(state.multiplier, 1)

    def test_a_broken_store_still_returns_a_wait_time(self):
        timing = load_timing('soundcloud', overrides={'backoff_429_base': 3600, 'max_multiplier': 16})
        state = RateState('soundcloud', timing, store=self.BrokenStore(),
                          now=lambda: START, jitter=lambda: 1.0)
        self.assertEqual(state.record_429(), 7200)


class SnapshotDefaultsTest(unittest.TestCase):

    def test_a_snapshot_defaults_to_a_neutral_multiplier(self):
        self.assertEqual(RateSnapshot(source='youtube').multiplier, 1)


if __name__ == '__main__':
    unittest.main()
