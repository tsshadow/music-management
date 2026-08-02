import unittest
from datetime import datetime, timedelta

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.soundcloud.unavailable_tracks import (
    InMemoryUnavailableStore,
    UnavailableTracks,
    is_still_written_off,
)

NOW = datetime(2026, 8, 2, 12, 0, 0)
DAY = timedelta(days=1)


class WriteOffWindowTest(unittest.TestCase):

    def test_a_track_seen_just_now_is_still_written_off(self):
        self.assertTrue(is_still_written_off(NOW, retry_days=30, now=NOW))

    def test_a_track_inside_the_window_is_still_written_off(self):
        self.assertTrue(is_still_written_off(NOW - 29 * DAY, retry_days=30, now=NOW))

    def test_a_track_past_the_window_is_worth_another_try(self):
        self.assertFalse(is_still_written_off(NOW - 31 * DAY, retry_days=30, now=NOW))

    def test_a_retry_window_of_zero_days_never_writes_anything_off(self):
        self.assertFalse(is_still_written_off(NOW, retry_days=0, now=NOW))


class UnavailableTracksTest(unittest.TestCase):

    def setUp(self):
        self.now = NOW
        self.store = InMemoryUnavailableStore()
        self.tracks = UnavailableTracks(store=self.store, retry_days=30,
                                        now=lambda: self.now)

    def test_an_unknown_track_is_not_skipped(self):
        self.assertFalse(self.tracks.should_skip('dj_a', 't1'))

    def test_a_remembered_track_is_skipped(self):
        self.tracks.remember('dj_a', 't1', reason='403')
        self.assertTrue(self.tracks.should_skip('dj_a', 't1'))

    def test_a_remembered_track_is_only_skipped_for_its_own_account(self):
        self.tracks.remember('dj_a', 't1', reason='403')
        self.assertFalse(self.tracks.should_skip('dj_b', 't1'))

    def test_a_remembered_track_is_tried_again_once_the_window_passes(self):
        self.tracks.remember('dj_a', 't1', reason='403')
        self.now = NOW + 31 * DAY
        self.assertFalse(self.tracks.should_skip('dj_a', 't1'))

    def test_remembering_a_track_again_restarts_its_window(self):
        self.tracks.remember('dj_a', 't1', reason='403')
        self.now = NOW + 20 * DAY
        self.tracks.remember('dj_a', 't1', reason='403')
        self.now = NOW + 40 * DAY
        self.assertTrue(self.tracks.should_skip('dj_a', 't1'))

    def test_the_first_sighting_is_kept_when_a_track_is_seen_again(self):
        self.tracks.remember('dj_a', 't1', reason='403')
        self.now = NOW + 20 * DAY
        self.tracks.remember('dj_a', 't1', reason='403')
        self.assertEqual(self.store.rows[('dj_a', 't1')]['first_seen'], NOW)

    def test_a_track_without_an_id_is_never_remembered(self):
        self.tracks.remember('dj_a', None, reason='403')
        self.assertEqual(self.store.rows, {})

    def test_a_track_without_an_id_is_never_skipped(self):
        self.assertFalse(self.tracks.should_skip('dj_a', None))

    def test_a_broken_store_does_not_stop_the_download(self):
        class BrokenStore:
            def load(self, account, track_id):
                raise RuntimeError('database is down')

            def remember(self, account, track_id, reason, when):
                raise RuntimeError('database is down')

        tracks = UnavailableTracks(store=BrokenStore(), retry_days=30, now=lambda: NOW)
        self.assertFalse(tracks.should_skip('dj_a', 't1'))
        tracks.remember('dj_a', 't1', reason='403')


if __name__ == '__main__':
    unittest.main()
