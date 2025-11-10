import os
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Provide minimal env vars for Settings
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

from postprocessing.constants import SongTypeEnum


class TaggerManualOverrideTest(unittest.TestCase):
    def test_manual_tag_applied_after_parse(self):
        dummy_song = MagicMock()
        dummy_song.tag_collection = MagicMock()

        # ensure real mutagen modules are available
        for mod in ['mutagen', 'mutagen.easyid3', 'mutagen.easymp4', 'mutagen.id3', 'mutagen.mp4']:
            sys.modules.pop(mod, None)

        cache_mod = types.ModuleType('postprocessing.Song.Helpers.Cache')
        cache_mod.databaseHelpers = {"artists": MagicMock(), "genres": MagicMock()}
        sys.modules['postprocessing.Song.Helpers.Cache'] = cache_mod
        # stub other song modules to avoid heavy imports
        for mod_name, class_name in [
            ('postprocessing.Song.TelegramSong', 'TelegramSong'),
            ('postprocessing.Song.GenericSong', 'GenericSong'),
            ('postprocessing.Song.SoundcloudSong', 'SoundcloudSong'),
            ('postprocessing.Song.YoutubeSong', 'YoutubeSong'),
        ]:
            mod = types.ModuleType(mod_name)
            setattr(mod, class_name, type(class_name, (), {}))
            sys.modules[mod_name] = mod

        from postprocessing import tagger as tagger_module
        with patch.object(tagger_module, 'LabelSong', return_value=dummy_song):
            tagger_module.Tagger.parse_song(Path('file.mp3'), SongTypeEnum.LABEL, {'genre': 'Trance'})

        dummy_song.parse.assert_called_once()
        dummy_song.tag_collection.add.assert_called_with('genre', 'Trance')
        dummy_song.save_file.assert_called_once()

if __name__ == '__main__':
    unittest.main()
