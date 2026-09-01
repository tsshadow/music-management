import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# mock_base replaces DatabaseConnector process-wide so that no test can reach MariaDB.
# Load the real source under a throwaway name and inject a fake connector, the same way
# ProcessedFilesHelperTest does.
_SOURCE = Path(__file__).resolve().parent / 'RescanInvalidator.py'


def load_module():
    spec = importlib.util.spec_from_file_location('_real_rescan_invalidator', _SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RescanInvalidatorTestCase(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.connection.cursor.return_value.__exit__.return_value = False
        connector = MagicMock()
        connector.connect.return_value = self.connection
        patcher = patch.object(self.module, 'DatabaseConnector', return_value=connector)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.processed = MagicMock()
        self.processed.mark_paths_for_rescan.side_effect = lambda paths, reason: len(paths)
        self.invalidator = self.module.RescanInvalidator(processed_files_helper=self.processed)


class InvalidateByTermTest(RescanInvalidatorTestCase):
    def test_a_matching_term_marks_the_files_it_found(self):
        self.cursor.fetchall.return_value = [('/music/a.mp3',), ('/music/b.mp3',)]
        count = self.invalidator.invalidate_by_term('Ran-D', 'artist_genre_rule')
        self.assertEqual(count, 2)
        self.processed.mark_paths_for_rescan.assert_called_once_with(
            ['/music/a.mp3', '/music/b.mp3'], 'artist_genre_rule'
        )

    def test_a_long_term_searches_title_and_path_as_well(self):
        self.cursor.fetchall.return_value = []
        self.invalidator.invalidate_by_term('Ran-D', 'artist_genre_rule')
        query, args = self.cursor.execute.call_args.args
        self.assertIn('t.title LIKE', query)
        self.assertIn('mf.file_path LIKE', query)
        self.assertEqual(args, ('Ran-D', '%Ran-D%', '%Ran-D%'))

    def test_a_short_term_only_matches_the_artist_name(self):
        # An artist called 'D' would otherwise drag in most of the library.
        self.cursor.fetchall.return_value = []
        self.invalidator.invalidate_by_term('D', 'artist_genre_rule')
        query, args = self.cursor.execute.call_args.args
        self.assertNotIn('LIKE', query)
        self.assertEqual(args, ('D',))

    def test_like_wildcards_in_the_term_are_escaped(self):
        self.cursor.fetchall.return_value = []
        self.invalidator.invalidate_by_term('50%_off', 'artist_genre_rule')
        _, args = self.cursor.execute.call_args.args
        self.assertEqual(args[1], r'%50\%\_off%')

    def test_an_empty_term_does_nothing(self):
        count = self.invalidator.invalidate_by_term('   ', 'artist_genre_rule')
        self.assertEqual(count, 0)
        self.cursor.execute.assert_not_called()
        self.processed.mark_paths_for_rescan.assert_not_called()

    def test_a_term_that_matches_nothing_marks_nothing(self):
        self.cursor.fetchall.return_value = []
        self.assertEqual(self.invalidator.invalidate_by_term('Ran-D', 'artist_genre_rule'), 0)
        self.processed.mark_paths_for_rescan.assert_not_called()

    def test_a_database_error_returns_zero_instead_of_raising(self):
        self.cursor.execute.side_effect = RuntimeError('database gone')
        self.assertEqual(self.invalidator.invalidate_by_term('Ran-D', 'artist_genre_rule'), 0)


class InvalidateByGenreTest(RescanInvalidatorTestCase):
    def test_tracks_linked_to_the_genre_are_marked_alongside_the_name_match(self):
        self.cursor.fetchall.side_effect = [[('/music/a.mp3',)], [('/music/b.mp3',)]]
        count = self.invalidator.invalidate_by_genre_id(7, 'Uptempo', 'genre_decision')
        self.assertEqual(count, 2)

    def test_the_link_table_is_queried_on_the_genre_id(self):
        self.cursor.fetchall.side_effect = [[], []]
        self.invalidator.invalidate_by_genre_id(7, 'Uptempo', 'genre_decision')
        query, args = self.cursor.execute.call_args_list[0].args
        self.assertIn('library_track_genres', query)
        self.assertEqual(args, (7,))


class InvalidateAllTest(RescanInvalidatorTestCase):
    def test_everything_is_marked_through_the_processed_files_helper(self):
        self.invalidator.invalidate_all('fallback')
        self.processed.mark_for_rescan.assert_called_once_with(None, reason='fallback')

    def test_no_count_is_promised_for_a_fallback(self):
        self.assertEqual(self.invalidator.invalidate_all(), -1)


if __name__ == '__main__':
    unittest.main()
