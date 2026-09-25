"""YouTube's sign-in wall is one incident, not one ERROR per video (bug report 076).

Covers the pieces on their own: recognising the line, the breaker's count, the
report that counts instead of logging, the fixed-length park in the rate state
and the sweep policy, and the downloader acting on all of it.
"""

import logging
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()

from services.downloader.account_report import AccountReport
from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.bot_check import (
    BOT_CHECK,
    COOKIES_MISSING,
    BotCheckBreaker,
    BotCheckTripped,
    is_bot_check,
    is_bot_check_side_effect,
)
from services.downloader.rate_state import InMemoryRateStateStore, RateLimited, RateState
from services.downloader.sweep import SweepPolicy
from services.downloader.timing import load_timing
from services.downloader.youtube import youtube as youtube_module
from services.downloader.youtube.YoutubeAccount import AUDIO, YoutubeAccount

NOW = datetime(2026, 9, 25, 7, 0, 0)

# Exactly what production logged, curly apostrophe included.
WALL = (
    'ERROR: [youtube] dOzV0vIrxjk: Sign in to confirm you’re not a bot. Use --cookies-from-browser or '
    '--cookies for the authentication.'
)
NO_TITLE = (
    '[youtube] No title found in player responses; falling back to title from initial data. '
    'Other metadata may also be missing'
)


class StubNotifier:
    """Stands in for ntfy; the bot-check park must not push on its own."""

    def __init__(self):
        self.sent = []

    def notify(self, message, title='Music Management'):
        """Remember one notification."""
        self.sent.append((title, message))
        return True


class RecognitionTest(unittest.TestCase):
    def test_the_production_line_is_the_wall(self):
        self.assertTrue(is_bot_check(WALL))

    def test_a_straight_apostrophe_is_the_same_wall(self):
        self.assertTrue(is_bot_check("Sign in to confirm you're not a bot"))

    def test_an_ordinary_error_is_not_the_wall(self):
        self.assertFalse(is_bot_check('ERROR: [youtube] abc: Private video'))
        self.assertFalse(is_bot_check(None))

    def test_the_no_title_warning_is_a_side_effect(self):
        self.assertTrue(is_bot_check_side_effect(NO_TITLE))
        self.assertFalse(is_bot_check_side_effect(WALL))


class BreakerTest(unittest.TestCase):
    def test_trips_at_the_threshold(self):
        breaker = BotCheckBreaker(3)
        self.assertFalse(breaker.record_refusal(WALL))
        self.assertFalse(breaker.record_refusal(WALL))
        self.assertTrue(breaker.record_refusal(WALL))
        self.assertTrue(breaker.tripped)

    def test_a_video_that_came_back_restarts_the_count(self):
        breaker = BotCheckBreaker(3)
        breaker.record_refusal(WALL)
        breaker.record_refusal(WALL)
        breaker.record_success()
        self.assertFalse(breaker.record_refusal(WALL))
        self.assertEqual(breaker.count, 1)

    def test_a_tripped_breaker_stays_tripped_for_the_sweep(self):
        breaker = BotCheckBreaker(1)
        breaker.record_refusal(WALL)
        breaker.record_success()
        self.assertTrue(breaker.tripped)

    def test_reset_starts_a_new_sweep(self):
        breaker = BotCheckBreaker(1)
        breaker.record_refusal(WALL)
        breaker.reset()
        self.assertFalse(breaker.tripped)
        self.assertEqual(breaker.count, 0)

    def test_a_threshold_below_one_is_one(self):
        self.assertTrue(BotCheckBreaker(0).record_refusal(WALL))

    def test_threads_share_one_count(self):
        breaker = BotCheckBreaker(40)
        threads = [threading.Thread(target=lambda: [breaker.record_refusal(WALL) for _ in range(10)]) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(breaker.count, 40)
        self.assertTrue(breaker.tripped)


class ReportTest(unittest.TestCase):
    def test_with_a_breaker_the_wall_is_counted_not_logged_as_an_error(self):
        report = AccountReport(breaker=BotCheckBreaker(5))
        with self.assertLogs(level='DEBUG') as logs:
            report.error(WALL)
            report.warning(NO_TITLE)
        self.assertEqual(report.bot_checks, 1)
        self.assertTrue(all(record.levelno == logging.DEBUG for record in logs.records))

    def test_the_tripping_refusal_ends_the_download_call(self):
        report = AccountReport(breaker=BotCheckBreaker(2))
        report.error(WALL)
        with self.assertRaises(BotCheckTripped):
            report.error(WALL)

    def test_without_a_breaker_the_wall_is_an_error_as_before(self):
        report = AccountReport()
        with self.assertLogs(level='ERROR') as logs:
            report.error(WALL)
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(report.bot_checks, 0)

    def test_other_errors_still_reach_the_log(self):
        report = AccountReport(breaker=BotCheckBreaker(2))
        with self.assertLogs(level='ERROR') as logs:
            report.error('ERROR: [youtube] abc: Private video')
        self.assertEqual(len(logs.records), 1)


class RateStateBlockTest(unittest.TestCase):
    def setUp(self):
        self.now = NOW
        self.timing = load_timing('youtube', overrides={})
        self.store = InMemoryRateStateStore()
        self.state = RateState('youtube', self.timing, store=self.store, now=lambda: self.now)

    def test_a_block_parks_for_the_given_time_and_names_its_reason(self):
        wait = self.state.record_block(BOT_CHECK, 21600)
        self.assertEqual(wait, 21600)
        self.assertEqual(self.state.cooldown_remaining(), 21600)
        self.assertEqual(self.store.load('youtube').block_reason, BOT_CHECK)

    def test_a_block_leaves_the_403_ladder_alone(self):
        self.state.record_block(BOT_CHECK, 21600)
        self.assertEqual(self.state.snapshot().consecutive_403, 0)

    def test_a_clean_run_clears_the_reason(self):
        self.state.record_block(BOT_CHECK, 60)
        self.now += timedelta(seconds=61)
        self.state.record_success()
        self.assertIsNone(self.state.snapshot().block_reason)

    def test_a_later_403_replaces_the_reason(self):
        self.state.record_block(BOT_CHECK, 60)
        self.state.record_403()
        self.assertIsNone(self.state.snapshot().block_reason)

    def test_reset_clears_the_reason(self):
        self.state.record_block(BOT_CHECK, 60)
        self.state.reset()
        self.assertIsNone(self.store.load('youtube').block_reason)


class PolicyBlockTest(unittest.TestCase):
    def setUp(self):
        self.now = NOW
        self.notifier = StubNotifier()
        timing = load_timing('youtube', overrides={})
        self.rate_state = RateState('youtube', timing, store=InMemoryRateStateStore(), now=lambda: self.now)
        self.policy = SweepPolicy(
            'youtube',
            timing=timing,
            rate_state=self.rate_state,
            schedule=AccountSchedule('youtube', store=InMemoryCheckStore()),
            notifier=self.notifier,
        )
        self.assertTrue(self.policy.begin())

    def test_the_first_caller_parks_and_warns_once(self):
        with self.assertLogs(level='DEBUG') as logs:
            first = self.policy.park_block(BOT_CHECK, 'a', 3600, 'log in')
            second = self.policy.park_block(BOT_CHECK, 'b', 3600, 'log in')
        self.assertIs(first, second)
        self.assertEqual(first.reason, BOT_CHECK)
        warnings = [record for record in logs.records if record.levelno >= logging.WARNING]
        self.assertEqual(len(warnings), 1)
        self.assertIn('log in', warnings[0].getMessage())
        self.assertTrue(self.policy.stop.is_set())

    def test_the_park_does_not_push_by_itself(self):
        # The WARNING already reaches the alerts topic through the event log.
        self.policy.park_block(BOT_CHECK, 'a', 3600, 'log in')
        self.assertEqual(self.notifier.sent, [])

    def test_the_next_sweeps_skip_quietly_while_parked(self):
        self.policy.park_block(BOT_CHECK, 'a', 3600, 'log in')
        with self.assertLogs(level='INFO') as logs:
            self.assertFalse(self.policy.begin())
        self.assertTrue(all(record.levelno == logging.INFO for record in logs.records))

    def test_a_plain_cooldown_still_warns_on_every_skipped_sweep(self):
        self.rate_state.record_403()
        with self.assertLogs(level='WARNING'):
            self.assertFalse(self.policy.begin())


class CookieProfileProblemTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_profile_with_a_cookie_database_is_fine(self):
        open(os.path.join(self.tmp.name, 'cookies.sqlite'), 'wb').close()
        self.assertIsNone(youtube_module.cookie_profile_problem(self.tmp.name))

    def test_a_missing_mount_is_named(self):
        problem = youtube_module.cookie_profile_problem('/firefox-config/profile-that-is-not-there')
        self.assertIn('does not exist', problem)

    def test_an_empty_profile_is_named(self):
        self.assertIn('no cookies.sqlite', youtube_module.cookie_profile_problem(self.tmp.name))

    def test_no_profile_means_nothing_to_check(self):
        self.assertIsNone(youtube_module.cookie_profile_problem(None))


class DownloaderBlockTest(unittest.TestCase):
    """The downloader wired to the breaker; yt-dlp itself is the suite's stub here."""

    def setUp(self):
        reset_database_helpers()
        self.now = NOW
        self.tmp = tempfile.TemporaryDirectory()
        self.profile = os.path.join(self.tmp.name, 'profile')
        os.makedirs(self.profile)
        open(os.path.join(self.profile, 'cookies.sqlite'), 'wb').close()
        patch('services.downloader.youtube.youtube.time.sleep').start()
        self.ydl = patch('services.downloader.youtube.youtube.YoutubeDL').start()
        self.config = patch.object(youtube_module, 'ConfigStore').start()
        self.settings = {
            'youtube_folder': os.path.join(self.tmp.name, 'youtube'),
            'youtube_archive': os.path.join(self.tmp.name, 'archive'),
            'yt_cookies': f'firefox:{self.profile}',
        }
        self.config.return_value.get_many.side_effect = lambda keys: {k: self.settings.get(k) for k in keys}
        self.timing = load_timing('youtube', overrides={'deep_sweep_days': 0, 'bot_check_threshold': 2})
        self.rate_store = InMemoryRateStateStore()

    def tearDown(self):
        patch.stopall()
        self.tmp.cleanup()

    def _downloader(self):
        downloader = youtube_module.YoutubeDownloader(
            timing=self.timing,
            rate_state=RateState('youtube', self.timing, store=self.rate_store, now=lambda: self.now),
            schedule=AccountSchedule('youtube', store=InMemoryCheckStore(), now=lambda: self.now),
            notifier=StubNotifier(),
        )
        downloader.get_accounts_from_db = lambda: [YoutubeAccount(name='@a'), YoutubeAccount(name='@b')]
        return downloader

    def _wall_on_every_video(self):
        """Make every download() answer with the sign-in wall through the report."""

        def download(_urls):
            logger = self.ydl.call_args.args[0]['logger']
            for _ in range(3):
                logger.error(WALL)

        self.ydl.return_value.__enter__.return_value.download.side_effect = download

    def test_the_wall_parks_youtube_for_the_configured_pause(self):
        self._wall_on_every_video()
        downloader = self._downloader()
        account = YoutubeAccount(name='@a', download_type=AUDIO)
        with self.assertRaises(RateLimited) as caught:
            downloader.download_account(account, downloader._prepare_ydl_opts(account, None, False))
        self.assertEqual(caught.exception.reason, BOT_CHECK)
        self.assertEqual(self.rate_store.load('youtube').block_reason, BOT_CHECK)
        self.assertEqual(caught.exception.wait, self.timing.bot_check_pause)

    def test_a_run_into_the_wall_logs_one_warning_and_no_errors(self):
        self._wall_on_every_video()
        with self.assertLogs(level='DEBUG') as logs:
            self._downloader().run()
        levels = [record.levelno for record in logs.records]
        self.assertEqual(levels.count(logging.WARNING), 1, [r.getMessage() for r in logs.records])
        self.assertNotIn(logging.ERROR, levels)
        # The second channel was never asked: the sweep stopped at the first.
        self.assertEqual(self.ydl.return_value.__enter__.return_value.download.call_count, 1)

    def test_a_video_that_comes_back_keeps_the_breaker_open(self):
        downloader = self._downloader()
        downloader.bot_breaker.record_refusal(WALL)
        downloader._filter_for(YoutubeAccount(name='@a'))({'id': 'x', 'duration': 10})
        self.assertEqual(downloader.bot_breaker.count, 0)

    def test_a_missing_cookie_database_is_one_error_and_no_downloads(self):
        os.remove(os.path.join(self.profile, 'cookies.sqlite'))
        with self.assertLogs(level='INFO') as logs:
            self._downloader().run()
        errors = [record for record in logs.records if record.levelno == logging.ERROR]
        self.assertEqual(len(errors), 1)
        self.assertIn('no cookies.sqlite', errors[0].getMessage())
        self.ydl.return_value.__enter__.return_value.download.assert_not_called()
        self.assertEqual(self.rate_store.load('youtube').block_reason, COOKIES_MISSING)

    def test_a_cookie_load_error_from_yt_dlp_parks_instead_of_retrying(self):
        class CookieLoadError(Exception):
            """Named like yt-dlp's own; the downloader matches it by name."""

        self.ydl.return_value.__enter__.return_value.download.side_effect = CookieLoadError('cannot open')
        downloader = self._downloader()
        account = YoutubeAccount(name='@a', download_type=AUDIO)
        with self.assertRaises(RateLimited) as caught:
            downloader.download_account(account, downloader._prepare_ydl_opts(account, None, False))
        self.assertEqual(caught.exception.reason, COOKIES_MISSING)
        self.assertEqual(self.ydl.return_value.__enter__.return_value.download.call_count, 1)

    def test_the_run_reads_a_snapshot_and_removes_it_afterwards(self):
        seen = []

        def download(_urls):
            seen.append(self.ydl.call_args.args[0]['cookiesfrombrowser'])

        self.ydl.return_value.__enter__.return_value.download.side_effect = download
        downloader = self._downloader()
        downloader.run()
        self.assertTrue(seen)
        browser, snapshot = seen[0]
        self.assertEqual(browser, 'firefox')
        self.assertNotEqual(snapshot, self.profile)
        self.assertFalse(os.path.exists(snapshot))
        self.assertEqual(downloader._base_ydl_opts['cookiesfrombrowser'], ('firefox', self.profile))


if __name__ == '__main__':
    unittest.main()
