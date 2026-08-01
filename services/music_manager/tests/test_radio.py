import unittest
from unittest.mock import MagicMock, patch
import os
import sys

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())
import services.music_manager.ntfy_listener
services.music_manager.ntfy_listener.start_ntfy_listener = lambda: None
import services.music_manager.routers.users
services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database
services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient
from services.music_manager.main import app


class RadioChannelsTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_lists_enabled_channels(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'slug': 'main', 'name': 'Radio', 'genre': None},
        ]
        response = self.client.get('/api/radio/channels', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'channels': [{'slug': 'main', 'name': 'Radio', 'genre': None}]})
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn('FROM radio_channels', query)
        self.assertIn('enabled = 1', query)

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_channels_db_failure_returns_500(self, mock_get_db):
        mock_get_db.return_value = None
        response = self.client.get('/api/radio/channels', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 500)

    def test_channels_requires_api_key(self):
        response = self.client.get('/api/radio/channels')
        self.assertEqual(response.status_code, 401)


class PlanEntriesTest(unittest.TestCase):

    def _candidate(self, track_id, seconds):
        return {'track_id': track_id, 'title': 't', 'artist': 'a', 'album': 'b',
                'cover_art': None, 'duration_ms': seconds * 1000}

    def test_starts_at_now_when_timeline_is_empty(self):
        from services.music_manager.routers import radio
        entries = radio.plan_entries(None, 1000.0, [self._candidate('tr-1', 60)], horizon=30.0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['started_at'], 1000.0)
        self.assertEqual(entries[0]['ends_at'], 1060.0)

    def test_appends_back_to_back_after_existing_end(self):
        from services.music_manager.routers import radio
        entries = radio.plan_entries(1200.0, 1000.0, [self._candidate('tr-1', 60), self._candidate('tr-2', 30)], horizon=300.0)
        self.assertEqual([e['started_at'] for e in entries], [1200.0, 1260.0])
        self.assertEqual([e['ends_at'] for e in entries], [1260.0, 1290.0])

    def test_restarts_at_now_when_timeline_has_fallen_behind(self):
        from services.music_manager.routers import radio
        entries = radio.plan_entries(500.0, 1000.0, [self._candidate('tr-1', 60)], horizon=30.0)
        self.assertEqual(entries[0]['started_at'], 1000.0)

    def test_stops_once_horizon_is_covered(self):
        from services.music_manager.routers import radio
        candidates = [self._candidate(f'tr-{i}', 60) for i in range(10)]
        entries = radio.plan_entries(None, 0.0, candidates, horizon=100.0)
        self.assertEqual(len(entries), 2)

    def test_returns_nothing_when_horizon_already_covered(self):
        from services.music_manager.routers import radio
        entries = radio.plan_entries(2000.0, 1000.0, [self._candidate('tr-1', 60)], horizon=600.0)
        self.assertEqual(entries, [])

    def test_does_not_mutate_candidates(self):
        from services.music_manager.routers import radio
        candidate = self._candidate('tr-1', 60)
        radio.plan_entries(None, 1000.0, [candidate], horizon=30.0)
        self.assertNotIn('started_at', candidate)


class FillChannelTest(unittest.TestCase):

    def _conn_with_end(self, existing_end):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {'last_end': existing_end}
        return conn, cursor

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_inserts_planned_entries(self, mock_fetch):
        from services.music_manager.routers import radio
        mock_fetch.return_value = [
            {'track_id': 'tr-1', 'title': 't', 'artist': 'a', 'album': 'b', 'cover_art': None, 'duration_ms': 700000},
        ]
        conn, cursor = self._conn_with_end(None)
        inserted = radio.fill_channel(conn, {'id': 3, 'slug': 'main', 'genre': None}, now=1000.0)
        self.assertEqual(inserted, 1)
        insert_call = next(c for c in cursor.execute.call_args_list if 'INSERT INTO radio_timeline' in c[0][0])
        self.assertEqual(insert_call[0][1][0], 3)
        self.assertEqual(insert_call[0][1][1], 'tr-1')
        mock_fetch.assert_called_once()
        self.assertIsNone(mock_fetch.call_args[0][0])

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_skips_fetch_when_timeline_already_full(self, mock_fetch):
        from services.music_manager.routers import radio
        conn, _ = self._conn_with_end(1000.0 + radio.SCHEDULE_HORIZON_SECONDS + 60)
        inserted = radio.fill_channel(conn, {'id': 3, 'slug': 'main', 'genre': None}, now=1000.0)
        self.assertEqual(inserted, 0)
        mock_fetch.assert_not_called()

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_passes_channel_genre_to_fetch(self, mock_fetch):
        from services.music_manager.routers import radio
        mock_fetch.return_value = []
        conn, _ = self._conn_with_end(None)
        radio.fill_channel(conn, {'id': 4, 'slug': 'hard', 'genre': 'hardstyle'}, now=1000.0)
        self.assertEqual(mock_fetch.call_args[0][0], 'hardstyle')

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_lms_failure_does_not_raise(self, mock_fetch):
        from services.music_manager.routers import radio
        mock_fetch.side_effect = RuntimeError('LMS down')
        conn, _ = self._conn_with_end(None)
        self.assertEqual(radio.fill_channel(conn, {'id': 3, 'slug': 'main', 'genre': None}, now=1000.0), 0)


class RadioStateTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '00000000-0000-4000-8000-000000000000'

    def test_time_endpoint_returns_epoch_seconds(self):
        response = self.client.get('/api/radio/time', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()['server_time'], 1_700_000_000)

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_state_returns_current_and_next(self, mock_get_db):
        conn = MagicMock()
        cursor = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        entry = {'track_id': 'tr-42', 'title': 'T', 'artist': 'A', 'album': 'B',
                 'cover_art': 'al-7', 'duration_ms': 215000,
                 'started_at': 1000.0, 'ends_at': 1215.0}
        nxt = dict(entry, track_id='tr-43', started_at=1215.0, ends_at=1400.0)
        cursor.fetchone.side_effect = [
            {'id': 1, 'slug': 'main', 'name': 'Radio', 'genre': None},
            entry,
            nxt,
        ]
        response = self.client.get('/api/radio/main/state', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['channel']['slug'], 'main')
        self.assertEqual(body['current']['track_id'], 'tr-42')
        self.assertEqual(body['next']['track_id'], 'tr-43')
        self.assertIn('server_time', body)

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_state_returns_404_for_unknown_channel(self, mock_get_db):
        conn = MagicMock()
        cursor = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = None
        response = self.client.get('/api/radio/nope/state', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 404)

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_state_returns_nulls_when_timeline_empty(self, mock_get_db):
        conn = MagicMock()
        cursor = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            {'id': 1, 'slug': 'main', 'name': 'Radio', 'genre': None},
            None,
            None,
        ]
        response = self.client.get('/api/radio/main/state', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['current'])
        self.assertIsNone(response.json()['next'])


class RadioInitDbTest(unittest.TestCase):

    def test_init_db_creates_tables_and_seeds_default_channel(self):
        from services.music_manager.routers import radio
        cursor = MagicMock()
        radio.init_db(cursor)
        statements = [call[0][0] for call in cursor.execute.call_args_list]
        self.assertTrue(any('CREATE TABLE IF NOT EXISTS radio_channels' in s for s in statements))
        self.assertTrue(any('CREATE TABLE IF NOT EXISTS radio_timeline' in s for s in statements))
        self.assertTrue(any('INSERT IGNORE INTO radio_channels' in s for s in statements))
