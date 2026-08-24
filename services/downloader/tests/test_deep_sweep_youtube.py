"""The pass that goes looking for the tail of a YouTube channel."""
import unittest
from unittest import mock

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.deep_sweep import FlatTrack
from services.downloader.rate_state import InMemoryRateStateStore, RateState, SweepAborted
from services.downloader.timing import load_timing
from services.downloader.write_offs import InMemoryWriteOffStore, WriteOffs
from services.downloader.youtube.youtube import YoutubeDownloader
from services.downloader.youtube.YoutubeAccount import AUDIO, VIDEO, YoutubeAccount


class StubNotifier:
    def notify(self, message, title='Music Management'):
        return None


def listing(*ids):
    return [FlatTrack(video_id, f'https://www.youtube.com/watch?v={video_id}', video_id)
            for video_id in ids]


class DeepSweepYoutubeTestCase(unittest.TestCase):

    def setUp(self):
        mock.patch('os.makedirs').start()
        self.addCleanup(mock.patch.stopall)
        self.timing = load_timing('youtube', overrides={'deep_sweep_max_downloads': 2})
        self.write_off_store = InMemoryWriteOffStore()
        self.check_store = InMemoryCheckStore()
        self.downloader = YoutubeDownloader(
            timing=self.timing,
            rate_state=RateState('youtube', self.timing, store=InMemoryRateStateStore()),
            schedule=AccountSchedule('youtube', store=self.check_store),
            write_offs=WriteOffs('youtube', store=self.write_off_store, retry_days=30),
            notifier=StubNotifier(),
        )
        self.downloader.downloader_config['archive_dir'] = '/nonexistent'
        self.fetched = []
        self.downloader.download_url = self._record

    def _record(self, url, ydl_opts=None, account=None):
        self.fetched.append(url)

    def _sweep(self, account, tracks, held, held_after=None):
        after = held if held_after is None else held_after
        with mock.patch('services.downloader.youtube.youtube.list_flat',
                        return_value=tracks), \
             mock.patch('services.downloader.youtube.youtube.YoutubeArchive.held_ids',
                        side_effect=[held, after]):
            return self.downloader.deep_sweep_account(account, {})


class DeepSweepYoutubeTest(DeepSweepYoutubeTestCase):

    def test_it_lists_the_videos_tab_of_the_channel(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)

        with mock.patch('services.downloader.youtube.youtube.list_flat',
                        return_value=[]) as lister, \
             mock.patch('services.downloader.youtube.youtube.YoutubeArchive.held_ids',
                        return_value=set()):
            self.downloader.deep_sweep_account(account, {})

        self.assertEqual('https://www.youtube.com/@dj_a/videos', lister.call_args[0][0])

    def test_it_fetches_the_videos_the_archive_does_not_hold(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)

        report = self._sweep(account, listing('a', 'b'), held={'a'},
                             held_after={'a', 'b'})

        self.assertEqual(['https://www.youtube.com/watch?v=b'], self.fetched)
        self.assertTrue(report.complete)

    def test_it_reaches_a_gap_behind_a_video_it_already_holds(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)

        self._sweep(account, listing('new', 'held', 'gap'), held={'held'},
                    held_after={'held', 'new', 'gap'})

        self.assertEqual(['https://www.youtube.com/watch?v=new',
                          'https://www.youtube.com/watch?v=gap'], self.fetched)

    def test_it_stops_at_the_cap_and_reports_the_pass_unfinished(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)

        report = self._sweep(account, listing('a', 'b', 'c'), held=set(),
                             held_after={'a', 'b'})

        self.assertEqual(2, len(self.fetched))
        self.assertTrue(report.capped)
        self.assertFalse(report.complete)

    def test_the_two_forms_of_one_channel_are_asked_about_separately(self):
        account = YoutubeAccount(name='@dj_a', download_type=VIDEO)

        with mock.patch('services.downloader.youtube.youtube.list_flat',
                        return_value=listing('a')), \
             mock.patch('services.downloader.youtube.youtube.YoutubeArchive.held_ids',
                        return_value={'a'}) as held:
            self.downloader.deep_sweep_account(account, {})

        self.assertEqual(VIDEO, held.call_args[0][2])

    def test_the_video_form_keeps_its_own_ledger(self):
        account = YoutubeAccount(name='@dj_a', download_type=VIDEO)

        self._sweep(account, listing('a'), held=set(), held_after=set())

        self.assertIn(('youtube', '@dj_a#video', 'a'), self.write_off_store.rows)

    def test_a_video_that_did_not_arrive_counts_as_a_failure(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)

        self._sweep(account, listing('a'), held=set(), held_after=set())

        row = self.write_off_store.rows[('youtube', '@dj_a', 'a')]
        self.assertEqual(1, row.attempts)

    def test_a_written_off_video_is_not_fetched_again(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)
        self.write_off_store.remember('youtube', '@dj_a', 'a', '403',
                                      self.downloader.write_offs._now(), None, 0)

        report = self._sweep(account, listing('a'), held=set())

        self.assertEqual([], self.fetched)
        self.assertTrue(report.complete)

    def test_a_video_below_the_channel_floor_stays_out_of_the_next_pass(self):
        # The video channels sit at 1200 seconds to keep trailers out; a trailer
        # written off under that floor must not come back on the audio bounds.
        account = YoutubeAccount(name='@dj_a', download_type=VIDEO, min_duration=1200)
        self.write_off_store.remember('youtube', '@dj_a#video', 'a', 'too_short',
                                      self.downloader.write_offs._now(), 300, 0)

        report = self._sweep(account, listing('a'), held=set())

        self.assertEqual([], self.fetched)
        self.assertTrue(report.complete)


class InterruptedPassTest(DeepSweepYoutubeTestCase):
    """A pass cut short may only settle the videos it actually reached."""

    def test_a_video_that_was_never_attempted_is_not_blamed_for_the_stop(self):
        # Settling the whole batch would charge a failed attempt to videos the
        # pass never got to. Three stops in a row and they are written off as
        # `failed` for a month -- the deep sweep skipping exactly the videos it
        # exists to fetch.
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)

        def _stop_the_sweep(url, ydl_opts=None, acc=None):
            self.fetched.append(url)
            self.downloader.policy.stop.set()

        self.downloader.download_url = _stop_the_sweep

        with mock.patch('services.downloader.youtube.youtube.list_flat',
                        return_value=listing('a', 'b')), \
             mock.patch('services.downloader.youtube.youtube.YoutubeArchive.held_ids',
                        side_effect=[set(), set()]):
            with self.assertRaises(SweepAborted):
                self.downloader.deep_sweep_account(account, {})

        self.assertEqual(1, self.write_off_store.rows[('youtube', '@dj_a', 'a')].attempts)
        self.assertNotIn(('youtube', '@dj_a', 'b'), self.write_off_store.rows)


class DeepSweepYoutubeBranchTest(DeepSweepYoutubeTestCase):
    """Which of the two paths one channel takes."""

    def test_a_channel_never_deep_swept_takes_the_deep_path(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)

        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep, \
             mock.patch.object(self.downloader, 'download_account') as ordinary:
            deep.return_value = mock.Mock(complete=True)
            self.downloader._check_account(account, {})

        deep.assert_called_once()
        ordinary.assert_not_called()

    def test_a_finished_pass_is_recorded_under_the_schedule_key(self):
        account = YoutubeAccount(name='@dj_a', download_type=VIDEO)

        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep:
            deep.return_value = mock.Mock(complete=True)
            self.downloader._check_account(account, {})

        self.assertIn('@dj_a#video', self.check_store.load('youtube'))

    def test_an_unfinished_pass_leaves_the_channel_deep_due(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)

        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep:
            deep.return_value = mock.Mock(complete=False)
            self.downloader._check_account(account, {})

        self.assertTrue(self.downloader.policy.deep_due('@dj_a'))

    def test_a_recently_deep_swept_channel_goes_back_to_the_ordinary_run(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)
        self.downloader.policy.schedule.mark_deep_swept('@dj_a')

        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep, \
             mock.patch.object(self.downloader, 'download_account') as ordinary:
            self.downloader._check_account(account, {})

        deep.assert_not_called()
        ordinary.assert_called_once()

    def test_deep_mode_forces_the_deep_path_whatever_the_cadence_says(self):
        account = YoutubeAccount(name='@dj_a', download_type=AUDIO)
        self.downloader.policy.schedule.mark_deep_swept('@dj_a')
        self.downloader.deep_mode = True

        with mock.patch.object(self.downloader, 'deep_sweep_account') as deep:
            deep.return_value = mock.Mock(complete=True)
            self.downloader._check_account(account, {})

        deep.assert_called_once()


if __name__ == '__main__':
    unittest.main()
