import unittest
from unittest.mock import MagicMock, patch
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.tagger.constants import ALBUM
from services.tagger.Song.SoundcloudSong import SoundcloudSong

class SoundcloudSongTest(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()

    @patch('services.tagger.Song.BaseSong.BaseSong.parse')
    @patch('services.tagger.Song.BaseSong.TagCollection')
    @patch('services.tagger.Song.BaseSong.EasyID3')
    @patch('services.tagger.Song.BaseSong.MP3')
    def test_album_set_to_soundcloud_uploader(self, mock_mp3, mock_easyid3, mock_tag_collection_cls, mock_base_parse):
        mock_file = MagicMock()
        mock_file.tags = {}
        mock_mp3.return_value = mock_file
        tag_collection = MagicMock()
        tag_collection.get_item_as_string.return_value = None
        mock_tag_collection_cls.return_value = tag_collection
        song = SoundcloudSong('/tmp/Scantraxx/test.mp3', {'uploader': 'Scantraxx'})
        song.parse()
        tag_collection.set_item.assert_any_call(ALBUM, 'Soundcloud (Scantraxx)')
if __name__ == '__main__':
    unittest.main()