import json
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users
from services.music_manager.api_key import resolve_system_api_key

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.music_manager.main import app


class RadioChannelsTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_lists_enabled_channels(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'slug': 'main', 'name': 'Radio', 'genre': None, 'filter_json': None, 'enabled': 1},
            {
                'slug': 'qdance',
                'name': 'Q-dance',
                'genre': None,
                'filter_json': '{"label": "Q-dance Records"}',
                'enabled': 1,
            },
        ]
        response = self.client.get('/api/radio/channels', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'channels': [
                    {'slug': 'main', 'name': 'Radio', 'genre': None, 'enabled': True, 'filter': {}},
                    {
                        'slug': 'qdance',
                        'name': 'Q-dance',
                        'genre': None,
                        'enabled': True,
                        'filter': {'label': 'Q-dance Records'},
                    },
                ]
            },
        )
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn('FROM radio_channels', query)
        self.assertIn('enabled = 1', query)

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_include_disabled_lists_channels_that_are_off_the_air(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'slug': 'off', 'name': 'Off', 'genre': None, 'filter_json': None, 'enabled': 0},
        ]
        response = self.client.get('/api/radio/channels?include_disabled=true', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['channels'][0]['enabled'])
        self.assertNotIn('enabled = 1', mock_cursor.execute.call_args[0][0])

    def test_include_disabled_needs_the_manage_permission(self):
        with patch('services.music_manager.routers.users.verify_api_key') as mock_verify:

            def _listener(_x_api_key=None):
                return {'type': 'user', 'user': {'id': 5, 'permissions': ['music.play'], 'role_name': 'user'}}

            mock_verify.side_effect = _listener
            response = self.client.get(
                '/api/radio/channels?include_disabled=true', headers={'x-api-key': 'listener-key'}
            )
            self.assertEqual(response.status_code, 403)

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
        return {
            'track_id': track_id,
            'title': 't',
            'artist': 'a',
            'album': 'b',
            'cover_art': None,
            'duration_ms': seconds * 1000,
        }

    def test_starts_at_now_when_timeline_is_empty(self):
        from services.music_manager.routers import radio

        entries = radio.plan_entries(None, 1000.0, [self._candidate('tr-1', 60)], horizon=30.0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['started_at'], 1000.0)
        self.assertEqual(entries[0]['ends_at'], 1060.0)

    def test_appends_back_to_back_after_existing_end(self):
        from services.music_manager.routers import radio

        entries = radio.plan_entries(
            1200.0, 1000.0, [self._candidate('tr-1', 60), self._candidate('tr-2', 30)], horizon=300.0
        )
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
    def _conn_with_end(self, existing_end, scheduled=()):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {'last_end': existing_end}
        cursor.fetchall.return_value = [{'track_id': t} for t in scheduled]
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
        self.assertEqual(mock_fetch.call_args[0][0], {})

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
        self.assertEqual(mock_fetch.call_args[0][0], {'genre': 'hardstyle'})

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_passes_stored_filter_to_fetch(self, mock_fetch):
        from services.music_manager.routers import radio

        mock_fetch.return_value = []
        conn, _ = self._conn_with_end(None)
        radio.fill_channel(
            conn,
            {
                'id': 5,
                'slug': 'qdance',
                'genre': None,
                'filter_json': '{"label": "Q-dance Records", "length": "short"}',
            },
            now=1000.0,
        )
        self.assertEqual(mock_fetch.call_args[0][0], {'label': 'Q-dance Records', 'length': 'short'})

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_does_not_schedule_a_track_already_on_the_timeline(self, mock_fetch):
        from services.music_manager.routers import radio

        mock_fetch.return_value = [
            {'track_id': 'tr-1', 'title': 't', 'artist': 'a', 'album': 'b', 'cover_art': None, 'duration_ms': 700000},
            {'track_id': 'tr-2', 'title': 't', 'artist': 'a', 'album': 'b', 'cover_art': None, 'duration_ms': 700000},
        ]
        conn, cursor = self._conn_with_end(None, scheduled=['tr-1'])
        inserted = radio.fill_channel(conn, {'id': 3, 'slug': 'main', 'genre': None}, now=1000.0)
        self.assertEqual(inserted, 1)
        insert_call = next(c for c in cursor.execute.call_args_list if 'INSERT INTO radio_timeline' in c[0][0])
        self.assertEqual(insert_call[0][1][1], 'tr-2')

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_lms_failure_does_not_raise(self, mock_fetch):
        from services.music_manager.routers import radio

        mock_fetch.side_effect = RuntimeError('LMS down')
        conn, _ = self._conn_with_end(None)
        self.assertEqual(radio.fill_channel(conn, {'id': 3, 'slug': 'main', 'genre': None}, now=1000.0), 0)


class CandidateFailureLoggingTest(unittest.TestCase):
    """A down LMS used to raise one WARNING -- an event plus an ntfy alert -- per
    channel every five seconds, each carrying the request URL with the apiKey."""

    LEAKY = RuntimeError(
        '401 Client Error: Unauthorized for url: http://lms:5082/rest/getSongsByFilter?apiKey=s3cret&v=1.16.1&c=muma-radio'
    )

    def setUp(self):
        from services.music_manager.routers import radio

        self.radio = radio
        radio._channels_in_outage.clear()
        self.addCleanup(radio._channels_in_outage.clear)

    def _conn(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {'last_end': None}
        cursor.fetchall.return_value = []
        return conn

    def _fill(self, slug='main'):
        return self.radio.fill_channel(self._conn(), {'id': 3, 'slug': slug, 'genre': None}, now=1000.0)

    def test_the_api_key_never_reaches_the_log(self):
        with patch.object(self.radio, 'fetch_candidate_tracks', side_effect=self.LEAKY):
            with self.assertLogs('music-manager.radio', level='DEBUG') as logs:
                self._fill()
                self._fill()
        text = '\n'.join(logs.output)
        self.assertNotIn('s3cret', text)
        self.assertIn('getSongsByFilter?<redacted>', text)

    def test_one_warning_per_outage_per_channel_then_debug(self):
        with patch.object(self.radio, 'fetch_candidate_tracks', side_effect=self.LEAKY):
            with self.assertLogs('music-manager.radio', level='DEBUG') as logs:
                for _ in range(5):
                    self._fill('main')
                self._fill('hard')
        warnings = [r for r in logs.records if r.levelname == 'WARNING']
        self.assertEqual(len(warnings), 2)
        self.assertEqual(len([r for r in logs.records if r.levelname == 'DEBUG']), 4)

    def test_a_recovery_ends_the_outage_so_the_next_one_warns_again(self):
        with self.assertLogs('music-manager.radio', level='DEBUG') as logs:
            with patch.object(self.radio, 'fetch_candidate_tracks', side_effect=self.LEAKY):
                self._fill()
            with patch.object(self.radio, 'fetch_candidate_tracks', return_value=[]):
                self._fill()
            with patch.object(self.radio, 'fetch_candidate_tracks', side_effect=self.LEAKY):
                self._fill()
        levels = [r.levelname for r in logs.records]
        self.assertEqual(levels, ['WARNING', 'INFO', 'WARNING'])

    def test_a_failed_tick_raises_without_the_api_key(self):
        # run_forever logs a failed tick with logger.exception, message and traceback
        # both; the tick must hand it neither the key nor the unredacted original.
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = self.LEAKY
        with patch.object(self.radio, 'get_db_connection', return_value=conn):
            with self.assertRaises(RuntimeError) as caught:
                self.radio.radio_tick()
        self.assertNotIn('s3cret', str(caught.exception))
        self.assertIn('getSongsByFilter?<redacted>', str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        conn.close.assert_called_once()


class RadioStateTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

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
        entry = {
            'track_id': 'tr-42',
            'title': 'T',
            'artist': 'A',
            'album': 'B',
            'cover_art': 'al-7',
            'duration_ms': 215000,
            'started_at': 1000.0,
            'ends_at': 1215.0,
        }
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


class ChannelFilterTest(unittest.TestCase):
    def test_reads_the_stored_filter(self):
        from services.music_manager.routers import radio

        self.assertEqual(
            radio.channel_filter({'slug': 'q', 'genre': None, 'filter_json': '{"label": "Dirty Workz"}'}),
            {'label': 'Dirty Workz'},
        )

    def test_falls_back_to_the_legacy_genre_column(self):
        from services.music_manager.routers import radio

        self.assertEqual(radio.channel_filter({'slug': 'h', 'genre': 'hardstyle'}), {'genre': 'hardstyle'})

    def test_no_filter_and_no_genre_is_the_whole_library(self):
        from services.music_manager.routers import radio

        self.assertEqual(radio.channel_filter({'slug': 'main', 'genre': None, 'filter_json': None}), {})

    def test_stored_filter_wins_over_genre(self):
        from services.music_manager.routers import radio

        self.assertEqual(
            radio.channel_filter({'slug': 'q', 'genre': 'hardstyle', 'filter_json': '{"label": "Q-dance Records"}'}),
            {'label': 'Q-dance Records'},
        )

    def test_unreadable_filter_falls_back_rather_than_raising(self):
        from services.music_manager.routers import radio

        self.assertEqual(
            radio.channel_filter({'slug': 'q', 'genre': 'hardstyle', 'filter_json': 'not json'}), {'genre': 'hardstyle'}
        )


class PickCandidatesTest(unittest.TestCase):
    def _candidate(self, track_id):
        return {'track_id': track_id, 'duration_ms': 1000}

    def test_keeps_the_order_lms_randomised(self):
        from services.music_manager.routers import radio

        candidates = [self._candidate('tr-1'), self._candidate('tr-2')]
        self.assertEqual([c['track_id'] for c in radio.pick_candidates(candidates, [])], ['tr-1', 'tr-2'])

    def test_drops_tracks_still_on_the_timeline(self):
        from services.music_manager.routers import radio

        candidates = [self._candidate('tr-1'), self._candidate('tr-2')]
        self.assertEqual([c['track_id'] for c in radio.pick_candidates(candidates, ['tr-1'])], ['tr-2'])

    def test_drops_a_repeat_within_the_same_batch(self):
        from services.music_manager.routers import radio

        candidates = [self._candidate('tr-1'), self._candidate('tr-1'), self._candidate('tr-2')]
        self.assertEqual([c['track_id'] for c in radio.pick_candidates(candidates, [])], ['tr-1', 'tr-2'])

    def test_copes_with_an_empty_timeline_argument(self):
        from services.music_manager.routers import radio

        self.assertEqual(radio.pick_candidates([self._candidate('tr-1')], None), [self._candidate('tr-1')])


class ChannelAdminTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

    def _conn(self, fetchone_values):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = list(fetchone_values)
        return conn, cursor

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_creates_a_channel_from_a_filter(self, mock_get_db):
        conn, cursor = self._conn([None])
        mock_get_db.return_value = conn
        response = self.client.post(
            '/api/radio/channels',
            headers={'x-api-key': self.api_key},
            json={'slug': 'qdance', 'name': 'Q-dance', 'filter': {'label': 'Q-dance Records', 'length': 'short'}},
        )
        self.assertEqual(response.status_code, 201)
        insert = next(c for c in cursor.execute.call_args_list if 'INSERT INTO radio_channels' in c[0][0])
        stored = json.loads(insert[0][1][2])
        self.assertEqual(stored['label'], 'Q-dance Records')
        self.assertEqual(stored['length'], 'short')

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_rejects_a_slug_that_would_not_fit_a_url(self, mock_get_db):
        conn, _ = self._conn([None])
        mock_get_db.return_value = conn
        response = self.client.post(
            '/api/radio/channels',
            headers={'x-api-key': self.api_key},
            json={'slug': 'Q Dance!', 'name': 'Q-dance'},
        )
        self.assertEqual(response.status_code, 400)

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_rejects_a_duplicate_slug(self, mock_get_db):
        conn, _ = self._conn([{'id': 1}])
        mock_get_db.return_value = conn
        response = self.client.post(
            '/api/radio/channels',
            headers={'x-api-key': self.api_key},
            json={'slug': 'main', 'name': 'Radio'},
        )
        self.assertEqual(response.status_code, 409)

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_updating_the_filter_clears_the_legacy_genre(self, mock_get_db):
        conn, cursor = self._conn(
            [
                {'id': 2},
                {
                    'slug': 'hard',
                    'name': 'Hard',
                    'genre': None,
                    'filter_json': '{"label": "Dirty Workz"}',
                    'enabled': 1,
                },
            ]
        )
        mock_get_db.return_value = conn
        response = self.client.put(
            '/api/radio/channels/hard',
            headers={'x-api-key': self.api_key},
            json={'filter': {'label': 'Dirty Workz'}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['filter'], {'label': 'Dirty Workz'})
        update = next(c for c in cursor.execute.call_args_list if c[0][0].startswith('UPDATE radio_channels'))
        self.assertIn('genre = NULL', update[0][0])

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_update_of_unknown_channel_is_404(self, mock_get_db):
        conn, _ = self._conn([None])
        mock_get_db.return_value = conn
        response = self.client.put(
            '/api/radio/channels/nope',
            headers={'x-api-key': self.api_key},
            json={'name': 'Nope'},
        )
        self.assertEqual(response.status_code, 404)

    @patch('services.music_manager.routers.radio.get_db_connection')
    def test_delete_takes_the_timeline_with_it(self, mock_get_db):
        conn, cursor = self._conn([{'id': 7}])
        mock_get_db.return_value = conn
        response = self.client.delete('/api/radio/channels/qdance', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        statements = [c[0][0] for c in cursor.execute.call_args_list]
        self.assertTrue(any('DELETE FROM radio_timeline' in s for s in statements))
        self.assertTrue(any('DELETE FROM radio_channels' in s for s in statements))

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_preview_reports_matches_and_a_sample(self, mock_fetch):
        mock_fetch.return_value = [
            {'track_id': f'tr-{i}', 'title': 'T', 'artist': 'A', 'album': 'B', 'cover_art': None, 'duration_ms': 200000}
            for i in range(12)
        ]
        response = self.client.post(
            '/api/radio/channels/preview',
            headers={'x-api-key': self.api_key},
            json={'filter': {'label': 'Q-dance Records'}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['matched'], 12)
        self.assertFalse(body['truncated'])
        self.assertEqual(len(body['sample']), 10)
        self.assertEqual(mock_fetch.call_args[0][0]['label'], 'Q-dance Records')

    @patch('services.music_manager.routers.radio.fetch_candidate_tracks')
    def test_preview_reports_an_unknown_label_rather_than_failing_silently(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError('LMS returned status=failed error=Not found')
        response = self.client.post(
            '/api/radio/channels/preview',
            headers={'x-api-key': self.api_key},
            json={'filter': {'label': 'No Such Label'}},
        )
        self.assertEqual(response.status_code, 502)

    def test_managing_channels_needs_more_than_being_logged_in(self):
        with patch('services.music_manager.routers.users.verify_api_key') as mock_verify:

            def _listener(_x_api_key=None):
                return {'type': 'user', 'user': {'id': 5, 'permissions': ['music.play'], 'role_name': 'user'}}

            mock_verify.side_effect = _listener
            for method, path in (
                ('post', '/api/radio/channels'),
                ('put', '/api/radio/channels/main'),
                ('delete', '/api/radio/channels/main'),
                ('post', '/api/radio/channels/preview'),
            ):
                response = getattr(self.client, method)(
                    path,
                    headers={'x-api-key': 'listener-key'},
                    **({} if method == 'delete' else {'json': {'slug': 'x', 'name': 'X'}}),
                )
                self.assertEqual(response.status_code, 403, f'{method} {path}')


class RadioInitDbTest(unittest.TestCase):
    def test_init_db_creates_tables_and_seeds_default_channel(self):
        from services.music_manager.routers import radio

        cursor = MagicMock()
        radio.init_db(cursor)
        statements = [call[0][0] for call in cursor.execute.call_args_list]
        self.assertTrue(any('CREATE TABLE IF NOT EXISTS radio_channels' in s for s in statements))
        self.assertTrue(any('CREATE TABLE IF NOT EXISTS radio_timeline' in s for s in statements))
        self.assertTrue(any('INSERT IGNORE INTO radio_channels' in s for s in statements))

    def test_init_db_adds_the_filter_column_when_it_is_missing(self):
        from services.music_manager.routers import radio

        cursor = MagicMock()
        cursor.fetchone.return_value = None
        radio.init_db(cursor)
        statements = [call[0][0] for call in cursor.execute.call_args_list]
        self.assertTrue(any('ADD COLUMN filter_json' in s for s in statements))

    def test_init_db_leaves_an_existing_filter_column_alone(self):
        from services.music_manager.routers import radio

        cursor = MagicMock()
        cursor.fetchone.return_value = {'Field': 'filter_json'}
        radio.init_db(cursor)
        statements = [call[0][0] for call in cursor.execute.call_args_list]
        self.assertFalse(any('ADD COLUMN filter_json' in s for s in statements))
