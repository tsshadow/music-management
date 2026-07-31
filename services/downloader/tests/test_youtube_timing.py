import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.timing import load_timing
from services.downloader.youtube.youtube import YoutubeDownloader

NOW = datetime(2026, 7, 30, 12, 0, 0)


class YoutubeTimingTestBase(unittest.TestCase):

    overrides: dict = {}

    def setUp(self):
        reset_database_helpers()
        self.now = NOW
        self.accounts = ['@chan_a', '@chan_b', '@chan_c']

        patch('os.makedirs').start()
        self.sleep_patcher = patch('services.downloader.youtube.youtube.time.sleep')
        self.mock_sleep = self.sleep_patcher.start()

        self.ydl_patcher = patch('services.downloader.youtube.youtube.YoutubeDL')
        self.mock_ydl = self.ydl_patcher.start()
        self.downloaded = []
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = self._download

        self.timing = load_timing('youtube', overrides=self.overrides)
        self.rate_store = InMemoryRateStateStore()
        self.check_store = InMemoryCheckStore()

    def tearDown(self):
        patch.stopall()

    def _download(self, urls):
        self.downloaded.extend(urls)
        return 0

    def _rate_state(self):
        return RateState('youtube', self.timing, store=self.rate_store,
                         now=lambda: self.now, jitter=lambda: 1.0)

    def _downloader(self):
        downloader = YoutubeDownloader(
            break_on_existing=False,
            timing=self.timing,
            rate_state=self._rate_state(),
            schedule=AccountSchedule('youtube', store=self.check_store, now=lambda: self.now),
        )
        downloader.get_accounts_from_db = lambda: list(self.accounts)
        return downloader


class AccountCooldownTest(YoutubeTimingTestBase):

    overrides = {'account_cooldown': 3600, 'burst_size': 10, 'min_pause': 0, 'max_pause': 0}

    def test_a_first_run_visits_every_channel(self):
        self._downloader().run()
        self.assertEqual(len(self.downloaded), 3)

    def test_a_second_run_right_after_visits_nobody(self):
        self._downloader().run()
        self.downloaded.clear()
        self._downloader().run()
        self.assertEqual(self.downloaded, [])

    def test_channels_come_back_once_the_cooldown_expires(self):
        self._downloader().run()
        self.downloaded.clear()
        self.now = NOW + timedelta(seconds=3601)
        self._downloader().run()
        self.assertEqual(len(self.downloaded), 3)


class RateLimitTest(YoutubeTimingTestBase):

    overrides = {'account_cooldown': 0, 'burst_size': 10, 'min_pause': 0, 'max_pause': 0,
                 'backoff_429_base': 3600, 'max_multiplier': 16}

    def _fail_with(self, message):
        def _raise(urls):
            self.downloaded.extend(urls)
            raise RuntimeError(message)
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = _raise

    def test_youtube_now_recognises_a_429(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.assertEqual(self._rate_state().multiplier, 2)

    def test_a_429_stops_the_sweep(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.assertEqual(len(self.downloaded), 1)

    def test_a_429_parks_youtube_for_the_next_sweep(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.downloaded.clear()
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = self._download
        self._downloader().run()
        self.assertEqual(self.downloaded, [])

    def test_a_403_parks_youtube_for_the_configured_base_wait(self):
        self._fail_with('HTTP Error 403: Forbidden')
        self._downloader().run()
        self.assertEqual(self._rate_state().cooldown_remaining(), self.timing.backoff_403_base)

    def test_a_rate_limit_never_blocks_the_process_for_hours(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        long_sleeps = [call.args[0] for call in self.mock_sleep.call_args_list
                       if call.args and call.args[0] > 300]
        self.assertEqual(long_sleeps, [])


class BatchThrottleTest(YoutubeTimingTestBase):

    overrides = {'account_cooldown': 0, 'burst_size': 1, 'min_pause': 45, 'max_pause': 45,
                 'max_workers': 1}

    def test_youtube_pauses_between_batches(self):
        self._downloader().run()
        pauses = [call.args[0] for call in self.mock_sleep.call_args_list if call.args and call.args[0] == 45]
        self.assertEqual(len(pauses), 2)


class YdlOptionsTest(YoutubeTimingTestBase):

    overrides = {'account_cooldown': 0, 'sleep_interval': 20, 'ratelimit_kbps': 1024,
                 'min_pause': 0, 'max_pause': 0}

    def test_yt_dlp_gets_the_configured_pauses(self):
        self._downloader().run()
        opts = self.mock_ydl.call_args[0][0]
        self.assertEqual(opts['sleep_interval'], 20)
        self.assertEqual(opts['ratelimit'], 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
