import unittest
from unittest.mock import patch
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.Song.LabelSong import LabelSong
from services.tagger.constants import ARTIST, GENRE

class TestImporterUnicode(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        self.path_exists_patcher = patch('os.path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

    def tearDown(self):
        patch.stopall()

    def test_replace_invalid_unicode(self):
        """Test that zero-width characters are replaced by semicolons."""
        file_path = '/tmp/Label/CAT/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(ARTIST, 'Artist\ufeffName')
        song.parse()
        self.assertEqual(song.artist(), 'Artist;Name')
if __name__ == '__main__':
    unittest.main()