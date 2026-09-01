import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# The module file is named "yt-fixer.py", which is not a valid identifier, so it has to
# be loaded straight from its path rather than imported.
_SOURCE = Path(__file__).resolve().parents[1] / 'other' / 'yt-fixer.py'
_spec = importlib.util.spec_from_file_location('yt_fixer', _SOURCE)
yt_fixer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(yt_fixer)


class YtFixerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        patcher = patch.object(yt_fixer, 'BASE_DIR', str(self.base))
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_nested(self, uploader='SomeChannel', album='Album', files=('a.m4a',)):
        """Builds Youtube/<uploader>/<album>/<uploader>/<files> -- the layout to repair."""
        nested = self.base / uploader / album / uploader
        nested.mkdir(parents=True)
        for name in files:
            (nested / name).write_text('audio')
        return nested

    def test_files_from_the_doubled_uploader_folder_move_up_and_the_nesting_goes_away(self):
        nested = self.make_nested(files=('a.m4a', 'b.m4a'))
        with patch('builtins.print'):
            yt_fixer.fix_nested_youtube_dirs()
        uploader_dir = self.base / 'SomeChannel'
        self.assertTrue((uploader_dir / 'a.m4a').exists())
        self.assertTrue((uploader_dir / 'b.m4a').exists())
        self.assertFalse(nested.parent.exists())

    def test_a_file_that_already_exists_upstairs_is_not_overwritten(self):
        self.make_nested(files=('a.m4a',))
        target = self.base / 'SomeChannel' / 'a.m4a'
        target.write_text('the good copy')
        with patch('builtins.print'):
            yt_fixer.fix_nested_youtube_dirs()
        self.assertEqual(target.read_text(), 'the good copy')

    def test_a_loose_file_at_the_top_is_not_treated_as_an_uploader(self):
        (self.base / 'loose.txt').write_text('x')
        with patch('builtins.print'):
            yt_fixer.fix_nested_youtube_dirs()  # must not raise
        self.assertTrue((self.base / 'loose.txt').exists())

    def test_a_loose_file_inside_an_uploader_folder_is_left_alone(self):
        uploader_dir = self.base / 'SomeChannel'
        uploader_dir.mkdir()
        (uploader_dir / 'song.m4a').write_text('audio')
        with patch('builtins.print'):
            yt_fixer.fix_nested_youtube_dirs()
        self.assertTrue((uploader_dir / 'song.m4a').exists())

    def test_a_correctly_shaped_album_folder_is_not_touched(self):
        album = self.base / 'SomeChannel' / 'Album'
        album.mkdir(parents=True)
        (album / 'a.m4a').write_text('audio')
        with patch('builtins.print'):
            yt_fixer.fix_nested_youtube_dirs()
        self.assertTrue((album / 'a.m4a').exists())


if __name__ == '__main__':
    unittest.main()
