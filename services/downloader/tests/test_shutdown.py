"""The stop signal a deploy sends, and what the downloaders do with it."""

import signal
import unittest
from unittest import mock

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader import downloader_service, shutdown
from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.deep_sweep import FlatTrack
from services.downloader.rate_state import InMemoryRateStateStore, RateState, SweepAborted
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.sweep import SweepPolicy
from services.downloader.timing import load_timing
from services.downloader.write_offs import InMemoryWriteOffStore, WriteOffs
from services.downloader.youtube.youtube import YoutubeDownloader


class ShutdownFlagTest(unittest.TestCase):
    def setUp(self):
        shutdown.reset()
        self.addCleanup(shutdown.reset)

    def test_nothing_is_requested_to_begin_with(self):
        self.assertFalse(shutdown.is_requested())

    def test_requesting_a_shutdown_raises_the_flag(self):
        shutdown.request()

        self.assertTrue(shutdown.is_requested())

    def test_a_second_request_is_harmless(self):
        shutdown.request()
        shutdown.request()

        self.assertTrue(shutdown.is_requested())

    def test_it_accepts_the_arguments_a_signal_handler_is_called_with(self):
        # signal.signal hands the handler (signum, frame); request is installed
        # directly as that handler, so it has to tolerate both.
        shutdown.request(signal.SIGTERM, None)

        self.assertTrue(shutdown.is_requested())

    def test_installing_the_handlers_arms_sigterm_and_sigint(self):
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        self.addCleanup(lambda: [signal.signal(sig, handler) for sig, handler in previous.items()])

        shutdown.install_handlers()

        self.assertIs(signal.getsignal(signal.SIGTERM), shutdown.request)
        self.assertIs(signal.getsignal(signal.SIGINT), shutdown.request)


class AbortHookTest(unittest.TestCase):
    """The hook yt-dlp calls while a download runs.

    Without it the worker sits inside a single multi-minute download and never
    reaches the between-tracks checkpoint, so Docker's ten second grace period
    expires and SIGKILL takes the process with its bookkeeping unwritten.
    """

    def setUp(self):
        shutdown.reset()
        self.addCleanup(shutdown.reset)

    def test_the_hook_does_nothing_while_no_shutdown_is_requested(self):
        self.assertIsNone(shutdown.abort_hook({'status': 'downloading'}))

    def test_the_hook_aborts_the_download_once_a_shutdown_is_requested(self):
        shutdown.request()

        with self.assertRaises(shutdown.ShuttingDown):
            shutdown.abort_hook({'status': 'downloading'})


class GuardTest(unittest.TestCase):
    """The checkpoint between two tracks already exists; a stop rides on it."""

    def setUp(self):
        shutdown.reset()
        self.addCleanup(shutdown.reset)
        timing = load_timing('soundcloud', overrides={})
        self.policy = SweepPolicy(
            'soundcloud',
            timing=timing,
            rate_state=RateState('soundcloud', timing, store=InMemoryRateStateStore()),
            schedule=AccountSchedule('soundcloud', store=InMemoryCheckStore()),
        )

    def test_the_guard_lets_an_account_through_normally(self):
        self.policy.guard('dj_a')

    def test_the_guard_stops_the_sweep_once_a_shutdown_is_requested(self):
        shutdown.request()

        with self.assertRaises(SweepAborted):
            self.policy.guard('dj_a')

    def test_the_reason_names_the_shutdown_rather_than_a_rate_limit(self):
        shutdown.request()

        with self.assertRaises(SweepAborted) as raised:
            self.policy.guard('dj_a')

        self.assertIn('shutting down', str(raised.exception))


class StubNotifier:
    def notify(self, message, title='Music Management'):
        return None


def _policy_parts(source):
    timing = load_timing(source, overrides={})
    return {
        'timing': timing,
        'rate_state': RateState(source, timing, store=InMemoryRateStateStore()),
        'schedule': AccountSchedule(source, store=InMemoryCheckStore()),
        'notifier': StubNotifier(),
    }


class AbortHookIsWiredInTest(unittest.TestCase):
    """Both downloaders have to hand the hook to yt-dlp, or the flag is unreachable."""

    def setUp(self):
        shutdown.reset()
        self.addCleanup(shutdown.reset)
        mock.patch('os.makedirs').start()
        self.addCleanup(mock.patch.stopall)

    def test_soundcloud_hands_the_abort_hook_to_yt_dlp(self):
        downloader = SoundcloudDownloader(**_policy_parts('soundcloud'))

        opts = downloader._prepare_ydl_opts('dj_a', None, False)

        self.assertIn(shutdown.abort_hook, opts['progress_hooks'])

    def test_youtube_hands_the_abort_hook_to_yt_dlp(self):
        downloader = YoutubeDownloader(**_policy_parts('youtube'))

        opts = downloader._build_ydl_opts('/tmp/archive.txt')

        self.assertIn(shutdown.abort_hook, opts['progress_hooks'])


class RetryStopsOnShutdownTest(unittest.TestCase):
    """The retry loop would otherwise burn the whole grace period on backoff sleeps."""

    def setUp(self):
        shutdown.reset()
        self.addCleanup(shutdown.reset)
        mock.patch('os.makedirs').start()
        self.addCleanup(mock.patch.stopall)
        self.downloader = SoundcloudDownloader(**_policy_parts('soundcloud'))
        self.attempts = 0

    def _failing_ydl(self, *_args, **_kwargs):
        self.attempts += 1
        raise shutdown.ShuttingDown('shutting down')

    def test_a_download_aborted_by_a_shutdown_is_not_retried(self):
        shutdown.request()

        with (
            mock.patch('services.downloader.soundcloud.soundcloud.YoutubeDL', side_effect=self._failing_ydl),
            mock.patch('services.downloader.soundcloud.soundcloud.time.sleep') as slept,
        ):
            with self.assertRaises(SweepAborted):
                self.downloader.download_url('https://soundcloud.com/dj_a/t1', {}, account='dj_a')

        self.assertEqual(1, self.attempts)
        slept.assert_not_called()

    def test_an_ordinary_failure_is_still_retried(self):
        def _boom(*_args, **_kwargs):
            self.attempts += 1
            raise RuntimeError('network down')

        with (
            mock.patch('services.downloader.soundcloud.soundcloud.YoutubeDL', side_effect=_boom),
            mock.patch('services.downloader.soundcloud.soundcloud.time.sleep'),
        ):
            self.downloader.download_url('https://soundcloud.com/dj_a/t1', {}, account='dj_a')

        self.assertEqual(self.downloader.timing.retry_attempts, self.attempts)


class BookkeepingSurvivesShutdownTest(unittest.TestCase):
    """The point of the whole exercise, end to end.

    A pass stopped halfway has to leave the same trace it would have left had it
    stopped for any other reason: what arrived counted, what did not written
    down, and the account still deep-due.
    """

    def setUp(self):
        shutdown.reset()
        self.addCleanup(shutdown.reset)
        mock.patch('os.makedirs').start()
        self.addCleanup(mock.patch.stopall)
        self.write_off_store = InMemoryWriteOffStore()
        parts = _policy_parts('soundcloud')
        self.downloader = SoundcloudDownloader(
            unavailable=WriteOffs('soundcloud', store=self.write_off_store, retry_days=30), **parts
        )
        self.downloader.downloader_config['archive_file'] = None
        self.downloader.downloader_config['archive_dir'] = '/nonexistent'
        self.fetched = []

    def _fetch_then_stop(self, url, yt_dl_opts=None, account=None):
        """Take the first track, then behave as a deploy would mid-download."""
        self.fetched.append(url)
        shutdown.request()

    def test_a_pass_cut_short_still_records_what_it_learned(self):
        self.downloader.download_url = self._fetch_then_stop
        listing = [FlatTrack(t, f'https://soundcloud.com/dj_a/{t}', t) for t in ('a', 'b', 'c')]

        with (
            mock.patch('services.downloader.soundcloud.soundcloud.list_flat', return_value=listing),
            mock.patch(
                'services.downloader.soundcloud.soundcloud.SoundcloudArchive.held_ids', side_effect=[set(), set()]
            ),
        ):
            with self.assertRaises(SweepAborted):
                self.downloader.deep_sweep_account('dj_a', {})

        # Only the first track was ever attempted: the guard stopped the rest.
        self.assertEqual(['https://soundcloud.com/dj_a/a'], self.fetched)
        # And it was written down rather than silently forgotten.
        self.assertEqual(1, self.write_off_store.rows[('soundcloud', 'dj_a', 'a')].attempts)

    def test_a_track_that_was_never_attempted_is_not_blamed_for_the_stop(self):
        # Counting the whole batch would charge a failed attempt to tracks the
        # pass never got to. Three stops in a row and they are written off as
        # `failed` for a month -- the deep sweep skipping exactly the tracks it
        # exists to fetch.
        self.downloader.download_url = self._fetch_then_stop
        listing = [FlatTrack(t, f'https://soundcloud.com/dj_a/{t}', t) for t in ('a', 'b', 'c')]

        with (
            mock.patch('services.downloader.soundcloud.soundcloud.list_flat', return_value=listing),
            mock.patch(
                'services.downloader.soundcloud.soundcloud.SoundcloudArchive.held_ids', side_effect=[set(), set()]
            ),
        ):
            with self.assertRaises(SweepAborted):
                self.downloader.deep_sweep_account('dj_a', {})

        self.assertNotIn(('soundcloud', 'dj_a', 'b'), self.write_off_store.rows)
        self.assertNotIn(('soundcloud', 'dj_a', 'c'), self.write_off_store.rows)

    def test_the_account_stays_deep_due_after_a_shutdown(self):
        # A stop arriving on the last track of the batch lets the loop end on its
        # own, so there is no guard left to raise. The pass still has to settle
        # and still has to count as unfinished.
        self.downloader.download_url = self._fetch_then_stop
        listing = [FlatTrack('a', 'https://soundcloud.com/dj_a/a', 'a')]

        with (
            mock.patch('services.downloader.soundcloud.soundcloud.list_flat', return_value=listing),
            mock.patch(
                'services.downloader.soundcloud.soundcloud.SoundcloudArchive.held_ids', side_effect=[set(), set()]
            ),
        ):
            self.downloader._check_account('dj_a', {})

        self.assertTrue(self.downloader.policy.deep_due('dj_a'))


class MainLoopStopsTest(unittest.TestCase):
    """`--repeat` must not go back to sleep once a stop has been asked for."""

    def setUp(self):
        shutdown.reset()
        self.addCleanup(shutdown.reset)

    def _run_main(self, argv, on_download):
        service = mock.MagicMock()
        service.download.side_effect = on_download
        with (
            mock.patch.object(downloader_service, 'DownloaderService', return_value=service),
            mock.patch.object(downloader_service, 'parse_args', return_value=downloader_service.parse_args(argv)),
            mock.patch.object(downloader_service, 'setup_logging'),
            mock.patch.object(downloader_service.time, 'sleep') as slept,
        ):
            downloader_service.main()
        return service, slept

    def test_a_repeating_run_stops_instead_of_sleeping(self):
        def _stop_after_one(*_args, **_kwargs):
            shutdown.request()

        _service, slept = self._run_main(['--step', 'soundcloud', '--repeat'], _stop_after_one)

        slept.assert_not_called()

    def test_the_handlers_are_armed_before_any_downloading_starts(self):
        armed = []

        def _note(*_args, **_kwargs):
            armed.append(signal.getsignal(signal.SIGTERM))
            shutdown.request()

        previous = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)

        self._run_main(['--step', 'soundcloud', '--repeat'], _note)

        self.assertEqual([shutdown.request], armed)


if __name__ == '__main__':
    unittest.main()
