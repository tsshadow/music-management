import os
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# Minimal env vars for Settings
os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('music_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '0')
os.environ.setdefault('DB_PASS', '')
os.environ.setdefault('DB_DB', 'db')

# Stub dotenv
sys.modules['dotenv'] = types.ModuleType('dotenv')
sys.modules['dotenv'].load_dotenv = lambda *a, **k: None

# ensure real mutagen modules are available
for mod in ['mutagen', 'mutagen.easyid3', 'mutagen.easymp4', 'mutagen.id3', 'mutagen.mp4']:
    sys.modules.pop(mod, None)

cache_mod = types.ModuleType('postprocessing.Song.Helpers.Cache')
cache_mod.databaseHelpers = {"artists": MagicMock(), "genres": MagicMock()}
sys.modules['postprocessing.Song.Helpers.Cache'] = cache_mod
for mod_name, class_name in [
    ('postprocessing.Song.TelegramSong', 'TelegramSong'),
    ('postprocessing.Song.GenericSong', 'GenericSong'),
    ('postprocessing.Song.SoundcloudSong', 'SoundcloudSong'),
    ('postprocessing.Song.YoutubeSong', 'YoutubeSong'),
    ('postprocessing.Song.LabelSong', 'LabelSong'),
]:
    mod = types.ModuleType(mod_name)
    setattr(mod, class_name, type(class_name, (), {}))
    sys.modules[mod_name] = mod

import api.tags as tags_api


class TagsAPITest(unittest.TestCase):
    def test_get_tags(self):
        with patch.object(tags_api.Tagger, 'available_tags', return_value=['artist', 'genre']):
            resp = tags_api.get_tags()
        self.assertEqual(resp, {'tags': ['artist', 'genre']})

    def test_post_tags_invokes_tagger(self):
        with patch.object(tags_api.Tagger, 'parse_song') as mock_parse:
            payload = tags_api.TagPayload(file='song.mp3', tag='genre', value='Trance')
            resp = tags_api.add_tag(payload)
        self.assertEqual(resp, {'status': 'ok'})
        mock_parse.assert_called_once()
        args, kwargs = mock_parse.call_args
        self.assertEqual(args[2], {'genre': 'Trance'})


if __name__ == '__main__':
    unittest.main()
