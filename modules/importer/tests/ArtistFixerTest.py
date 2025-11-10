import os
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# provide minimal env vars for Settings
os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')
# will set music_folder_path in setUp

# stub dotenv
sys.modules['dotenv'] = types.ModuleType('dotenv')
sys.modules['dotenv'].load_dotenv = lambda *a, **k: None

# stub requests used by ExternalArtistLookup
sys.modules.setdefault('requests', types.ModuleType('requests'))

# ensure mutagen module provides MutagenError for artistfixer import
mutagen_mod = sys.modules.setdefault('mutagen', types.ModuleType('mutagen'))
setattr(mutagen_mod, 'MutagenError', Exception)

# prepare stub Cache module before importing ArtistFixer
cache_mod = types.ModuleType('postprocessing.Song.Helpers.Cache')
cache_mod.databaseHelpers = {"artists": MagicMock()}
sys.modules['postprocessing.Song.Helpers.Cache'] = cache_mod

from postprocessing.Song.rules.TagResult import TagResult, TagResultType
import importlib
import postprocessing.artistfixer as artistfixer

class ArtistFixerTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ['music_folder_path'] = self.tempdir.name

        # create some dummy files
        Path(self.tempdir.name, 'one.mp3').touch()
        Path(self.tempdir.name, 'two.flac').touch()
        sub = Path(self.tempdir.name, 'sub'); sub.mkdir()
        Path(sub, 'three.m4a').touch()
        Path(sub, 'skip.txt').touch()

        self.created_paths = []
        def fake_base_song(path):
            self.created_paths.append(Path(path))
            song = MagicMock()
            song.artist.return_value = 'New Artist'
            song.tag_collection.get_item.return_value = MagicMock()
            song.save_file.return_value = None
            return song

        self.rule_instance = MagicMock()
        self.rule_instance.apply.return_value = TagResult('New Artist', TagResultType.VALID)

        importlib.reload(artistfixer)
        self.artist_db = artistfixer.databaseHelpers['artists']
        self.artist_db.exists.return_value = False

        self.patcher_settings = patch.object(
            artistfixer,
            'Settings',
            return_value=types.SimpleNamespace(music_folder_path=self.tempdir.name)
        )
        self.patcher_bs = patch.object(artistfixer, 'BaseSong', side_effect=fake_base_song)
        self.patcher_rule = patch.object(artistfixer, 'VerifyArtistRule', return_value=self.rule_instance)
        for p in (self.patcher_settings, self.patcher_bs, self.patcher_rule):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tempdir.cleanup)

        self.fix = artistfixer.ArtistFixer()

    def test_run_processes_supported_files(self):
        with patch('builtins.print') as mock_print:
            self.fix.run()

        # three supported files should be processed
        self.assertEqual(len(self.created_paths), 3)
        self.assertEqual(self.rule_instance.apply.call_count, 3)
        # prints should indicate artists were added
        self.assertTrue(all('artists table' in call.args[0] for call in mock_print.call_args_list))

if __name__ == '__main__':
    unittest.main()
