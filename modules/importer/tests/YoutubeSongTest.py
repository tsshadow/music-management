import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Minimal environment variables for Settings
os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('music_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '0')
os.environ.setdefault('DB_PASS', '')
os.environ.setdefault('DB_DB', 'db')

# Stub dotenv used by Settings
sys.modules['dotenv'] = types.ModuleType('dotenv')
sys.modules['dotenv'].load_dotenv = lambda *a, **k: None

# Ensure we're using the real YoutubeSong module (other tests may stub it)
sys.modules.pop('postprocessing.Song.YoutubeSong', None)

from postprocessing.constants import ALBUM
from postprocessing.Song.YoutubeSong import YoutubeSong


class YoutubeSongTest(unittest.TestCase):
    @patch('postprocessing.Song.BaseSong.BaseSong.parse')
    @patch('postprocessing.Song.BaseSong.TagCollection')
    @patch('postprocessing.Song.BaseSong.MP4')
    def test_album_set_to_youtube_channel(self, mock_mp4, mock_tag_collection_cls, mock_base_parse):
        mock_file = MagicMock()
        mock_file.tags = {}
        mock_mp4.return_value = mock_file

        tag_collection = MagicMock()
        tag_collection.get_item_as_string.return_value = None
        mock_tag_collection_cls.return_value = tag_collection

        song = YoutubeSong('/tmp/Q-dance/test.m4a', {'uploader': 'Q-dance'})
        song.parse()

        tag_collection.set_item.assert_any_call(ALBUM, 'Youtube (Q-dance)')


if __name__ == '__main__':
    unittest.main()
