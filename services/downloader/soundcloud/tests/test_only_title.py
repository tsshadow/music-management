import unittest
from unittest.mock import MagicMock, patch
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.tagger.constants import TITLE, ARTIST

class TestSoundcloudOnlyTitle(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()

    def test_only_title(self):
        """
        Test that if the SoundCloud title has no delimiters, the uploader is used as artist.
        """
        path = '/tmp/soundcloud/Albino/RIJE MOAT.mp3'
        extra_info = {'uploader': 'Albino', 'title': 'RIJE MOAT'}
        song = SoundcloudSong(path, extra_info)
        song.tag_collection.set_item(TITLE, extra_info['title'])
        song.parse()
        self.assertEqual(song.artist(), 'Albino')
        self.assertEqual(song.title(), 'RIJE MOAT')
if __name__ == '__main__':
    unittest.main()