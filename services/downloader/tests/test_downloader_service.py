import unittest

from services.tests.mock_base import setup_mocks
setup_mocks()

from services.downloader.downloader_service import parse_args, sweep_sleep_seconds
from services.downloader.timing import load_timing


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


class CommandLineTest(unittest.TestCase):

    def test_sleeptime_is_unset_by_default_so_the_settings_decide(self):
        args = parse_args([])
        self.assertIsNone(args.sleeptime)

    def test_sleeptime_can_still_be_forced_by_hand(self):
        args = parse_args(['--sleeptime', '30'])
        self.assertEqual(args.sleeptime, 30)


if __name__ == '__main__':
    unittest.main()
