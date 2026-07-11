import sys
import types
import unittest
mock_db = types.ModuleType('services.common.Helpers.DatabaseConnector')

class DummyConnector:

    def connect(self):

        class DummyConn:

            def cursor(self):

                class Ctx:

                    def __enter__(self):
                        return self

                    def __exit__(self, exc_type, exc, tb):
                        pass

                    def execute(self, q, params=None):
                        pass

                    def fetchone(self):
                        return None
                return Ctx()

            def commit(self):
                pass
        return DummyConn()
mock_db.DatabaseConnector = DummyConnector
sys.modules['services.common.Helpers.DatabaseConnector'] = mock_db
from downloader.youtube import YoutubeArchive

class YoutubeArchiveTest(unittest.TestCase):

    def test_exists_returns_false_when_not_present(self):
        self.assertFalse(YoutubeArchive.exists('acc', 'vid'))
if __name__ == '__main__':
    unittest.main()