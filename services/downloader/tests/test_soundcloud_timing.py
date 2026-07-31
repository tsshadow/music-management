import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.timing import load_timing

NOW = datetime(2026, 7, 30, 12, 0, 0)


class SoundcloudTimingTestBase(unittest.TestCase):

    overrides: dict = {}

    def setUp(self):
        reset_database_helpers()
        self.now = NOW
        self.accounts = ['dj_a', 'dj_b', 'dj_c']

        self.accounts_patcher = patch('services.downloader.soundcloud.soundcloud.get_accounts_from_db')
        self.mock_accounts = self.accounts_patcher.start()
        self.mock_accounts.side_effect = lambda: list(self.accounts)

        patch('os.makedirs').start()
        self.sleep_patcher = patch('services.downloader.soundcloud.soundcloud.time.sleep')
        self.mock_sleep = self.sleep_patcher.start()

        self.ydl_patcher = patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
        self.mock_ydl = self.ydl_patcher.start()
        self.downloaded = []
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = self._download

        self.timing = load_timing('soundcloud', overrides=self.overrides)
        self.rate_store = InMemoryRateStateStore()
        self.check_store = InMemoryCheckStore()

    def tearDown(self):
        patch.stopall()

    def _download(self, urls):
        self.downloaded.extend(urls)
        return 0

    def _rate_state(self):
        return RateState('soundcloud', self.timing, store=self.rate_store,
                         now=lambda: self.now, jitter=lambda: 1.0)

    def _downloader(self):
        rate_state = self._rate_state()
        return SoundcloudDownloader(
            break_on_existing=False,
            timing=self.timing.with_multiplier(rate_state.multiplier),
            rate_state=rate_state,
            schedule=AccountSchedule('soundcloud', store=self.check_store, now=lambda: self.now),
        )


class AccountCooldownTest(SoundcloudTimingTestBase):

    overrides = {'account_cooldown': 3600, 'burst_size': 10, 'min_pause': 0, 'max_pause': 0}

    def test_a_first_run_visits_every_account(self):
        self._downloader().run()
        self.assertEqual(len(self.downloaded), 3)

    def test_a_second_run_right_after_visits_nobody(self):
        self._downloader().run()
        self.downloaded.clear()
        self._downloader().run()
        self.assertEqual(self.downloaded, [])

    def test_accounts_come_back_once_the_cooldown_expires(self):
        self._downloader().run()
        self.downloaded.clear()
        self.now = NOW + timedelta(seconds=3601)
        self._downloader().run()
        self.assertEqual(len(self.downloaded), 3)

    def test_a_new_account_is_picked_up_while_the_others_cool_down(self):
        self._downloader().run()
        self.downloaded.clear()
        self.accounts.append('dj_new')
        self._downloader().run()
        self.assertEqual(self.downloaded, ['http://soundcloud.com/dj_new/tracks'])

    def test_asking_for_one_account_by_name_ignores_the_cooldown(self):
        self._downloader().run()
        self.downloaded.clear()
        self._downloader().run(account='dj_a')
        self.assertEqual(self.downloaded, ['http://soundcloud.com/dj_a/tracks'])


class RateLimitTest(SoundcloudTimingTestBase):

    overrides = {'account_cooldown': 0, 'burst_size': 10, 'min_pause': 0, 'max_pause': 0,
                 'backoff_429_base': 3600, 'max_multiplier': 16, 'recovery_runs': 2}

    def _fail_with(self, message):
        def _raise(urls):
            self.downloaded.extend(urls)
            raise RuntimeError(message)
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = _raise

    def test_a_429_stops_the_sweep_instead_of_walking_on(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.assertEqual(len(self.downloaded), 1)

    def test_a_429_raises_the_multiplier(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.assertEqual(self._rate_state().multiplier, 2)

    def test_a_429_parks_the_source_and_the_next_sweep_does_nothing(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.downloaded.clear()
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = self._download
        self._downloader().run()
        self.assertEqual(self.downloaded, [])

    def test_the_source_wakes_up_once_the_cooldown_has_passed(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.downloaded.clear()
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = self._download
        self.now = NOW + timedelta(seconds=7201)
        self._downloader().run()
        self.assertEqual(len(self.downloaded), 3)

    def test_a_429_never_blocks_the_process_for_hours(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        long_sleeps = [call.args[0] for call in self.mock_sleep.call_args_list
                       if call.args and call.args[0] > 300]
        self.assertEqual(long_sleeps, [])

    def test_a_403_stops_the_sweep_too(self):
        self._fail_with('HTTP Error 403: Forbidden')
        self._downloader().run()
        self.assertEqual(len(self.downloaded), 1)

    def test_a_403_parks_the_source_for_the_configured_base_wait(self):
        self._fail_with('HTTP Error 403: Forbidden')
        self._downloader().run()
        self.assertEqual(self._rate_state().cooldown_remaining(), self.timing.backoff_403_base)

    def test_a_clean_sweep_walks_the_multiplier_back_down(self):
        self._fail_with('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = self._download
        self.now = NOW + timedelta(seconds=7201)
        for _ in range(2):
            self._downloader().run()
        self.assertEqual(self._rate_state().multiplier, 1)


class BatchThrottleTest(SoundcloudTimingTestBase):

    overrides = {'account_cooldown': 0, 'burst_size': 1, 'min_pause': 45, 'max_pause': 45,
                 'max_workers': 1}

    def test_soundcloud_pauses_between_batches(self):
        self._downloader().run()
        pauses = [call.args[0] for call in self.mock_sleep.call_args_list if call.args and call.args[0] == 45]
        self.assertEqual(len(pauses), 2)

    def test_the_last_batch_is_not_followed_by_a_pause(self):
        self.accounts = ['dj_only']
        self._downloader().run()
        pauses = [call.args[0] for call in self.mock_sleep.call_args_list if call.args and call.args[0] == 45]
        self.assertEqual(pauses, [])


class MultiplierReachesTheDownloadTest(SoundcloudTimingTestBase):

    overrides = {'account_cooldown': 0, 'sleep_interval': 15, 'max_sleep_interval': 90,
                 'ratelimit_kbps': 512, 'sleep_requests': 2, 'min_pause': 0, 'max_pause': 0}

    def test_yt_dlp_gets_the_configured_pauses(self):
        self._downloader().run()
        opts = self.mock_ydl.call_args[0][0]
        self.assertEqual(opts['sleep_interval'], 15)
        self.assertEqual(opts['ratelimit'], 512 * 1024)

    def test_yt_dlp_slows_down_further_while_the_multiplier_is_up(self):
        self._rate_state().record_429()
        self.now = NOW + timedelta(seconds=7201)
        self._downloader().run()
        opts = self.mock_ydl.call_args[0][0]
        self.assertEqual(opts['sleep_interval'], 30)


class AccountsAreOnlyMarkedWhenVisitedTest(SoundcloudTimingTestBase):

    overrides = {'account_cooldown': 3600, 'burst_size': 10, 'min_pause': 0, 'max_pause': 0}

    def test_an_account_skipped_by_a_rate_limit_is_retried_next_sweep(self):
        def _raise(urls):
            self.downloaded.extend(urls)
            raise RuntimeError('HTTP Error 429: Too Many Requests')
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = _raise
        self._downloader().run()
        visited_first = list(self.downloaded)

        self.downloaded.clear()
        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = self._download
        self.now = NOW + timedelta(seconds=7201)
        self._downloader().run()

        self.assertEqual(len(visited_first), 1)
        self.assertEqual(len(self.downloaded), 3)


if __name__ == '__main__':
    unittest.main()
