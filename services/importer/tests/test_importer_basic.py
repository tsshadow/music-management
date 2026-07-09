import unittest
from unittest.mock import patch
from services.tests.mock_base import setup_mocks, reset_database_helpers

setup_mocks()

from services.tagger.Song.LabelSong import LabelSong
from services.tagger.constants import PUBLISHER, CATALOG_NUMBER, TITLE, ARTIST

class TestBasicImport(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        self.path_exists_patcher = patch('os.path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

    def tearDown(self):
        patch.stopall()

    def test_publisher_and_catalog_extraction(self):
        """Test extraction of publisher and catalog number from path."""
        # Structure: .../Publisher/Catalog Number Anything/Song.mp3
        file_path = '/tmp/music/Scantraxx/SCAN123 Best Of Hardstyle/01. D-Block - Takin Off.mp3'
        
        song = LabelSong(file_path)
        song.tag_collection.set_item(TITLE, "Takin Off")
        song.tag_collection.set_item(ARTIST, "D-Block")
        song.parse()
        
        self.assertEqual(song.publisher(), 'Scantraxx')
        self.assertEqual(song.catalog_number(), 'SCAN123')

    def test_publisher_extraction_different_depth(self):
        """Test extraction when path is deeper."""
        file_path = '/home/user/music/labels/Dirty Workz/DWX456 Remixes/Remix.mp3'
        
        song = LabelSong(file_path)
        self.assertEqual(song._publisher, 'Dirty Workz')
        self.assertEqual(song._catalog_number, 'DWX456')

    def test_catalog_number_no_space(self):
        """Test catalog number extraction when there is no space in the folder name."""
        file_path = '/tmp/Labels/Fusion/FUSION001/Track.mp3'
        
        song = LabelSong(file_path)
        self.assertEqual(song._publisher, 'Fusion')
        self.assertEqual(song._catalog_number, 'FUSION001')

if __name__ == '__main__':
    unittest.main()
