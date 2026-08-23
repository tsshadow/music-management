"""The pass that goes looking for the tail of an account."""
import unittest
from datetime import datetime
from unittest import mock

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.deep_sweep import FlatTrack
from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.timing import load_timing
from services.downloader.write_offs import InMemoryWriteOffStore, WriteOffs

NOW = datetime(2026, 8, 23, 12, 0, 0)


class StubNotifier:
    def notify(self, message, title='Music Management'):
        return None


def listing(*ids):
    return [FlatTrack(track_id, f'https://soundcloud.com/dj_a/{track_id}', track_id)
            for track_id in ids]


class DeepSweepSoundcloudTest(unittest.TestCase):

    def setUp(self):
        self.timing = load_timing('soundcloud',
                                  overrides={'deep_sweep_max_downloads': 2})
        self.write_off_store = InMemoryWriteOffStore()
        self.check_store = InMemoryCheckStore()
        self.downloader = SoundcloudDownloader(
            timing=self.timing,
            rate_state=RateState('soundcloud', self.timing,
                                 store=InMemoryRateStateStore()),
            schedule=AccountSchedule('soundcloud', store=self.check_store,
                                     now=lambda: NOW),
            unavailable=WriteOffs('soundcloud', store=self.write_off_store,
                                  retry_days=30, now=lambda: NOW),
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
        with mock.patch('services.downloader.soundcloud.soundcloud.list_flat',
                        return_value=tracks), \
             mock.patch('services.downloader.soundcloud.soundcloud.SoundcloudArchive'
                        '.held_ids', side_effect=[held, after]):
            return self.downloader.deep_sweep_account('dj_a', {})

    def test_it_fetches_the_tracks_the_archive_does_not_hold(self):
        report = self._sweep(listing('a', 'b'), held={'a'}, held_after={'a', 'b'})

        self.assertEqual(['https://soundcloud.com/dj_a/b'], self.fetched)
        self.assertTrue(report.complete)

    def test_it_reaches_a_gap_behind_a_track_it_already_holds(self):
        # This is the whole point: break_on_existing would stop at 'held'.
        self._sweep(listing('new', 'held', 'gap'), held={'held'},
                    held_after={'held', 'new', 'gap'})

        self.assertEqual(['https://soundcloud.com/dj_a/new',
                          'https://soundcloud.com/dj_a/gap'], self.fetched)

    def test_an_account_with_no_gaps_fetches_nothing_and_is_complete(self):
        report = self._sweep(listing('a', 'b'), held={'a', 'b'})

        self.assertEqual([], self.fetched)
        self.assertTrue(report.complete)
        self.assertEqual(0, report.wanted)

    def test_it_stops_at_the_cap_and_reports_the_pass_unfinished(self):
        report = self._sweep(listing('a', 'b', 'c'), held=set(),
                             held_after={'a', 'b'})

        self.assertEqual(2, len(self.fetched))
        self.assertTrue(report.capped)
        self.assertFalse(report.complete)

    def test_a_track_that_did_not_arrive_counts_as_a_failure(self):
        self._sweep(listing('a'), held=set(), held_after=set())

        row = self.write_off_store.rows[('soundcloud', 'dj_a', 'a')]
        self.assertEqual(1, row.attempts)
        self.assertEqual('failing', row.reason)

    def test_a_track_rejected_during_this_pass_is_not_counted_as_a_failure(self):
        self.write_off_store.remember('soundcloud', 'dj_a', 'a', 'too_short',
                                      NOW, 30, 0)
        with mock.patch('services.downloader.soundcloud.soundcloud.list_flat',
                        return_value=listing('a')), \
             mock.patch('services.downloader.soundcloud.soundcloud.SoundcloudArchive'
                        '.held_ids', side_effect=[set(), set()]):
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
        self.write_off_store.remember('soundcloud', 'dj_a', 'a', 'too_short',
                                      NOW, 30, 0)

        with mock.patch('services.downloader.soundcloud.soundcloud.DURATION_BOUNDS',
                        (10, 21600)):
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
            rate_state=RateState('soundcloud', self.timing,
                                 store=InMemoryRateStateStore()),
            schedule=AccountSchedule('soundcloud', store=self.check_store,
                                     now=lambda: NOW),
            unavailable=WriteOffs('soundcloud', store=InMemoryWriteOffStore(),
                                  retry_days=30, now=lambda: NOW),
            notifier=StubNotifier(),
        )

    def test_an_account_never_deep_swept_takes_the_deep_path(self):
        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep, \
             mock.patch.object(self.downloader, '_probe') as probe:
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

        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep, \
             mock.patch.object(self.downloader, '_probe', return_value=None), \
             mock.patch.object(self.downloader, 'download_account') as download:
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


if __name__ == '__main__':
    unittest.main()
