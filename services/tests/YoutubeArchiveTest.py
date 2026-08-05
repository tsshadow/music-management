import unittest
from unittest.mock import patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()
# Import under the fully-qualified "services." name, the same one the code under
# test uses. This file used to swap sys.modules['...DatabaseConnector'] for a stub
# at import time, which leaked into every test module that ran after it and made
# two unrelated tests fail depending on collection order.
from services.downloader.youtube.YoutubeArchive import YoutubeArchive


class FakeCursor:

    def __init__(self, row):
        self.row = row
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def execute(self, query, params=None):
        self.queries.append((' '.join(query.split()), params))

    def fetchone(self):
        return self.row


class FakeConnection:

    def __init__(self, row=None):
        self.fake_cursor = FakeCursor(row)

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        pass

    def close(self):
        pass


class YoutubeArchiveTest(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()

    def _with_connection(self, connection):
        return patch('services.downloader.youtube.YoutubeArchive.DatabaseConnector',
                     return_value=type('Connector', (), {'connect': lambda _self: connection})())

    def test_exists_returns_false_when_not_present(self):
        connection = FakeConnection(row=None)
        with self._with_connection(connection):
            self.assertFalse(YoutubeArchive.exists('acc', 'vid'))

    def test_exists_returns_true_when_present(self):
        connection = FakeConnection(row=(1,))
        with self._with_connection(connection):
            self.assertTrue(YoutubeArchive.exists('acc', 'vid'))

    def test_exists_asks_for_one_download_type(self):
        """Audio and video of the same video are separate archive rows."""
        connection = FakeConnection(row=None)
        with self._with_connection(connection):
            YoutubeArchive.exists('@qdance', 'vid', 'video')
        query, params = connection.fake_cursor.queries[-1]
        self.assertIn('download_type = %s', query)
        self.assertEqual(params, ('@qdance', 'vid', 'video'))

    def test_insert_records_the_download_type(self):
        connection = FakeConnection(row=None)
        with self._with_connection(connection):
            YoutubeArchive.insert('@qdance', 'vid', '/mnt/music/Youtube_Video/Q-dance/Set.mkv',
                                  'https://youtu.be/vid', 'Set', download_type='video')
        query, params = connection.fake_cursor.queries[-1]
        self.assertIn('INSERT IGNORE INTO downloads_youtube_archive', query)
        self.assertEqual(params[-1], 'video')

    def test_insert_skips_incomplete_rows(self):
        connection = FakeConnection(row=None)
        with self._with_connection(connection):
            YoutubeArchive.insert('', 'vid', '/tmp/x.m4a', 'https://youtu.be/vid', 'Set')
        self.assertEqual(connection.fake_cursor.queries, [])


if __name__ == '__main__':
    unittest.main()
