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

# Stub databaseHelpers to avoid DB access
cache_mod = types.ModuleType('postprocessing.Song.Helpers.Cache')
cache_mod.databaseHelpers = {
    'artists': MagicMock(),
    'ignored_artists': MagicMock(),
    'genres': MagicMock(),
    'ignored_genres': MagicMock(),
    'artistGenreHelper': MagicMock(),
    'subgenreHelper': MagicMock(),
}
sys.modules['postprocessing.Song.Helpers.Cache'] = cache_mod

# Ensure we're using the real SoundcloudSong module (other tests may stub it)
sys.modules.pop('postprocessing.Song.SoundcloudSong', None)
from postprocessing.constants import ALBUM
from postprocessing.Song.SoundcloudSong import SoundcloudSong


class SoundcloudSongTest(unittest.TestCase):
    @patch('postprocessing.Song.BaseSong.BaseSong.parse')
    @patch('postprocessing.Song.BaseSong.TagCollection')
    @patch('postprocessing.Song.BaseSong.EasyID3')
    @patch('postprocessing.Song.BaseSong.MP3')
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
