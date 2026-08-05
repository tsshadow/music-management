import contextlib
import sys
import types
import unittest
from unittest.mock import MagicMock, call, patch

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader import downloader_service
from services.downloader.downloader_service import DownloaderService, main, parse_args, sweep_sleep_seconds
from services.downloader.timing import load_timing


@contextlib.contextmanager
def stub_telegram_downloader():
    """Stand in for the Telegram downloader that download() imports lazily.

    Patching the real class is not an option here: importing
    services.downloader.telegram pulls in telethon, which is a downloader-image
    dependency and not present in every environment that runs this suite. Putting
    the stub in sys.modules satisfies the lazy import without it.
    """
    downloader = MagicMock()
    module = types.ModuleType('services.downloader.telegram.telegram')
    module.TelegramDownloader = downloader
    package = types.ModuleType('services.downloader.telegram')
    package.telegram = module
    with patch.dict(sys.modules, {
        'services.downloader.telegram': package,
        'services.downloader.telegram.telegram': module,
    }):
        yield downloader


def _timing_for(intervals):
    def _load(source):
        return load_timing(source, overrides={'sweep_interval': intervals[source]})
    return _load


class SweepSleepTest(unittest.TestCase):

    def test_the_interval_comes_from_the_settings(self):
        seconds = sweep_sleep_seconds(['soundcloud'], None, load=_timing_for({'soundcloud': 1800}))
        self.assertEqual(seconds, 1800)

    def test_an_explicit_command_line_value_wins(self):
        seconds = sweep_sleep_seconds(['soundcloud'], 60, load=_timing_for({'soundcloud': 1800}))
        self.assertEqual(seconds, 60)

    def test_several_steps_wake_up_on_the_shortest_interval(self):
        seconds = sweep_sleep_seconds(['soundcloud', 'youtube'], None,
                                      load=_timing_for({'soundcloud': 1800, 'youtube': 900}))
        self.assertEqual(seconds, 900)

    def test_a_settings_failure_falls_back_to_a_safe_interval(self):
        def _broken(_source):
            raise RuntimeError('database is down')
        self.assertEqual(sweep_sleep_seconds(['soundcloud'], None, load=_broken), 900)

    def test_no_steps_falls_back_to_a_safe_interval(self):
        self.assertEqual(sweep_sleep_seconds([], None, load=_timing_for({})), 900)


class CurrentTimingTest(unittest.TestCase):

    def test_the_timing_of_a_source_comes_from_its_sweep_policy(self):
        policy = MagicMock()
        with patch.object(downloader_service, 'SweepPolicy', return_value=policy) as sweep_policy:
            self.assertIs(downloader_service._current_timing('soundcloud'), policy.timing)

        sweep_policy.assert_called_once_with('soundcloud')


class CommandLineTest(unittest.TestCase):

    def test_sleeptime_is_unset_by_default_so_the_settings_decide(self):
        args = parse_args([])
        self.assertIsNone(args.sleeptime)

    def test_sleeptime_can_still_be_forced_by_hand(self):
        args = parse_args(['--sleeptime', '30'])
        self.assertEqual(args.sleeptime, 30)

    def test_no_steps_means_the_caller_decides_to_run_them_all(self):
        self.assertEqual(parse_args([]).step, '')

    def test_steps_are_taken_verbatim_from_the_command_line(self):
        self.assertEqual(parse_args(['--step', 'youtube,telegram']).step, 'youtube,telegram')

    def test_breaking_on_an_existing_item_is_the_default(self):
        self.assertTrue(parse_args([]).break_on_existing)

    def test_breaking_on_an_existing_item_can_be_turned_off(self):
        self.assertFalse(parse_args(['--no-break-on-existing']).break_on_existing)

    def test_a_single_run_is_the_default(self):
        self.assertFalse(parse_args([]).repeat)
        self.assertTrue(parse_args(['--repeat']).repeat)

    def test_an_account_limits_the_run(self):
        self.assertIsNone(parse_args([]).account)
        self.assertEqual(parse_args(['--account', 'Angerfist']).account, 'Angerfist')


class DownloadDispatchTest(unittest.TestCase):
    """download() picks a downloader per source and hands it the run settings."""

    def setUp(self):
        with patch.object(downloader_service, 'Settings'):
            self.service = DownloaderService()
        self.service.dry_run = True

    def test_an_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.service.download('spotify', None, True)

        self.assertIn('spotify', str(raised.exception))

    def test_youtube_runs_the_youtube_downloader(self):
        with patch('services.downloader.youtube.youtube.YoutubeDownloader') as downloader:
            self.service.download('youtube', 'Angerfist', break_on_existing=False)

        downloader.assert_called_once_with(break_on_existing=False, dry_run=True)
        downloader.return_value.run.assert_called_once_with(account='Angerfist')

    def test_soundcloud_runs_the_soundcloud_downloader(self):
        with patch('services.downloader.soundcloud.soundcloud.SoundcloudDownloader') as downloader:
            self.service.download('soundcloud', None, break_on_existing=True)

        downloader.assert_called_once_with(break_on_existing=True, dry_run=True)
        downloader.return_value.run.assert_called_once_with(account=None)

    def test_telegram_runs_one_download_per_named_account(self):
        self.service.settings.telegram_accounts = ' hardcore , uptempo ,, '

        with stub_telegram_downloader() as downloader:
            self.service.download('telegram', None, break_on_existing=True)

        self.assertEqual(downloader.return_value.run.call_args_list, [call('hardcore'), call('uptempo')])

    def test_an_explicit_telegram_account_wins_over_the_configured_list(self):
        self.service.settings.telegram_accounts = 'hardcore,uptempo'

        with stub_telegram_downloader() as downloader:
            self.service.download('telegram', 'gabber', break_on_existing=True)

        downloader.return_value.run.assert_called_once_with('gabber')

    def test_telegram_without_any_account_downloads_nothing(self):
        self.service.settings.telegram_accounts = ''

        with stub_telegram_downloader() as downloader, patch.dict('os.environ', {'telegram_accounts': ''}):
            self.service.download('telegram', None, break_on_existing=True)

        downloader.return_value.run.assert_not_called()


class MainLoopTest(unittest.TestCase):

    def run_main(self, argv, sleep=None):
        """Run main() with every downloader stubbed out.

        A repeating run never returns on its own, so those tests end the loop by
        having the last sleep raise; that exception is the expected way out.
        """
        service = MagicMock()
        with patch.object(downloader_service, 'DownloaderService', return_value=service), \
             patch.object(downloader_service, 'parse_args', return_value=parse_args(argv)), \
             patch.object(downloader_service.time, 'sleep', side_effect=sleep) as sleeper, \
             contextlib.suppress(KeyboardInterrupt):
            main()
        return service, sleeper

    def sources_run(self, service):
        return [download.args[0] for download in service.download.call_args_list]

    def test_every_source_runs_when_no_step_is_named(self):
        service, sleeper = self.run_main([])

        self.assertEqual(self.sources_run(service), ['youtube', 'soundcloud', 'telegram'])
        sleeper.assert_not_called()

    def test_only_the_named_steps_run(self):
        service, _sleeper = self.run_main(['--step', 'telegram'])

        self.assertEqual(self.sources_run(service), ['telegram'])

    def test_the_command_line_flags_are_passed_through(self):
        service, _sleeper = self.run_main(['--step', 'youtube', '--account', 'Angerfist', '--no-break-on-existing'])

        self.assertEqual(
            service.download.call_args.kwargs, {'break_on_existing': False, 'account': 'Angerfist'}
        )

    def test_repeat_sleeps_between_rounds(self):
        service, sleeper = self.run_main(
            ['--step', 'youtube', '--repeat', '--sleeptime', '5'],
            sleep=[None, KeyboardInterrupt()],
        )

        self.assertEqual(sleeper.call_args_list[0].args, (5,))
        self.assertEqual(self.sources_run(service), ['youtube', 'youtube'])


if __name__ == '__main__':
    unittest.main()
