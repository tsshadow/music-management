import sys
import types
import unittest

# Stub DatabaseConnector
mock_db = types.ModuleType("postprocessing.Song.Helpers.DatabaseConnector")


class DummyConnector:
    def connect(self):
        class DummyConn:
            def cursor(self_inner):
                class Ctx:
                    def __enter__(self_ctx):
                        return self_ctx

                    def __exit__(self_ctx, exc_type, exc, tb):
                        pass

                    def execute(self_ctx, q, params=None):
                        pass

                    def fetchone(self_ctx):
                        return None

                return Ctx()

            def commit(self_inner):
                pass

        return DummyConn()


mock_db.DatabaseConnector = DummyConnector
sys.modules["postprocessing.Song.Helpers.DatabaseConnector"] = mock_db

from downloader.YoutubeArchive import YoutubeArchive


class YoutubeArchiveTest(unittest.TestCase):
    def test_exists_returns_false_when_not_present(self):
        self.assertFalse(YoutubeArchive.exists("acc", "vid"))


if __name__ == "__main__":
    unittest.main()

