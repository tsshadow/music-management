import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('music_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '0')
os.environ.setdefault('DB_PASS', '')
os.environ.setdefault('DB_DB', 'db')
sys.modules['dotenv'] = types.ModuleType('dotenv')
sys.modules['dotenv'].load_dotenv = lambda *a, **k: None
from services.tagger.constants import SongTypeEnum

class TaggerManualOverrideTest(unittest.TestCase):

    def test_manual_tag_applied_after_parse(self):
        dummy_song = MagicMock()
        dummy_song.tag_collection = MagicMock()
        orig_mods = {m: sys.modules.get(m) for m in ['mutagen', 'mutagen.easyid3', 'mutagen.easymp4', 'mutagen.id3', 'mutagen.mp4', 'postprocessing.Song.Helpers.Cache', 'postprocessing.Song.TelegramSong', 'postprocessing.Song.GenericSong', 'postprocessing.Song.SoundcloudSong', 'postprocessing.Song.YoutubeSong']}
        try:
            for mod in ['mutagen', 'mutagen.easyid3', 'mutagen.easymp4', 'mutagen.id3', 'mutagen.mp4']:
                sys.modules.pop(mod, None)
            cache_mod = types.ModuleType('postprocessing.Song.Helpers.Cache')
            cache_mod.databaseHelpers = {'artists': MagicMock(), 'genres': MagicMock()}
            sys.modules['postprocessing.Song.Helpers.Cache'] = cache_mod
            for mod_name, class_name in [('postprocessing.Song.TelegramSong', 'TelegramSong'), ('postprocessing.Song.GenericSong', 'GenericSong'), ('postprocessing.Song.SoundcloudSong', 'SoundcloudSong'), ('postprocessing.Song.YoutubeSong', 'YoutubeSong')]:
                mod = types.ModuleType(mod_name)
                setattr(mod, class_name, type(class_name, (), {}))
                sys.modules[mod_name] = mod
            from services.tagger.tagger import Tagger as TaggerClass
            with patch('services.tagger.tagger.LabelSong', return_value=dummy_song):
                TaggerClass.parse_song(Path('file.mp3'), SongTypeEnum.LABEL, {'genre': 'Trance'})
            dummy_song.parse.assert_called_once()
            dummy_song.tag_collection.add.assert_called_with('genre', 'Trance')
            dummy_song.save_file.assert_called_once()
        finally:
            for m, old_m in orig_mods.items():
                if old_m: sys.modules[m] = old_m
                else: sys.modules.pop(m, None)
if __name__ == '__main__':
    unittest.main()