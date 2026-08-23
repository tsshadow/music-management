import unittest
from datetime import datetime, timedelta

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.write_offs import (
    InMemoryWriteOffStore,
    WriteOff,
    WriteOffs,
    is_still_written_off,
    still_written_off,
)

NOW = datetime(2026, 8, 23, 12, 0, 0)
DAY = timedelta(days=1)


def duration_row(seconds: int) -> WriteOff:
    reason = 'too_short' if seconds < 60 else 'too_long'
    return WriteOff(reason=reason, last_seen=NOW, duration=seconds, attempts=0)


class WriteOffWindowTest(unittest.TestCase):

    def test_a_track_seen_just_now_is_still_written_off(self):
        self.assertTrue(is_still_written_off(NOW, retry_days=30, now=NOW))

    def test_a_track_inside_the_window_is_still_written_off(self):
        self.assertTrue(is_still_written_off(NOW - 29 * DAY, retry_days=30, now=NOW))

    def test_a_track_past_the_window_is_worth_another_try(self):
        self.assertFalse(is_still_written_off(NOW - 31 * DAY, retry_days=30, now=NOW))

    def test_a_retry_window_of_zero_days_never_writes_anything_off(self):
        self.assertFalse(is_still_written_off(NOW, retry_days=0, now=NOW))


class DurationVerdictTest(unittest.TestCase):

    def test_a_short_track_stays_written_off_under_the_bounds_that_judged_it(self):
        self.assertTrue(still_written_off(duration_row(30), 30, NOW, (60, 21600)))

    def test_a_short_track_comes_back_once_the_floor_drops_below_it(self):
        self.assertFalse(still_written_off(duration_row(30), 30, NOW, (10, 21600)))

    def test_a_long_track_comes_back_once_the_ceiling_rises_above_it(self):
        self.assertFalse(still_written_off(duration_row(30000), 30, NOW, (60, 40000)))

    def test_a_duration_row_without_a_duration_is_trusted(self):
        entry = WriteOff(reason='too_short', last_seen=NOW, duration=None, attempts=0)
        self.assertTrue(still_written_off(entry, 30, NOW, (10, 21600)))

    def test_a_duration_row_is_trusted_when_no_bounds_are_offered(self):
        self.assertTrue(still_written_off(duration_row(30), 30, NOW, None))

    def test_a_403_still_expires_on_its_window_and_ignores_the_bounds(self):
        entry = WriteOff(reason='403', last_seen=NOW - 31 * DAY, duration=None, attempts=0)
        self.assertFalse(still_written_off(entry, 30, NOW, (60, 21600)))

    def test_a_recent_403_is_still_written_off(self):
        entry = WriteOff(reason='403', last_seen=NOW - 29 * DAY, duration=None, attempts=0)
        self.assertTrue(still_written_off(entry, 30, NOW, (60, 21600)))


class WriteOffsTest(unittest.TestCase):

    def setUp(self):
        self.store = InMemoryWriteOffStore()
        self.offs = WriteOffs('soundcloud', store=self.store, retry_days=30,
                              now=lambda: NOW)

    def test_an_unknown_track_is_not_skipped(self):
        self.assertFalse(self.offs.should_skip('dj_a', 't1'))

    def test_a_remembered_track_is_skipped(self):
        self.offs.remember('dj_a', 't1', reason='403')
        self.assertTrue(self.offs.should_skip('dj_a', 't1'))

    def test_a_remembered_track_is_only_skipped_for_its_own_account(self):
        self.offs.remember('dj_a', 't1', reason='403')
        self.assertFalse(self.offs.should_skip('dj_b', 't1'))

    def test_a_write_off_is_scoped_to_its_source(self):
        self.offs.remember('dj_a', 't1', reason='403')
        other = WriteOffs('youtube', store=self.store, retry_days=30, now=lambda: NOW)
        self.assertFalse(other.should_skip('dj_a', 't1'))

    def test_a_track_without_an_id_is_never_skipped_or_stored(self):
        self.offs.remember('dj_a', None, reason='403')
        self.assertFalse(self.offs.should_skip('dj_a', None))
        self.assertEqual({}, self.store.rows)

    def test_a_duration_write_off_stores_what_it_measured(self):
        self.offs.remember('dj_a', 't1', reason='too_short', duration=30)
        self.assertEqual(30, self.store.rows[('soundcloud', 'dj_a', 't1')].duration)

    def test_load_many_returns_only_the_tracks_asked_about(self):
        self.offs.remember('dj_a', 't1', reason='403')
        self.offs.remember('dj_a', 't2', reason='too_short', duration=30)
        found = self.offs.load_many('dj_a', ['t1', 't3'])
        self.assertEqual(['t1'], sorted(found))

    def test_load_many_of_nothing_is_empty(self):
        self.assertEqual({}, self.offs.load_many('dj_a', []))

    def test_a_broken_store_does_not_write_anything_off(self):
        class BrokenStore:
            def load(self, *args):
                raise RuntimeError('database is down')

            def remember(self, *args):
                raise RuntimeError('database is down')

        offs = WriteOffs('soundcloud', store=BrokenStore(), retry_days=30,
                         now=lambda: NOW)
        self.assertFalse(offs.should_skip('dj_a', 't1'))
        offs.remember('dj_a', 't1', reason='403')

    def test_load_many_raises_rather_than_hiding_a_broken_store(self):
        class BrokenStore:
            def load_many(self, *args):
                raise RuntimeError('database is down')

        offs = WriteOffs('soundcloud', store=BrokenStore(), retry_days=30,
                         now=lambda: NOW)
        with self.assertRaises(RuntimeError):
            offs.load_many('dj_a', ['t1'])


class NoteFailureTest(unittest.TestCase):

    def setUp(self):
        self.store = InMemoryWriteOffStore()
        self.offs = WriteOffs('soundcloud', store=self.store, retry_days=30,
                              now=lambda: NOW)

    def test_the_first_two_failures_do_not_write_the_track_off(self):
        self.assertFalse(self.offs.note_failure('dj_a', 't1'))
        self.assertFalse(self.offs.note_failure('dj_a', 't1'))

    def test_the_third_failure_writes_it_off(self):
        for _ in range(2):
            self.offs.note_failure('dj_a', 't1')
        self.assertTrue(self.offs.note_failure('dj_a', 't1'))
        self.assertEqual('failed', self.store.rows[('soundcloud', 'dj_a', 't1')].reason)

    def test_a_failing_track_is_held_back_for_its_retry_window(self):
        self.offs.note_failure('dj_a', 't1')
        self.assertTrue(self.offs.should_skip('dj_a', 't1'))

    def test_a_failure_does_not_erase_a_measured_duration(self):
        self.offs.remember('dj_a', 't1', reason='too_short', duration=30)
        self.offs.note_failure('dj_a', 't1')
        self.assertEqual(30, self.store.rows[('soundcloud', 'dj_a', 't1')].duration)
