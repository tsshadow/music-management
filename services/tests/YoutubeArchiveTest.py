import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from services.tests.mock_base import reset_database_helpers

pytestmark = pytest.mark.mock_base('yt_dlp', 'Cache')

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
        # Mirrors both entry points of the real DatabaseConnector: the archive
        # helpers go through `connection()` so the socket is always closed again.
        @contextmanager
        def _connection(_self):
            try:
                yield connection
            finally:
                connection.close()

        return patch(
            'services.downloader.youtube.YoutubeArchive.DatabaseConnector',
            return_value=type('Connector', (), {'connect': lambda _self: connection, 'connection': _connection})(),
        )

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
            YoutubeArchive.insert(
                '@qdance',
                'vid',
                '/mnt/music/Youtube_Video/Q-dance/Set.mkv',
                'https://youtu.be/vid',
                'Set',
                download_type='video',
            )
        query, params = connection.fake_cursor.queries[-1]
        self.assertIn('INSERT INTO downloads_youtube_archive', query)
        # The three trailing values are download_type and info_json twice -- once for the
        # insert, once for the ON DUPLICATE KEY branch.
        self.assertEqual(params[-3], 'video')

    def test_insert_skips_incomplete_rows(self):
        connection = FakeConnection(row=None)
        with self._with_connection(connection):
            YoutubeArchive.insert('', 'vid', '/tmp/x.m4a', 'https://youtu.be/vid', 'Set')
        self.assertEqual(connection.fake_cursor.queries, [])

    def test_what_youtube_knew_is_stored_beside_the_row(self):
        """The music-credit panel, which the title split can only guess at."""
        connection = FakeConnection(row=None)
        with self._with_connection(connection):
            YoutubeArchive.insert(
                '@qdance',
                'vid',
                '/tmp/x.m4a',
                'https://youtu.be/vid',
                'Set',
                raw_info={'id': 'vid', 'artists': ['Angerfist'], 'track': 'Raise Your Fist'},
            )
        stored = json.loads(connection.fake_cursor.queries[-1][1][-1])
        self.assertEqual(['Angerfist'], stored['artists'])
        self.assertEqual('Raise Your Fist', stored['track'])

    def test_a_row_archived_before_the_column_existed_is_filled_in(self):
        """This table is keyed on (video_id, download_type), so a re-download conflicts.

        Ignoring the conflict would leave 53295 rows without their metadata forever, even
        for the videos that are fetched again. COALESCE is what keeps the *first* answer
        rather than the newest -- a re-download says nothing better about a video.
        """
        connection = FakeConnection(row=None)
        with self._with_connection(connection):
            YoutubeArchive.insert('@qdance', 'vid', '/tmp/x.m4a', 'https://youtu.be/vid', 'Set', raw_info={'id': 'vid'})
        query, _ = connection.fake_cursor.queries[-1]
        self.assertIn('ON DUPLICATE KEY UPDATE info_json = COALESCE(info_json, %s)', query)

    def test_a_download_does_not_follow_its_uploader(self):
        """One manual download must not subscribe the whole channel, nor add a second spelling of it."""
        connection = FakeConnection(row=None)
        with self._with_connection(connection):
            YoutubeArchive.insert(
                '@qdance', 'vid', '/tmp/x.m4a', 'https://youtu.be/vid', 'Set', raw_info={'channel_id': 'UC123'}
            )
        queries = [query for query, _params in connection.fake_cursor.queries]
        self.assertFalse([query for query in queries if 'downloads_youtube_accounts' in query], queries)
        self.assertIn('INSERT INTO downloads_youtube_archive', queries[-1])


if __name__ == '__main__':
    unittest.main()
