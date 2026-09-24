import unittest
from datetime import datetime, timedelta

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.rate_state import (
    InMemoryRateStateStore,
    RateSnapshot,
    RateState,
    backoff_403_wait,
    decayed_403_count,
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

    def test_a_403_count_that_was_never_set_stays_at_zero(self):
        self.assertEqual(decayed_403_count(0, None, decay=21600, now=START), 0)

    def test_a_fresh_403_count_does_not_decay_yet(self):
        last = START - timedelta(seconds=21599)
        self.assertEqual(decayed_403_count(4, last, decay=21600, now=START), 4)

    def test_one_decay_window_drops_one_step(self):
        last = START - timedelta(seconds=21600)
        self.assertEqual(decayed_403_count(4, last, decay=21600, now=START), 3)

    def test_several_windows_drop_several_steps(self):
        last = START - timedelta(seconds=3 * 21600)
        self.assertEqual(decayed_403_count(4, last, decay=21600, now=START), 1)

    def test_a_long_silence_clears_the_count_entirely(self):
        last = START - timedelta(days=30)
        self.assertEqual(decayed_403_count(7, last, decay=21600, now=START), 0)

    def test_decay_of_zero_seconds_is_treated_as_no_decay(self):
        last = START - timedelta(days=30)
        self.assertEqual(decayed_403_count(7, last, decay=0, now=START), 7)

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
        self.timing = load_timing(
            'soundcloud',
            overrides={
                'backoff_429_base': 3600,
                'backoff_403_base': 240,
                'backoff_403_factor': 4,
                'backoff_403_cap': 86400,
                'max_multiplier': 16,
                'recovery_runs': 3,
            },
        )

    def _state(self):
        return RateState('soundcloud', self.timing, store=self.store, now=lambda: self.now, jitter=lambda: 1.0)

    def test_403s_spread_far_apart_do_not_climb_the_ladder(self):
        """A track that is unavailable once a day must not park the source for a day."""
        state = self._state()
        self.assertEqual(state.record_403(), 240)
        for _ in range(5):
            self.now += timedelta(seconds=self.timing.backoff_403_decay)
            state = self._state()
            self.assertEqual(state.record_403(), 240)

    def test_403s_in_quick_succession_still_climb_the_ladder(self):
        state = self._state()
        self.assertEqual(state.record_403(), 240)
        self.assertEqual(state.record_403(), 960)

    def test_a_quiet_spell_gives_back_rungs_before_the_next_403(self):
        state = self._state()
        state.record_403()
        state.record_403()
        state.record_403()
        self.now += timedelta(seconds=2 * self.timing.backoff_403_decay)
        self.assertEqual(self._state().record_403(), 960)

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
        state = RateState('soundcloud', timing, store=self.BrokenStore(), now=lambda: START, jitter=lambda: 1.0)
        self.assertEqual(state.record_429(), 7200)


class ChangedElsewhereTest(unittest.TestCase):
    """A reset from the management page while a sweep holds its RateState must stick.

    The sweep wrote its in-memory copy back at finish(), so the reset was silently
    undone by the state from before it.
    """

    setUp = RateStateTest.setUp
    _state = RateStateTest._state

    def test_a_reset_during_a_sweep_survives_the_sweeps_finish(self):
        sweep = self._state()
        for _ in range(3):
            sweep.record_429()
        self.assertEqual(self.store.load("soundcloud").multiplier, 8)

        self._state().reset()  # another process: the reset endpoint
        sweep.record_success()

        stored = self.store.load('soundcloud')
        self.assertEqual(stored.multiplier, 1)
        self.assertIsNone(stored.cooldown_until)
        self.assertEqual(stored.clean_runs, 1, 'the clean run is merged onto the reset, not dropped')

    def test_a_403_after_a_reset_starts_the_ladder_from_the_bottom(self):
        sweep = self._state()
        for _ in range(3):
            sweep.record_403()
        self._state().reset()
        self.assertEqual(sweep.record_403(), 240)

    def test_the_sweeps_own_writes_are_not_mistaken_for_someone_elses(self):
        sweep = self._state()
        sweep.record_429()
        sweep.record_success()
        self.assertEqual(self.store.load('soundcloud').multiplier, 2)
        self.assertEqual(self.store.load('soundcloud').clean_runs, 1)

    def test_whole_second_storage_does_not_read_as_a_change(self):
        # DATETIME keeps whole seconds; what comes back has no microseconds.
        class SecondsStore(InMemoryRateStateStore):
            def save(self, snapshot):
                values = {
                    k: (v.replace(microsecond=0) if isinstance(v, datetime) else v) for k, v in vars(snapshot).items()
                }
                super().save(RateSnapshot(**values))

        self.store = SecondsStore()
        self.now = START + timedelta(microseconds=500000)
        sweep = self._state()
        sweep.record_403()
        with self.assertNoLogs(level='INFO'):
            sweep.record_success()


class SnapshotDefaultsTest(unittest.TestCase):
    def test_a_snapshot_defaults_to_a_neutral_multiplier(self):
        self.assertEqual(RateSnapshot(source='youtube').multiplier, 1)


if __name__ == '__main__':
    unittest.main()
