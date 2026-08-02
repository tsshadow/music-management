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

NOW = datetime(2026, 7, 30, 12, 0, 0)


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
        )

    def _fail_with_403(self, mock_ytdlp):
        def _download(urls):
            opts = mock_ytdlp.call_args[0][0]
            opts['logger'].error('HTTP Error 403: Forbidden')
            return 1
        mock_ytdlp.return_value.__enter__.return_value.download.side_effect = _download

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_403_in_the_log_is_reported_as_a_rate_limit(self, mock_ytdlp):
        self._fail_with_403(mock_ytdlp)
        with self.assertRaises(RateLimited):
            self._downloader().download_url('http://soundcloud.com/test_account/tracks')

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_the_first_403_parks_soundcloud_for_the_base_wait(self, mock_ytdlp):
        self._fail_with_403(mock_ytdlp)
        with self.assertRaises(RateLimited):
            self._downloader().download_url('http://soundcloud.com/test_account/tracks')
        self.assertEqual(self._rate_state().cooldown_remaining(), 240)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_consecutive_403s_climb_the_ladder_across_restarts(self, mock_ytdlp):
        self._fail_with_403(mock_ytdlp)
        for expected in (240, 960, 3840):
            with self.assertRaises(RateLimited) as caught:
                self._downloader().download_url('http://soundcloud.com/test_account/tracks')
            self.assertEqual(caught.exception.wait, expected)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_403_does_not_block_the_thread(self, mock_ytdlp):
        self._fail_with_403(mock_ytdlp)
        with patch('services.downloader.soundcloud.soundcloud.time.sleep') as mock_sleep:
            with self.assertRaises(RateLimited):
                self._downloader().download_url('http://soundcloud.com/test_account/tracks')
        self.assertEqual(mock_sleep.call_count, 0)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_a_clean_sweep_clears_the_403_count(self, mock_ytdlp):
        self._fail_with_403(mock_ytdlp)
        with self.assertRaises(RateLimited):
            self._downloader().download_url('http://soundcloud.com/test_account/tracks')

        mock_ytdlp.return_value.__enter__.return_value.download.side_effect = lambda urls: 0
        state = self._rate_state()
        state.record_success()
        self.assertEqual(state.snapshot().consecutive_403, 0)


if __name__ == '__main__':
    unittest.main()
