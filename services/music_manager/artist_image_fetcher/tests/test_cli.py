import unittest
from unittest.mock import MagicMock, patch

from services.music_manager.artist_image_fetcher import cli


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.fetcher = MagicMock()
        self.conn = MagicMock()
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.conn.cursor.return_value.__exit__.return_value = False
        # The CLI takes connections through DatabaseConnector.connection(), which
        # closes them again -- `--repeat` runs these commands in a loop, so a
        # dropped connection there is one leaked MariaDB session per pass.
        connector = MagicMock(connect=MagicMock(return_value=self.conn))
        connector.connection.return_value.__enter__.return_value = self.conn
        connector.connection.return_value.__exit__.return_value = False
        patches = [
            patch.object(cli, 'ArtistImageFetcher', return_value=self.fetcher),
            patch.object(cli, 'DatabaseConnector', return_value=connector),
            patch.object(cli, 'setup_logging'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_cli(self, *argv):
        with patch('sys.argv', ['artist-image-fetcher', *argv]), patch('builtins.print') as printed:
            cli.main()
        return [' '.join(str(a) for a in call.args) for call in printed.call_args_list]


class FetchCommandTest(CliTestCase):
    def test_an_artist_id_is_fetched_directly(self):
        self.run_cli('fetch', '--artist-id', '7', '--name', 'Angerfist')
        self.fetcher.fetch_for_artist.assert_called_once_with(
            7, 'Angerfist', force_refresh=False, override_cleared=False
        )

    def test_the_force_flag_is_passed_through(self):
        self.run_cli('fetch', '--artist-id', '7', '--force')
        self.fetcher.fetch_for_artist.assert_called_once_with(7, None, force_refresh=True, override_cleared=True)

    def test_a_name_is_resolved_to_an_id_first(self):
        self.cursor.fetchone.return_value = {'id': 12}
        self.run_cli('fetch', '--name', 'Angerfist')
        self.fetcher.fetch_for_artist.assert_called_once_with(
            12, 'Angerfist', force_refresh=False, override_cleared=False
        )

    def test_a_name_that_is_not_in_the_library_is_reported(self):
        self.cursor.fetchone.return_value = None
        output = self.run_cli('fetch', '--name', 'Nobody')
        self.assertTrue(any('not found' in line for line in output))
        self.fetcher.fetch_for_artist.assert_not_called()

    def test_fetch_without_an_id_or_a_name_explains_what_is_missing(self):
        output = self.run_cli('fetch')
        self.assertTrue(any('--artist-id' in line for line in output))
        self.fetcher.fetch_for_artist.assert_not_called()


class FetchMissingCommandTest(CliTestCase):
    def test_every_artist_without_an_image_is_fetched(self):
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'One'}, {'id': 2, 'name': 'Two'}]
        output = self.run_cli('fetch-missing', '--limit', '5')
        self.assertEqual(self.fetcher.fetch_for_artist.call_count, 2)
        self.assertEqual(self.cursor.execute.call_args_list[0].args[1], (5,))
        self.assertTrue(any('Found 2 artists' in line for line in output))

    def test_previously_failed_artists_are_excluded_by_default(self):
        self.cursor.fetchall.return_value = []
        self.run_cli('fetch-missing')
        self.assertIn("NOT IN ('failed', 'cleared')", self.cursor.execute.call_args_list[0].args[0])

    def test_include_failed_switches_the_filter_around(self):
        self.cursor.fetchall.return_value = []
        self.run_cli('fetch-missing', '--include-failed')
        self.assertIn("image_status = 'failed'", self.cursor.execute.call_args_list[0].args[0])

    def test_an_empty_result_prints_the_status_breakdown(self):
        self.cursor.fetchall.side_effect = [[], [('failed', 3)]]
        output = self.run_cli('fetch-missing')
        self.assertTrue(any('Found 0 artists' in line for line in output))
        self.assertTrue(any('Stats for NULL primary_image_id' in line for line in output))
        self.fetcher.fetch_for_artist.assert_not_called()

    def test_an_empty_result_without_any_stats_prints_only_the_count(self):
        self.cursor.fetchall.side_effect = [[], []]
        output = self.run_cli('fetch-missing')
        self.assertFalse(any('Stats for' in line for line in output))


class RefreshCommandTest(CliTestCase):
    def test_stale_artists_are_refetched_with_force(self):
        self.cursor.fetchall.return_value = [{'id': 3, 'name': 'Three'}]
        output = self.run_cli('refresh', '--older-than-days', '30', '--limit', '9')
        self.fetcher.fetch_for_artist.assert_called_once_with(3, 'Three', force_refresh=True)
        self.assertEqual(self.cursor.execute.call_args.args[1], (30, 9))
        self.assertTrue(any('Refreshing 1' in line for line in output))


class LoopingTest(CliTestCase):
    def test_without_a_command_the_help_is_printed_and_the_loop_stops(self):
        with (
            patch('sys.argv', ['artist-image-fetcher']),
            patch.object(cli.argparse.ArgumentParser, 'print_help') as help_text,
        ):
            cli.main()
        help_text.assert_called_once()

    def test_the_daemon_flag_keeps_the_loop_running_between_sleeps(self):
        self.cursor.fetchall.return_value = []
        with patch('time.sleep', side_effect=[None, KeyboardInterrupt]) as sleep:
            with (
                patch('sys.argv', ['artist-image-fetcher', '--daemon', '--sleeptime', '1', 'fetch-missing']),
                patch('builtins.print'),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    cli.main()
        self.assertEqual(sleep.call_args.args, (1,))


class SetupLoggingTest(CliTestCase):
    def test_main_sets_up_logging_with_the_music_manager_source(self):
        self.run_cli('fetch', '--artist-id', '7', '--name', 'Angerfist')
        cli.setup_logging.assert_called_once_with('music-manager')


if __name__ == '__main__':
    unittest.main()
