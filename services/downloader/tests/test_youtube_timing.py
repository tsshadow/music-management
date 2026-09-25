import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from services.tests.mock_base import reset_database_helpers

pytestmark = pytest.mark.mock_base('yt_dlp', 'config_store', 'Cache')


from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.timing import load_timing
from services.downloader.youtube.youtube import YoutubeDownloader

NOW = datetime(2026, 7, 30, 12, 0, 0)


class StubNotifier:
    """Stub notifier for test isolation — prevents sweep.py lazy import."""

    def notify(self, message, title='Music Management'):
        return True


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

        # This suite is about the ordinary path: the cooldowns, the batching and
        # the backoff. Without this every channel would be deep-due -- none has
        # ever been deep-swept -- and take the full-listing path instead.
        self.timing = load_timing('youtube', overrides={'deep_sweep_days': 0, **self.overrides})
        self.rate_store = InMemoryRateStateStore()
        self.check_store = InMemoryCheckStore()

    def tearDown(self):
        patch.stopall()

    def _download(self, urls):
        self.downloaded.extend(urls)
        return 0

    def _rate_state(self):
        return RateState('youtube', self.timing, store=self.rate_store, now=lambda: self.now, jitter=lambda: 1.0)

    def _downloader(self):
        downloader = YoutubeDownloader(
            break_on_existing=False,
            timing=self.timing,
            rate_state=self._rate_state(),
            schedule=AccountSchedule('youtube', store=self.check_store, now=lambda: self.now),
            notifier=StubNotifier(),
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
    overrides = {
        'account_cooldown': 0,
        'burst_size': 10,
        'min_pause': 0,
        'max_pause': 0,
        'backoff_429_base': 3600,
        'max_multiplier': 16,
    }

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
        long_sleeps = [call.args[0] for call in self.mock_sleep.call_args_list if call.args and call.args[0] > 300]
        self.assertEqual(long_sleeps, [])


class ReportedErrorTest(RateLimitTest):
    """What yt-dlp actually does with `ignoreerrors`: log the error and return normally.

    The tests above raise out of `download()`, which real yt-dlp never does for a
    per-entry 403 under that option. The error reaches the logger and nothing
    else, so the logger is where the park has to come from.
    """

    def _report(self, message):
        def _log_and_return(urls):
            self.downloaded.extend(urls)
            logger = self.mock_ydl.call_args.args[0]['logger']
            logger.error(f'ERROR: [youtube] abc123: {message}')
            return 1

        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = _log_and_return

    def test_every_attempt_hands_yt_dlp_a_logger(self):
        self._downloader().run()
        for call in self.mock_ydl.call_args_list:
            self.assertIn('logger', call.args[0])

    def test_a_logged_403_parks_youtube(self):
        self._report('Unable to download webpage: HTTP Error 403: Forbidden')
        self._downloader().run()
        self.assertEqual(self._rate_state().cooldown_remaining(), self.timing.backoff_403_base)
        self.assertEqual(len(self.downloaded), 1)

    def test_a_logged_429_parks_youtube_and_doubles_the_multiplier(self):
        self._report('HTTP Error 429: Too Many Requests')
        self._downloader().run()
        self.assertEqual(self._rate_state().multiplier, 2)
        self.assertEqual(len(self.downloaded), 1)

    def test_the_error_reaches_the_log_and_so_the_event_stream(self):
        self._report('HTTP Error 403: Forbidden')
        with self.assertLogs(level='ERROR') as logs:
            self._downloader().run()
        self.assertTrue(any('HTTP Error 403: Forbidden' in line for line in logs.output))

    def test_an_unrelated_logged_error_does_not_park(self):
        self._report('Private video. Sign in if you have been granted access to this video')
        self._downloader().run()
        self.assertEqual(self._rate_state().cooldown_remaining(), 0)
        self.assertEqual(len(self.downloaded), 3)

    def test_a_403_yt_dlp_recovered_from_does_not_park(self):
        # yt-dlp tries several player clients and retries failed requests, logging
        # each refusal on the way as a warning. The video still came back.
        def _warn_and_return(urls):
            self.downloaded.extend(urls)
            self.mock_ydl.call_args.args[0]['logger'].warning(
                'WARNING: [youtube] abc123: Unable to download API page: HTTP Error 403: Forbidden'
            )
            return 0

        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = _warn_and_return
        self._downloader().run()
        self.assertEqual(self._rate_state().cooldown_remaining(), 0)
        self.assertEqual(len(self.downloaded), 3)

    def test_a_403_logged_before_break_on_existing_still_parks(self):
        # `break_on_existing` ends a channel by raising out of download(); what the
        # logger heard before that point must not be dropped with it.
        def _log_then_break(urls):
            self.downloaded.extend(urls)
            self.mock_ydl.call_args.args[0]['logger'].error('ERROR: HTTP Error 403: Forbidden')
            raise RuntimeError(
                'Encountered a video that is already in the archive, stopping due to --break-on-existing'
            )

        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = _log_then_break
        self._downloader().run()
        self.assertEqual(self._rate_state().cooldown_remaining(), self.timing.backoff_403_base)


class ShutdownDuringChannelTest(YoutubeTimingTestBase):
    overrides = {'account_cooldown': 0, 'burst_size': 10, 'min_pause': 0, 'max_pause': 0, 'max_workers': 1}

    def setUp(self):
        super().setUp()
        from services.downloader import shutdown

        self.shutdown = shutdown
        shutdown.reset()
        self.addCleanup(shutdown.reset)

    def test_a_channel_aborted_by_a_shutdown_is_not_retried(self):
        def _abort(urls):
            self.downloaded.extend(urls)
            self.shutdown.request()
            raise self.shutdown.ShuttingDown('shutting down')

        self.mock_ydl.return_value.__enter__.return_value.download.side_effect = _abort
        from services.downloader.rate_state import SweepAborted

        with self.assertRaises(SweepAborted):
            self._downloader().download_account('@chan_a')
        self.assertEqual(self.downloaded, ['http://www.youtube.com/@chan_a'])
        self.mock_sleep.assert_not_called()


class BatchThrottleTest(YoutubeTimingTestBase):
    overrides = {'account_cooldown': 0, 'burst_size': 1, 'min_pause': 45, 'max_pause': 45, 'max_workers': 1}

    def test_youtube_pauses_between_batches(self):
        self._downloader().run()
        pauses = [call.args[0] for call in self.mock_sleep.call_args_list if call.args and call.args[0] == 45]
        self.assertEqual(len(pauses), 2)


class YdlOptionsTest(YoutubeTimingTestBase):
    overrides = {'account_cooldown': 0, 'sleep_interval': 20, 'ratelimit_kbps': 1024, 'min_pause': 0, 'max_pause': 0}

    def test_yt_dlp_gets_the_configured_pauses(self):
        self._downloader().run()
        opts = self.mock_ydl.call_args[0][0]
        self.assertEqual(opts['sleep_interval'], 20)
        self.assertEqual(opts['ratelimit'], 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
