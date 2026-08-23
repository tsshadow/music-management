import contextlib
import unittest
from datetime import datetime
from unittest.mock import patch

# Mock the database before importing SoundcloudDownloader
from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateLimited, RateState
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.timing import load_timing
from services.downloader.write_offs import InMemoryWriteOffStore, WriteOffs

NOW = datetime(2026, 7, 30, 12, 0, 0)


class StubNotifier:
    """Stub notifier for test isolation — prevents sweep.py lazy import."""

    def notify(self, message, title='Music Management'):
        return True


class TestSoundcloud403Backoff(unittest.TestCase):
    """A 403 reported through the yt-dlp logger has to park SoundCloud.

    yt-dlp runs with `ignoreerrors`, so a 403 never surfaces as an exception; it
    only shows up in the log. These tests cover that path end to end.
    """

    def setUp(self):
        reset_database_helpers()
        self.now = NOW

        self.db_patcher = patch('services.downloader.soundcloud.soundcloud.get_accounts_from_db')
        self.mock_get_accounts = self.db_patcher.start()
        self.mock_get_accounts.return_value = ['test_account']

        patch('os.makedirs').start()
        patch('services.downloader.soundcloud.soundcloud.time.sleep').start()

        self.timing = load_timing('soundcloud', overrides={
            'backoff_403_base': 240, 'backoff_403_factor': 4, 'backoff_403_cap': 86400,
        })
        self.rate_store = InMemoryRateStateStore()
        self.check_store = InMemoryCheckStore()
        self.unavailable_store = InMemoryWriteOffStore()

    def tearDown(self):
        patch.stopall()

    def _rate_state(self):
        return RateState('soundcloud', self.timing, store=self.rate_store,
                         now=lambda: self.now, jitter=lambda: 1.0)

    def _downloader(self):
        return SoundcloudDownloader(
            break_on_existing=False,
            timing=self.timing,
            rate_state=self._rate_state(),
            schedule=AccountSchedule('soundcloud', store=self.check_store, now=lambda: self.now),
            unavailable=WriteOffs('soundcloud', store=self.unavailable_store,
                                  retry_days=30, now=lambda: self.now),
            notifier=StubNotifier(),
        )

    def _fail_with_403(self, mock_ytdlp):
        def _download(urls):
            opts = mock_ytdlp.call_args[0][0]
            opts['logger'].error('HTTP Error 403: Forbidden')
            return 1
        mock_ytdlp.return_value.__enter__.return_value.download.side_effect = _download

    def _fail_with_429(self, mock_ytdlp):
        def _download(urls):
            opts = mock_ytdlp.call_args[0][0]
            opts['logger'].error('HTTP Error 429: Too Many Requests')
            return 1
        mock_ytdlp.return_value.__enter__.return_value.download.side_effect = _download

    def _forbid_one_track_of_several(self, mock_ytdlp):
        """An account we can read, holding one track we are not allowed to have."""
        def _download(urls):
            opts = mock_ytdlp.call_args[0][0]
            opts['match_filter']({'id': 't1', 'title': 'fine', 'duration': 300,
                                  'channel_id': 'test_account'})
            opts['match_filter']({'id': 't2', 'title': 'go plus', 'duration': 300,
                                  'channel_id': 'test_account'})
            opts['logger'].error('HTTP Error 403: Forbidden')
            return 1
        mock_ytdlp.return_value.__enter__.return_value.download.side_effect = _download

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_429_is_reported_as_a_rate_limit(self, mock_ytdlp):
        self._fail_with_429(mock_ytdlp)
        with self.assertRaises(RateLimited):
            self._downloader().download_url('http://soundcloud.com/test_account/tracks')

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_single_unreadable_account_does_not_park_soundcloud(self, mock_ytdlp):
        """One account giving nothing back is not evidence of a block."""
        self._fail_with_403(mock_ytdlp)
        self._downloader().download_url('http://soundcloud.com/test_account/tracks')
        self.assertEqual(self._rate_state().cooldown_remaining(), 0)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_enough_unreadable_accounts_in_a_row_park_soundcloud(self, mock_ytdlp):
        self._fail_with_403(mock_ytdlp)
        downloader = self._downloader()
        downloader.download_url('http://soundcloud.com/a/tracks')
        downloader.download_url('http://soundcloud.com/b/tracks')
        with self.assertRaises(RateLimited):
            downloader.download_url('http://soundcloud.com/c/tracks')

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_parking_after_a_run_of_blanks_waits_the_base(self, mock_ytdlp):
        self._fail_with_403(mock_ytdlp)
        downloader = self._downloader()
        for name in ('a', 'b', 'c'):
            with contextlib.suppress(RateLimited):
                downloader.download_url(f'http://soundcloud.com/{name}/tracks')
        self.assertEqual(self._rate_state().cooldown_remaining(), 240)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_forbidden_track_among_readable_ones_does_not_park_soundcloud(self, mock_ytdlp):
        self._forbid_one_track_of_several(mock_ytdlp)
        self._downloader().download_url('http://soundcloud.com/test_account/tracks')
        self.assertEqual(self._rate_state().cooldown_remaining(), 0)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_forbidden_track_is_written_off_so_it_is_not_asked_for_again(self, mock_ytdlp):
        self._forbid_one_track_of_several(mock_ytdlp)
        downloader = self._downloader()
        downloader.download_url('http://soundcloud.com/test_account/tracks')
        self.assertTrue(downloader.unavailable.should_skip('test_account', 't2'))

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_readable_track_is_not_written_off(self, mock_ytdlp):
        self._forbid_one_track_of_several(mock_ytdlp)
        downloader = self._downloader()
        downloader.download_url('http://soundcloud.com/test_account/tracks')
        self.assertFalse(downloader.unavailable.should_skip('test_account', 't1'))

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_readable_account_clears_a_run_of_blanks(self, mock_ytdlp):
        downloader = self._downloader()
        self._fail_with_403(mock_ytdlp)
        downloader.download_url('http://soundcloud.com/a/tracks')
        downloader.download_url('http://soundcloud.com/b/tracks')
        self._forbid_one_track_of_several(mock_ytdlp)
        downloader.download_url('http://soundcloud.com/c/tracks')
        self._fail_with_403(mock_ytdlp)
        downloader.download_url('http://soundcloud.com/d/tracks')
        self.assertEqual(self._rate_state().cooldown_remaining(), 0)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_429_does_not_block_the_thread(self, mock_ytdlp):
        self._fail_with_429(mock_ytdlp)
        with patch('services.downloader.soundcloud.soundcloud.time.sleep') as mock_sleep:
            with self.assertRaises(RateLimited):
                self._downloader().download_url('http://soundcloud.com/test_account/tracks')
        self.assertEqual(mock_sleep.call_count, 0)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_clean_sweep_clears_the_403_count(self, mock_ytdlp):
        self._fail_with_429(mock_ytdlp)
        with self.assertRaises(RateLimited):
            self._downloader().download_url('http://soundcloud.com/test_account/tracks')

        mock_ytdlp.return_value.__enter__.return_value.download.side_effect = lambda urls: 0
        state = self._rate_state()
        state.record_success()
        self.assertEqual(state.snapshot().consecutive_403, 0)


if __name__ == '__main__':
    unittest.main()
