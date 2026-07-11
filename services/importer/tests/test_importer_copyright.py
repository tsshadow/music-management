import unittest
from unittest.mock import patch
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.Song.LabelSong import LabelSong
from services.tagger.constants import PUBLISHER, COPYRIGHT, DATE

class TestCopyright(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        self.path_exists_patcher = patch('os.path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

    def tearDown(self):
        patch.stopall()

    def test_calculate_copyright_with_date(self):
        """Test copyright calculation with publisher and date."""
        file_path = '/tmp/Scantraxx/SCAN123/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(DATE, '2023-01-01')
        song.tag_collection.set_item(PUBLISHER, 'Scantraxx')
        copyright = song.calculate_copyright()
        self.assertEqual(copyright, 'Scantraxx (2023)')

    def test_calculate_copyright_without_date(self):
        """Test copyright calculation with publisher but no date."""
        file_path = '/tmp/Scantraxx/SCAN123/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(PUBLISHER, 'Scantraxx')
        copyright = song.calculate_copyright()
        self.assertEqual(copyright, 'Scantraxx')

    def test_calculate_copyright_applied_on_parse(self):
        """Test that copyright is automatically applied during parse if missing."""
        file_path = '/tmp/Scantraxx/SCAN123/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(DATE, '2024-05-05')
        song.parse()
        self.assertEqual(song.copyright(), 'Scantraxx (2024)')

    def test_calculate_copyright_not_overwritten(self):
        """Test that existing copyright is not overwritten."""
        file_path = '/tmp/Scantraxx/SCAN123/song.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(COPYRIGHT, 'Original Copyright')
        song.parse()
        self.assertEqual(song.copyright(), 'Original Copyright')
if __name__ == '__main__':
    unittest.main()