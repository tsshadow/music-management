import unittest
from unittest.mock import patch, MagicMock
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.Song.LabelSong import LabelSong
from services.tagger.constants import ARTIST, GENRE

class TestGenreRules(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers
        self.db_helpers = databaseHelpers
        self.path_exists_patcher = patch('os.path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

    def tearDown(self):
        patch.stopall()

    def test_infer_genre_from_artist(self):
        """Test that genre is inferred from artist via LabelSong rules."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(ARTIST, 'Headhunterz')
        self.db_helpers['artistGenreHelper'].get.return_value = ['Hardstyle']
        song.parse()
        self.assertEqual(song.genre(), 'Hardstyle')

    def test_infer_genre_from_subgenre(self):
        """Test that genre is inferred from subgenre via LabelSong rules."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(GENRE, 'Rawstyle')
        self.db_helpers['subgenreHelper'].get.return_value = ['Hardstyle']
        song.parse()
        self.assertIn('Hardstyle', song.genre())
        self.assertIn('Rawstyle', song.genre())

    def test_clean_and_filter_genre(self):
        """Test that invalid genres are filtered out."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(GENRE, 'Invalid Genre;Hardstyle')
        self.db_helpers['rules_genres'].exists.side_effect = lambda x: x == 'Hardstyle'
        self.db_helpers['rules_genres'].get_corrected_or_exists.side_effect = lambda x: x if x == 'Hardstyle' else None
        song.parse()
        self.assertEqual(song.genre(), 'Hardstyle')

    def test_add_missing_genre_to_backlog(self):
        """Test that unknown genres are added to the backlog."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(GENRE, 'Unknown Genre')
        self.db_helpers['rules_genres'].exists.return_value = False
        self.db_helpers['rules_ignored_genres'].exists.return_value = False
        self.db_helpers['rules_genre_backlog'].exists.return_value = False
        song.parse()
        self.db_helpers['rules_genre_backlog'].add.assert_called_with('Unknown Genre')
if __name__ == '__main__':
    unittest.main()