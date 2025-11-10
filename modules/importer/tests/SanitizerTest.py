import sys
import types
import unittest
import tempfile
import os
from pathlib import Path

# Provide dummy environment values required by Settings
os.environ.setdefault('import_folder_path', '/tmp')
os.environ.setdefault('music_folder_path', '/tmp')
os.environ.setdefault('eps_folder_path', '/tmp')
os.environ.setdefault('delimiter', '/')

# Stub dotenv module used by Settings
sys.modules['dotenv'] = types.ModuleType('dotenv')
sys.modules['dotenv'].load_dotenv = lambda *args, **kwargs: None

from postprocessing.sanitizer import Sanitizer

class SanitizerTest(unittest.TestCase):
    def test_replace_invalid_characters(self):
        sanitizer = Sanitizer()
        original = 'bad/name|with:chars'
        expected = 'bad-name-with-chars'
        self.assertEqual(sanitizer.replace_invalid_characters(original), expected)

    def test_sanitize_file_renames(self):
        sanitizer = Sanitizer()
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / 'bad|name.txt'
            bad_path.write_text('test')
            sanitizer.sanitize_file(bad_path)
            self.assertFalse(bad_path.exists())
            self.assertTrue((Path(tmp) / 'bad-name.txt').exists())

if __name__ == '__main__':
    unittest.main()
