import unittest
from unittest.mock import patch, MagicMock
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.common.Helpers.GenreRulesHelper import GenreRow, WHITE, BLACK
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

    def test_blacklisted_genre_is_filtered_out(self):
        """Test that genres marked black are removed from the tag."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(GENRE, 'Arts;Hardstyle')
        self.db_helpers['genre_rules'].set_rows([GenreRow(1, 'Hardstyle', 'hardstyle', WHITE, None), GenreRow(2, 'Arts', 'arts', BLACK, None)])
        song.parse()
        self.assertEqual(song.genre(), 'Hardstyle')

    def test_blacklisted_genre_with_canonical_is_corrected(self):
        """Test that a correction rewrites the genre instead of dropping it."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(GENRE, 'uptempo')
        self.db_helpers['genre_rules'].set_rows([GenreRow(1, 'Uptempo Hardcore', 'uptempo hardcore', WHITE, None), GenreRow(2, 'uptempo', 'uptempo', BLACK, 1)], expansions={2: [1]})
        song.parse()
        self.assertEqual(song.genre(), 'Uptempo Hardcore')

    def test_slash_separated_genres_become_two_genres(self):
        """'Hardstyle/Hardcore' is a separator, not a genre name."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(GENRE, 'Hardstyle/Hardcore')
        self.db_helpers['genre_rules'].set_rows([GenreRow(1, 'Hardstyle', 'hardstyle', WHITE, None), GenreRow(2, 'Hardcore', 'hardcore', WHITE, None)])
        song.parse()
        self.assertEqual(song.genre(), 'Hardcore;Hardstyle')

    def test_contraction_expands_into_both_genres(self):
        """'Upterror' carries two genres at once."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(GENRE, 'Upterror')
        self.db_helpers['genre_rules'].set_rows([GenreRow(1, 'Uptempo Hardcore', 'uptempo hardcore', WHITE, None), GenreRow(2, 'Terror', 'terror', WHITE, None), GenreRow(3, 'Upterror', 'upterror', BLACK, None)], expansions={3: [1, 2]})
        song.parse()
        self.assertEqual(song.genre(), 'Terror;Uptempo Hardcore')

    def test_unknown_genre_is_queued_for_curation_and_left_in_the_tag(self):
        """Unknown genres are recorded but never silently approved."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(GENRE, 'Unknown Genre')
        self.db_helpers['genre_rules'].set_rows([])
        song.parse()
        self.db_helpers['genre_rules'].record_unknown.assert_called_with('Unknown Genre')
        self.assertEqual(song.genre(), 'Unknown Genre')
if __name__ == '__main__':
    unittest.main()