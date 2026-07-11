import unittest
from unittest.mock import patch, MagicMock
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.Song.LabelSong import LabelSong
from services.tagger.constants import ARTIST, TITLE, REMIXER

class TestArtistRules(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers
        self.db_helpers = databaseHelpers
        self.path_exists_patcher = patch('os.path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

    def tearDown(self):
        patch.stopall()

    def test_infer_remixer_from_title(self):
        """Test that remixer is extracted from title via LabelSong rules."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(TITLE, 'Song Name (Headhunterz Remix)')
        song.tag_collection.set_item(ARTIST, 'Original Artist')
        self.db_helpers['library_artists'].get.side_effect = lambda x: x if x == 'Headhunterz' else x
        self.db_helpers['library_artists'].exists.side_effect = lambda x: x == 'Headhunterz'
        song.parse()
        self.assertIn('Headhunterz', song.artist())
        self.assertEqual(song.tag_collection.get_item_as_string(REMIXER), 'Headhunterz')

    def test_add_missing_artist_to_database_does_not_add_by_default(self):
        """Test that missing artists are NOT added to the database by default (ask_for_missing=False)."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(ARTIST, 'New Artist')
        self.db_helpers['library_artists'].exists.return_value = False
        song.parse()
        self.db_helpers['library_artists'].add.assert_not_called()

    def test_check_artist_rule(self):
        """Test that artists are corrected if they exist in the database with different casing."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(ARTIST, 'd-block')
        self.db_helpers['library_artists'].get.side_effect = lambda x: 'D-Block' if x.lower() == 'd-block' else x
        self.db_helpers['library_artists'].exists.side_effect = lambda x: x.lower() == 'd-block'
        song.parse()
        self.assertEqual(song.artist(), 'D-Block')
if __name__ == '__main__':
    unittest.main()