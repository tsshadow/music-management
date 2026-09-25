"""The pass that goes looking for the tail of an account."""

import unittest
from datetime import datetime
from unittest import mock

import pytest

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.deep_sweep import FlatTrack, ListingFailed
from services.downloader.rate_state import InMemoryRateStateStore, RateLimited, RateState
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.timing import load_timing
from services.downloader.write_offs import InMemoryWriteOffStore, WriteOffs

pytestmark = pytest.mark.mock_base('yt_dlp')

NOW = datetime(2026, 8, 23, 12, 0, 0)


class StubNotifier:
    def notify(self, message, title='Music Management'):
        return None


def listing(*ids):
    return [FlatTrack(track_id, f'https://soundcloud.com/dj_a/{track_id}', track_id) for track_id in ids]


class DeepSweepSoundcloudTest(unittest.TestCase):
    def setUp(self):
        self.timing = load_timing('soundcloud', overrides={'deep_sweep_max_downloads': 2})
        self.write_off_store = InMemoryWriteOffStore()
        self.check_store = InMemoryCheckStore()
        self.downloader = SoundcloudDownloader(
            timing=self.timing,
            rate_state=RateState('soundcloud', self.timing, store=InMemoryRateStateStore()),
            schedule=AccountSchedule('soundcloud', store=self.check_store, now=lambda: NOW),
            unavailable=WriteOffs('soundcloud', store=self.write_off_store, retry_days=30, now=lambda: NOW),
            notifier=StubNotifier(),
        )
        # No text archive on disk; the database is the only record here.
        self.downloader.downloader_config['archive_file'] = None
        self.downloader.downloader_config['archive_dir'] = '/nonexistent'
        self.fetched = []
        self.downloader.download_url = self._record

    def _record(self, url, yt_dl_opts=None, account=None):
        self.fetched.append(url)

    def _sweep(self, tracks, held, held_after=None):
        after = held if held_after is None else held_after
        with (
            mock.patch('services.downloader.soundcloud.soundcloud.list_flat', return_value=tracks),
            mock.patch(
                'services.downloader.soundcloud.soundcloud.SoundcloudArchive.held_ids', side_effect=[held, after]
            ),
        ):
            return self.downloader.deep_sweep_account('dj_a', {})

    def test_it_fetches_the_tracks_the_archive_does_not_hold(self):
        report = self._sweep(listing('a', 'b'), held={'a'}, held_after={'a', 'b'})

        self.assertEqual(['https://soundcloud.com/dj_a/b'], self.fetched)
        self.assertTrue(report.complete)

    def test_it_reaches_a_gap_behind_a_track_it_already_holds(self):
        # This is the whole point: break_on_existing would stop at 'held'.
        self._sweep(listing('new', 'held', 'gap'), held={'held'}, held_after={'held', 'new', 'gap'})

        self.assertEqual(['https://soundcloud.com/dj_a/new', 'https://soundcloud.com/dj_a/gap'], self.fetched)

    def test_an_account_with_no_gaps_fetches_nothing_and_is_complete(self):
        report = self._sweep(listing('a', 'b'), held={'a', 'b'})

        self.assertEqual([], self.fetched)
        self.assertTrue(report.complete)
        self.assertEqual(0, report.wanted)

    def test_it_stops_at_the_cap_and_reports_the_pass_unfinished(self):
        report = self._sweep(listing('a', 'b', 'c'), held=set(), held_after={'a', 'b'})

        self.assertEqual(2, len(self.fetched))
        self.assertTrue(report.capped)
        self.assertFalse(report.complete)

    def test_a_track_that_did_not_arrive_counts_as_a_failure(self):
        self._sweep(listing('a'), held=set(), held_after=set())

        row = self.write_off_store.rows[('soundcloud', 'dj_a', 'a')]
        self.assertEqual(1, row.attempts)
        self.assertEqual('failing', row.reason)

    def test_a_track_rejected_during_this_pass_is_not_counted_as_a_failure(self):
        self.write_off_store.remember('soundcloud', 'dj_a', 'a', 'too_short', NOW, 30, 0)
        with (
            mock.patch('services.downloader.soundcloud.soundcloud.list_flat', return_value=listing('a')),
            mock.patch(
                'services.downloader.soundcloud.soundcloud.SoundcloudArchive.held_ids', side_effect=[set(), set()]
            ),
        ):
            # The ledger was empty when the pass started; the filter wrote the
            # verdict while it ran.
            self.downloader.unavailable.load_many = lambda account, ids: {}
            self.downloader.deep_sweep_account('dj_a', {})

        self.assertEqual(0, self.write_off_store.rows[('soundcloud', 'dj_a', 'a')].attempts)

    def test_a_written_off_track_is_not_fetched_again(self):
        self.write_off_store.remember('soundcloud', 'dj_a', 'a', '403', NOW, None, 0)

        report = self._sweep(listing('a'), held=set())

        self.assertEqual([], self.fetched)
        self.assertTrue(report.complete)
        self.assertEqual(1, report.written_off)

    def test_a_short_track_is_wanted_again_once_the_floor_drops_below_it(self):
        self.write_off_store.remember('soundcloud', 'dj_a', 'a', 'too_short', NOW, 30, 0)

        with mock.patch('services.downloader.soundcloud.soundcloud.DURATION_BOUNDS', (10, 21600)):
            report = self._sweep(listing('a'), held=set(), held_after={'a'})

        self.assertEqual(['https://soundcloud.com/dj_a/a'], self.fetched)
        self.assertTrue(report.complete)


class DeepSweepBranchTest(unittest.TestCase):
    """Which of the two paths one account takes."""

    def setUp(self):
        self.timing = load_timing('soundcloud', overrides={})
        self.check_store = InMemoryCheckStore()
        self.downloader = SoundcloudDownloader(
            timing=self.timing,
            rate_state=RateState('soundcloud', self.timing, store=InMemoryRateStateStore()),
            schedule=AccountSchedule('soundcloud', store=self.check_store, now=lambda: NOW),
            unavailable=WriteOffs('soundcloud', store=InMemoryWriteOffStore(), retry_days=30, now=lambda: NOW),
            notifier=StubNotifier(),
        )

    def test_an_account_never_deep_swept_takes_the_deep_path(self):
        with (
            mock.patch.object(self.downloader, 'deep_sweep_account') as deep,
            mock.patch.object(self.downloader, '_probe') as probe,
        ):
            deep.return_value = mock.Mock(complete=True)
            self.downloader._check_account('dj_a', {})

        deep.assert_called_once()
        probe.assert_not_called()

    def test_a_finished_pass_is_recorded_so_the_cadence_starts(self):
        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep:
            deep.return_value = mock.Mock(complete=True)
            self.downloader._check_account('dj_a', {})

        self.assertEqual(NOW, self.check_store.load('soundcloud')['dj_a'].last_deep_sweep_at)

    def test_an_unfinished_pass_leaves_the_account_deep_due(self):
        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep:
            deep.return_value = mock.Mock(complete=False)
            self.downloader._check_account('dj_a', {})

        self.assertEqual({}, self.check_store.load('soundcloud'))
        self.assertTrue(self.downloader.policy.deep_due('dj_a'))

    def test_a_recently_deep_swept_account_goes_back_to_the_probe(self):
        self.downloader.policy.schedule.mark_deep_swept('dj_a')

        with (
            mock.patch.object(self.downloader, 'deep_sweep_account') as deep,
            mock.patch.object(self.downloader, '_probe', return_value=None),
            mock.patch.object(self.downloader, 'download_account') as download,
        ):
            self.downloader._check_account('dj_a', {})

        deep.assert_not_called()
        download.assert_called_once()

    def test_deep_mode_forces_the_deep_path_whatever_the_cadence_says(self):
        self.downloader.policy.schedule.mark_deep_swept('dj_a')
        self.downloader.deep_mode = True

        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep:
            deep.return_value = mock.Mock(complete=True)
            self.downloader._check_account('dj_a', {})

        deep.assert_called_once()


class RefusedListingTest(unittest.TestCase):
    """A listing that did not come back must neither finish the account nor end a blank run."""

    def setUp(self):
        self.timing = load_timing('soundcloud', overrides={})
        self.check_store = InMemoryCheckStore()
        self.downloader = SoundcloudDownloader(
            timing=self.timing,
            rate_state=RateState('soundcloud', self.timing, store=InMemoryRateStateStore()),
            schedule=AccountSchedule('soundcloud', store=self.check_store, now=lambda: NOW),
            unavailable=WriteOffs('soundcloud', store=InMemoryWriteOffStore(), retry_days=30, now=lambda: NOW),
            notifier=StubNotifier(),
        )
        self.downloader.downloader_config['archive_file'] = None
        self.downloader.downloader_config['archive_dir'] = '/nonexistent'

    def _check(self, error, account='dj_a'):
        with (
            mock.patch('services.downloader.soundcloud.soundcloud.list_flat', side_effect=error) as listing,
            mock.patch.object(self.downloader.policy, 'note_progress') as progress,
            mock.patch.object(self.downloader, 'download_account') as full_run,
        ):
            try:
                self.downloader._check_account(account, {})
            finally:
                self.progress = progress
                self.listing = listing
                self.full_run = full_run

    @staticmethod
    def _refused(account='dj_a'):
        return ListingFailed(f'https://soundcloud.com/{account}/tracks', 'HTTP Error 403: Forbidden')

    def test_a_403_on_the_listing_counts_as_one_blank_account_and_leaves_it_deep_due(self):
        # The same reading `_settle` gives a full run that got nothing back: an
        # account that is private or region-blocked answers 403 too.
        self._check(self._refused())

        self.assertEqual(1, self.downloader.policy._blank_run)
        self.assertEqual(0, self.downloader.policy.rate_state.cooldown_remaining())
        self.assertTrue(self.downloader.policy.deep_due('dj_a'))
        self.progress.assert_not_called()
        # Not asked a second time through the probe or the full run.
        self.assertEqual(1, self.listing.call_count)
        self.full_run.assert_not_called()

    def test_block_threshold_refused_listings_in_a_row_park_the_source(self):
        for index in range(self.timing.block_threshold - 1):
            self._check(self._refused(f'dj_{index}'), account=f'dj_{index}')

        with self.assertRaises(RateLimited) as raised:
            self._check(self._refused('dj_last'), account='dj_last')

        self.assertEqual('403', raised.exception.reason)
        self.assertGreater(self.downloader.policy.rate_state.cooldown_remaining(), 0)

    def test_a_refused_probe_counts_as_a_blank_account_too(self):
        self.downloader.deep_mode = False
        with (
            mock.patch.object(self.downloader.policy, 'deep_due', return_value=False),
            mock.patch('services.downloader.soundcloud.soundcloud.newest_track', side_effect=self._refused()),
        ):
            self._check(self._refused())

        self.assertEqual(1, self.downloader.policy._blank_run)
        self.full_run.assert_not_called()

    def test_a_429_on_the_listing_parks_the_source_without_resetting_the_blank_run(self):
        # The blank counter is the only evidence of a 403 storm; a listing that
        # never came back must not wipe it.
        with self.assertRaises(RateLimited) as raised:
            self._check(ListingFailed('https://soundcloud.com/dj_a/tracks', 'HTTP Error 429: Too Many Requests'))

        self.assertEqual('429', raised.exception.reason)
        self.progress.assert_not_called()
        self.assertTrue(self.downloader.policy.deep_due('dj_a'))

    def test_an_account_name_with_403_in_it_is_not_a_refusal(self):
        self._check(ListingFailed('https://soundcloud.com/dj-403/tracks', 'Unable to download JSON metadata'), 'dj-403')

        self.assertEqual(0, self.downloader.policy.rate_state.cooldown_remaining())
        self.assertEqual(0, self.downloader.policy._blank_run)

    def test_any_other_listing_failure_falls_through_to_the_ordinary_check(self):
        self._check(ListingFailed('https://soundcloud.com/dj_a/tracks', 'Unable to download JSON metadata'))

        self.full_run.assert_called_once_with('dj_a', {})
        self.progress.assert_not_called()
        self.assertTrue(self.downloader.policy.deep_due('dj_a'))
        self.assertEqual(0, self.downloader.policy.rate_state.cooldown_remaining())


if __name__ == '__main__':
    unittest.main()
