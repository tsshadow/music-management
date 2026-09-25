import unittest
from unittest.mock import MagicMock, patch

import pytest

from services.tests.mock_base import reset_database_helpers

pytestmark = pytest.mark.mock_base('mutagen', 'Cache')

from services.tagger.constants import ARTIST, TITLE
from services.tagger.Song import LabelSong as label_song_module
from services.tagger.Song.LabelSong import LabelSong


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
        file_path = '/mnt/music/Scantraxx/SCAN123 Best Of Hardstyle/01. D-Block - Takin Off.mp3'
        song = LabelSong(file_path)
        song.tag_collection.set_item(TITLE, 'Takin Off')
        song.tag_collection.set_item(ARTIST, 'D-Block')
        song.parse()
        self.assertEqual(song.publisher(), 'Scantraxx')
        self.assertEqual(song.catalog_number(), 'SCAN123')

    def test_publisher_extraction_different_depth(self):
        """Test extraction when path is deeper."""
        file_path = '/mnt/music/labels/Dirty Workz/DWX456 Remixes/Remix.mp3'
        song = LabelSong(file_path)
        self.assertEqual(song._publisher, 'Dirty Workz')
        self.assertEqual(song._catalog_number, 'DWX456')

    def test_catalog_number_no_space(self):
        """Test catalog number extraction when there is no space in the folder name."""
        file_path = '/mnt/music/Labels/Fusion/FUSION001/Track.mp3'
        song = LabelSong(file_path)
        self.assertEqual(song._publisher, 'Fusion')
        self.assertEqual(song._catalog_number, 'FUSION001')

    def test_publisher_from_eps_root_when_release_folder_is_nested(self):
        """A scene release that repeats its folder inside itself keeps the label."""
        release = 'Hartshorn_-_LOSE_CTRL-(ABSLT065)-SINGLE-WEB-2026-SRG'
        file_path = f'/eps/ABSLT Records/ABSLT065 - {release}/{release}/01-hartshorn_-_lose_ctrl_(original_mix).mp3'
        with patch.object(label_song_module, 's', MagicMock(eps_folder_path='/eps', delimiter='/')):
            song = LabelSong(file_path)
        self.assertEqual(song._publisher, 'ABSLT Records')
        self.assertEqual(song._catalog_number, 'ABSLT065')

    def test_publisher_from_eps_root_at_normal_depth(self):
        """The usual label/release/file layout is unchanged by the EPs anchor."""
        file_path = '/eps/Scantraxx/SCAN123 Best Of Hardstyle/01. D-Block - Takin Off.mp3'
        with patch.object(label_song_module, 's', MagicMock(eps_folder_path='/eps', delimiter='/')):
            song = LabelSong(file_path)
        self.assertEqual(song._publisher, 'Scantraxx')
        self.assertEqual(song._catalog_number, 'SCAN123')

    def test_track_loose_in_the_label_folder_still_gets_the_label(self):
        """No release folder at all: the label survives, the catalog number is empty."""
        file_path = '/eps/ABSLT Records/01-hartshorn_-_lose_ctrl.mp3'
        with patch.object(label_song_module, 's', MagicMock(eps_folder_path='/eps', delimiter='/')):
            song = LabelSong(file_path)
        self.assertEqual(song._publisher, 'ABSLT Records')
        self.assertEqual(song._catalog_number, '')

    def test_path_outside_the_eps_root_falls_back_to_the_parent_folders(self):
        """Importer paths that are not under the EPs root keep the old behaviour."""
        file_path = '/import/Scantraxx/SCAN123 Best Of Hardstyle/01. D-Block - Takin Off.mp3'
        with patch.object(label_song_module, 's', MagicMock(eps_folder_path='/eps', delimiter='/')):
            song = LabelSong(file_path)
        self.assertEqual(song._publisher, 'Scantraxx')
        self.assertEqual(song._catalog_number, 'SCAN123')


if __name__ == '__main__':
    unittest.main()
