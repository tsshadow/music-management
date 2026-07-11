import unittest
from unittest.mock import MagicMock, patch
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.tagger.constants import TITLE, ARTIST

class TestSoundcloudMultiPart(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers
        databaseHelpers['library_artists'].get_all_values.return_value = ['Devin Wild']
        databaseHelpers['library_artists'].exists.return_value = True

    def test_multi_part_split(self):
        """
        Test that 'Part1 | Part2 | Part3' is correctly split.
        Example: 'Defqon 2025 | Devin Wild | Blue'
        """
        path = '/tmp/soundcloud/Q-dance/Defqon 2025 | Devin Wild | Blue.mp3'
        extra_info = {'uploader': 'Q-dance', 'title': 'Defqon 2025 | Devin Wild | Blue'}
        song = SoundcloudSong(path, extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Devin Wild')
        self.assertIn('Defqon 2025', song.title())
        self.assertIn('Blue', song.title())
if __name__ == '__main__':
    unittest.main()