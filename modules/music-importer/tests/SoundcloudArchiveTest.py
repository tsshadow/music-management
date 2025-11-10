import sys
import types
import unittest

# stub DatabaseConnector and numpy
sys.modules['numpy'] = types.ModuleType('numpy')
sub_testing = types.ModuleType('numpy.testing')
sub_testing.print_coercion_tables = lambda *args, **kwargs: None
sys.modules['numpy.testing'] = sub_testing
pc = types.ModuleType('numpy.testing.print_coercion_tables')
pc.print_new_cast_table = lambda *a, **k: None
sys.modules['numpy.testing.print_coercion_tables'] = pc

mock_db = types.ModuleType('postprocessing.Song.Helpers.DatabaseConnector')
class DummyConnector:
    def connect(self):
        class DummyConn:
            def cursor(self):
                class Ctx:
                    def __enter__(self_inner): return self_inner
                    def __exit__(self_inner, exc_type, exc, tb): pass
                    def execute(self_inner, q, params=None): pass
                    def fetchone(self_inner): return None
                return Ctx()
        return DummyConn()
mock_db.DatabaseConnector = DummyConnector
sys.modules['postprocessing.Song.Helpers.DatabaseConnector'] = mock_db

from downloader.SoundcloudArchive import SoundcloudArchive

class SoundcloudArchiveTest(unittest.TestCase):
    def test_get_uploader_id(self):
        info = {'channel_id': '123', 'uploader_id': 'abc'}
        self.assertEqual(SoundcloudArchive._get_uploader_id(info), '123')
        self.assertEqual(SoundcloudArchive._get_uploader_id({'uploader_id': 'abc'}), 'abc')
        self.assertIsNone(SoundcloudArchive._get_uploader_id({}))

if __name__ == '__main__':
    unittest.main()
