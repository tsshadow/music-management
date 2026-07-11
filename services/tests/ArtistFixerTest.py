import os
import sys
import types
import tempfile
import unittest
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch
os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')
sys.modules['dotenv'] = types.ModuleType('dotenv')
sys.modules['dotenv'].load_dotenv = lambda *a, **k: None
sys.modules.setdefault('requests', types.ModuleType('requests'))
try:
    import mutagen
except ImportError:
    mutagen = types.ModuleType('mutagen')
    mutagen.__path__ = []
    sys.modules['mutagen'] = mutagen
mutagen.MutagenError = getattr(mutagen, 'MutagenError', Exception)
cache_mod = types.ModuleType('services.common.Helpers.Cache')
cache_mod.databaseHelpers = {'library_artists': MagicMock()}
sys.modules['services.common.Helpers.Cache'] = cache_mod
from services.tagger.Song.rules.TagResult import TagResult, TagResultType
from services.other import artistfixer

class ArtistFixerTest(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ['music_folder_path'] = self.tempdir.name
        Path(self.tempdir.name, 'one.mp3').touch()
        Path(self.tempdir.name, 'two.flac').touch()
        sub = Path(self.tempdir.name, 'sub')
        sub.mkdir()
        Path(sub, 'three.m4a').touch()
        Path(sub, 'skip.txt').touch()
        self.created_paths = []
        self.mocks = {}

        def fake_base_song(path):
            self.created_paths.append(Path(path))
            song = MagicMock()
            song.artist.return_value = 'New Artist'
            song.tag_collection.get_item.return_value = MagicMock()
            song.save_file.return_value = None
            return song
        self.mocks['rule_instance'] = MagicMock()
        self.mocks['rule_instance'].apply.return_value = TagResult('New Artist', TagResultType.VALID)
        importlib.reload(artistfixer)
        self.mocks['artist_db'] = artistfixer.databaseHelpers['library_artists']
        self.mocks['artist_db'].exists.return_value = False
        patcher_settings = patch.object(artistfixer, 'Settings', return_value=types.SimpleNamespace(music_folder_path=self.tempdir.name))
        patcher_bs = patch.object(artistfixer, 'BaseSong', side_effect=fake_base_song)
        patcher_rule = patch.object(artistfixer, 'VerifyArtistRule', return_value=self.mocks['rule_instance'])
        for p in (patcher_settings, patcher_bs, patcher_rule):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tempdir.cleanup)
        self.fix = artistfixer.ArtistFixer()

    def test_run_processes_supported_files(self):
        with patch('builtins.print') as mock_print:
            self.fix.run()
        self.assertEqual(len(self.created_paths), 3)
        self.assertEqual(self.mocks['rule_instance'].apply.call_count, 3)
        self.assertTrue(all(('library_artists table' in call.args[0] for call in mock_print.call_args_list)))
if __name__ == '__main__':
    unittest.main()