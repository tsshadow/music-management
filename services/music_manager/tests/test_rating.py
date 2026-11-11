import json
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

# Only stub these when they aren't already provided by services/tests/mock_base.py
# (loaded once for the whole pytest session via services/conftest.py) or by the real
# installed packages -- blindly overwriting sys.modules here would clobber the
# properly-constructed mutagen mock classes with a plain MagicMock, breaking
# isinstance() checks in any importer/downloader test that runs afterward in the
# same pytest session.

import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda only_sources=None: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.music_manager.main import app


class _RatingTable:
    """A stand-in for `rating_tracks` keyed as the real table is, for the statements the handler runs.

    `INSERT ... ON DUPLICATE KEY UPDATE` replaces the row with the same key and `DELETE` removes it,
    so a repeated event can be checked by what the table holds afterwards, not by the SQL text.
    """

    def __init__(self, track_uid: str | None = None):
        self.rows: dict[tuple, int] = {}
        self._track_uid = track_uid
        self._last: str | None = None

    def connection(self) -> MagicMock:
        """A new connection whose cursor writes into this table; one per get_db_connection call."""
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = self
        return conn

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Apply one statement of the handler to the rows."""
        if 'INSERT INTO rating_tracks' in sql:
            entity_type, entity_id, username, rating = params
            self.rows[(entity_type, entity_id, username)] = rating
        elif 'DELETE FROM rating_tracks' in sql:
            self.rows.pop(tuple(params), None)
        self._last = sql

    def fetchone(self):
        """The path lookup's track, or no row for anything else (the username lookup)."""
        if self._last and 'SELECT t.track_uid' in self._last and self._track_uid:
            return {'track_uid': self._track_uid}
        return None


class TestRating(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_handle_lms_event_success(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        payload = {
            'event': 'rating_changed',
            'object_type': 'track',
            'object_id': 'track123',
            'username': 'user',
            'rating': 80,
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'entity_id': 'track123'})
        mock_cursor.execute.assert_called()
        insert_call = next(
            call for call in mock_cursor.execute.call_args_list if 'INSERT INTO rating_tracks' in call[0][0]
        )
        self.assertIn('ON DUPLICATE KEY UPDATE', insert_call[0][0])
        self.assertEqual(insert_call[0][1], ('track', 'track123', 'user', 80))

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_handle_lms_event_with_path_resolution(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'track_uid': 'resolved-uid'}
        payload = {
            'event': 'rating_changed',
            'object_type': 'track',
            'object_id': 'lms-id',
            'username': 'user',
            'rating': 90,
            'path': '/mnt/music/artist/album/song.mp3',
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'entity_id': 'resolved-uid'})
        path_res_call = next(call for call in mock_cursor.execute.call_args_list if 'SELECT t.track_uid' in call[0][0])
        self.assertIn('library_media_files', path_res_call[0][0])
        insert_call = next(
            call for call in mock_cursor.execute.call_args_list if 'INSERT INTO rating_tracks' in call[0][0]
        )
        self.assertEqual(insert_call[0][1][1], 'resolved-uid')

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_handle_lms_event_resolves_lms_library_root(self, mock_get_db):
        """LMS reports paths under its own media-library root (/music), while muma stores
        them under /mnt/music. The lookup must bridge the two, otherwise every event falls
        back to the raw LMS track id and the mirrored rating becomes unusable."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'track_uid': 'resolved-uid'}
        payload = {
            'event': 'rating_changed',
            'object_type': 'track',
            'object_id': '1392868',
            'username': 'user',
            'rating': 5,
            'path': '/music/Soundcloud/EQUAL2/song.mp3',
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'entity_id': 'resolved-uid'})
        path_res_call = next(call for call in mock_cursor.execute.call_args_list if 'SELECT t.track_uid' in call[0][0])
        self.assertIn('/mnt/music/Soundcloud/EQUAL2/song.mp3', path_res_call[0][1])

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_rating_removed_deletes_the_mirrored_row(self, mock_get_db):
        """Clearing a rating in LMS sends ``rating_removed``; the mirror must drop the row
        rather than keep the old star forever (the sync is one-way)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'track_uid': 'resolved-uid'}
        payload = {
            'event': 'rating_removed',
            'object_type': 'track',
            'object_id': '1392868',
            'username': 'user',
            'rating': 0,
            'path': '/music/Soundcloud/EQUAL2/song.mp3',
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'removed', 'entity_id': 'resolved-uid'})
        statements = [call[0][0] for call in mock_cursor.execute.call_args_list]
        self.assertFalse(any('INSERT INTO rating_tracks' in sql for sql in statements))
        delete_call = next(
            call for call in mock_cursor.execute.call_args_list if 'DELETE FROM rating_tracks' in call[0][0]
        )
        self.assertEqual(delete_call[0][1], ('track', 'resolved-uid', 'user'))
        mock_conn.commit.assert_called()

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_rating_changed_to_zero_is_a_removal(self, mock_get_db):
        """No star count below 1 exists, so a zero rating never lands in the mirror."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        payload = {
            'event': 'rating_changed',
            'object_type': 'artist',
            'object_id': 'Headhunterz',
            'username': 'user',
            'rating': 0,
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'removed', 'entity_id': 'Headhunterz'})
        delete_call = next(
            call for call in mock_cursor.execute.call_args_list if 'DELETE FROM rating_tracks' in call[0][0]
        )
        self.assertEqual(delete_call[0][1], ('artist', 'Headhunterz', 'user'))

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_a_repeated_rating_changed_leaves_one_row(self, mock_get_db):
        """LMS's outbox sends a change again when it never saw the answer; the repeat changes nothing."""
        table = _RatingTable(track_uid='resolved-uid')
        mock_get_db.side_effect = lambda: table.connection()
        payload = {
            'event': 'rating_changed',
            'object_type': 'track',
            'object_id': '1392868',
            'username': 'user',
            'rating': 4,
            'path': '/music/a/b.mp3',
        }
        for _ in range(2):
            response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
            self.assertEqual(response.json(), {'status': 'success', 'entity_id': 'resolved-uid'})
        self.assertEqual(table.rows, {('track', 'resolved-uid', 'user'): 4})

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_a_repeated_rating_removed_leaves_no_row(self, mock_get_db):
        table = _RatingTable(track_uid='resolved-uid')
        table.rows[('track', 'resolved-uid', 'user')] = 3
        mock_get_db.side_effect = lambda: table.connection()
        payload = {
            'event': 'rating_removed',
            'object_type': 'track',
            'object_id': '1392868',
            'username': 'user',
            'rating': 0,
            'path': '/music/a/b.mp3',
        }
        for _ in range(2):
            response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
            self.assertEqual(response.json(), {'status': 'removed', 'entity_id': 'resolved-uid'})
        self.assertEqual(table.rows, {})

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_a_path_lookup_without_a_connection_answers_503_and_writes_nothing(self, mock_get_db):
        """Stored under the LMS id and answered 200, the rating would be lost: LMS drops what it
        sees accepted. A 503 keeps it in LMS's outbox for a retry."""
        table = _RatingTable(track_uid='resolved-uid')
        connections = iter([None, table.connection()])
        mock_get_db.side_effect = lambda: next(connections)
        payload = {
            'event': 'rating_changed',
            'object_type': 'track',
            'object_id': '1392868',
            'username': 'user',
            'rating': 5,
            'path': '/music/a/b.mp3',
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(mock_get_db.call_count, 1)
        self.assertEqual(table.rows, {})

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_a_path_that_matches_no_track_keeps_the_lms_id(self, mock_get_db):
        """Not a delivery failure: the rating is stored under the LMS id, as before."""
        table = _RatingTable(track_uid=None)
        mock_get_db.side_effect = lambda: table.connection()
        payload = {
            'event': 'rating_changed',
            'object_type': 'track',
            'object_id': '1392868',
            'username': 'user',
            'rating': 2,
            'path': '/music/a/gone.mp3',
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(table.rows, {('track', '1392868', 'user'): 2})

    def test_candidate_paths_bridges_both_roots(self):
        from services.music_manager.routers.rating import candidate_paths

        self.assertEqual(candidate_paths('/music/a/b.mp3'), ['/music/a/b.mp3', '/mnt/music/a/b.mp3', 'a/b.mp3'])
        self.assertEqual(candidate_paths('/mnt/music/a/b.mp3'), ['/mnt/music/a/b.mp3', '/music/a/b.mp3', 'a/b.mp3'])
        self.assertEqual(candidate_paths('a/b.mp3'), ['a/b.mp3', '/mnt/music/a/b.mp3', '/music/a/b.mp3'])

    def test_handle_lms_event_invalid_event(self):
        payload = {
            'event': 'some_other_event',
            'object_type': 'track',
            'object_id': '123',
            'username': 'user',
            'rating': 50,
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ignored', 'reason': 'unsupported event type'})

    @patch('services.music_manager.routers.rating.get_db_connection')
    def test_handle_lms_event_db_failure(self, mock_get_db):
        mock_get_db.return_value = None
        payload = {
            'event': 'rating_changed',
            'object_type': 'track',
            'object_id': '123',
            'username': 'user',
            'rating': 50,
        }
        response = self.client.post('/api/rating/lms-event', json=payload, headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 500)
        self.assertIn('Database connection failed', response.json()['detail'])

    def test_handle_lms_event_no_auth(self):
        payload = {
            'event': 'rating_changed',
            'object_type': 'track',
            'object_id': '123',
            'username': 'user',
            'rating': 50,
        }
        response = self.client.post('/api/rating/lms-event', json=payload)
        self.assertEqual(response.status_code, 401)

    @patch('services.music_manager.routers.users.get_db_connection')
    def test_get_playlist_tracks_with_rating_filter(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [
            {'username': 'user'},
            {
                'params': json.dumps(
                    {'rating_range': [80, 100], 'genres': ['Trance'], 'size': 100, 'sort_method': 'highest_rated'}
                )
            },
        ]
        mock_cursor.fetchall.return_value = [{'id': 1, 'title': 'Track 1', 'artist': 'Artist 1', 'rating': 90}]
        response = self.client.get('/api/users/1/dynamic-playlists/1/tracks', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        tracks_query_call = next(call for call in mock_cursor.execute.call_args_list if 'SELECT DISTINCT' in call[0][0])
        query = tracks_query_call[0][0]
        params = tracks_query_call[0][1]
        self.assertIn('rt.rating >= %s AND rt.rating <= %s', query)
        self.assertIn('ORDER BY rt.rating DESC', query)
        self.assertIn(80, params)
        self.assertIn(100, params)


if __name__ == '__main__':
    unittest.main()
