import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.mp3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

from fastapi.testclient import TestClient

from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.main import app
from services.music_manager.routers import news


class NewsSchemaTest(unittest.TestCase):

    def test_creates_both_tables_and_seeds_the_nos_source(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        news.init_db(cursor)
        statements = ' '.join(call[0][0] for call in cursor.execute.call_args_list)
        self.assertIn('CREATE TABLE IF NOT EXISTS news_sources', statements)
        self.assertIn('CREATE TABLE IF NOT EXISTS news_bulletins', statements)
        self.assertIn('INSERT IGNORE INTO news_sources', statements)
        seeded = [call[0][1] for call in cursor.execute.call_args_list if len(call[0]) > 1]
        self.assertIn(news.DEFAULT_STREAM_URL, seeded[0])


class NewsScheduleTest(unittest.TestCase):

    def test_next_capture_is_five_seconds_before_the_coming_hour(self):
        # 2026-08-20 17:30:00 UTC -> the 18:00 capture opens at 17:59:55
        self.assertEqual(
            news.next_capture_at(1787247000.0, minute_of_hour=0, lead_seconds=5),
            1787248795.0,
        )

    def test_next_capture_skips_to_the_following_hour_when_the_lead_has_passed(self):
        # One second late for 17:59:55, so the next chance is an hour on.
        self.assertEqual(
            news.next_capture_at(1787248796.0, minute_of_hour=0, lead_seconds=5),
            1787252395.0,
        )

    def test_started_at_is_the_intended_hour_not_the_connect_time(self):
        self.assertEqual(news.bulletin_started_at(1787248795.0, lead_seconds=5), 1787248800.0)

    def test_filename_names_the_intended_hour(self):
        self.assertEqual(
            news.bulletin_filename('nos', 1787248800.0),
            'nos-2026-08-20T18-00.mp3',
        )


class NewsCaptureTest(unittest.TestCase):

    def _source(self):
        return {'id': 1, 'slug': 'nos', 'stream_url': 'http://stream.test/mp3',
                'duration_seconds': 600, 'lead_seconds': 5, 'retention_count': 12}

    @patch('services.music_manager.routers.news.prune_bulletins', return_value=0)
    @patch('services.music_manager.routers.news.probe_duration_ms', return_value=612000)
    @patch('services.music_manager.routers.news.capture_stream', return_value=14688000)
    def test_stores_a_finished_capture(self, mock_capture, _mock_probe, _mock_prune):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.lastrowid = 42
        with patch('services.music_manager.routers.news.news_dir', return_value='/tmp/news'), \
             patch('services.music_manager.routers.news.os.replace') as mock_replace:
            bulletin_id = news.capture_once(conn, self._source(), 1787248795.0)
        self.assertEqual(bulletin_id, 42)
        self.assertTrue(mock_capture.call_args[0][1].endswith('.part'))
        mock_replace.assert_called_once()
        insert = cursor.execute.call_args[0][0]
        self.assertIn('INSERT INTO news_bulletins', insert)
        self.assertEqual(cursor.execute.call_args[0][1][1], 1787248800.0)

    @patch('services.music_manager.routers.news.probe_duration_ms', return_value=30000)
    @patch('services.music_manager.routers.news.capture_stream', return_value=720000)
    def test_discards_a_capture_shorter_than_a_minute(self, _mock_capture, _mock_probe):
        conn = MagicMock()
        with patch('services.music_manager.routers.news.news_dir', return_value='/tmp/news'), \
             patch('services.music_manager.routers.news.os.replace') as mock_replace, \
             patch('services.music_manager.routers.news.os.remove') as mock_remove:
            bulletin_id = news.capture_once(conn, self._source(), 1787248795.0)
        self.assertIsNone(bulletin_id)
        mock_replace.assert_not_called()
        mock_remove.assert_called_once()

    def test_prune_deletes_files_and_rows_beyond_retention(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{'id': 7, 'filename': 'nos-old.mp3'}]
        with patch('services.music_manager.routers.news.news_dir', return_value='/tmp/news'), \
             patch('services.music_manager.routers.news.os.path.exists', return_value=True), \
             patch('services.music_manager.routers.news.os.remove') as mock_remove:
            removed = news.prune_bulletins(conn, self._source())
        self.assertEqual(removed, 1)
        mock_remove.assert_called_once_with('/tmp/news/nos-old.mp3')
        self.assertIn('DELETE FROM news_bulletins', cursor.execute.call_args[0][0])


class NewsRecorderTest(unittest.TestCase):

    def _source(self):
        return {'id': 1, 'slug': 'nos', 'stream_url': 'http://stream.test/mp3',
                'duration_seconds': 600, 'lead_seconds': 5, 'retention_count': 12}

    @patch('services.music_manager.routers.news.capture_once')
    def test_retries_once_after_a_failure(self, mock_capture):
        mock_capture.side_effect = [ConnectionError('boom'), 5]
        conn = MagicMock()
        with patch('services.music_manager.routers.news.time.sleep') as mock_sleep:
            bulletin_id = news.record_source(conn, self._source(), 1787248795.0)
        self.assertEqual(bulletin_id, 5)
        self.assertEqual(mock_capture.call_count, 2)
        mock_sleep.assert_called_once_with(news.RETRY_DELAY_SECONDS)

    @patch('services.music_manager.routers.news.capture_once')
    def test_gives_up_on_the_hour_and_records_the_error(self, mock_capture):
        mock_capture.side_effect = ConnectionError('still down')
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        with patch('services.music_manager.routers.news.time.sleep'):
            bulletin_id = news.record_source(conn, self._source(), 1787248795.0)
        self.assertIsNone(bulletin_id)
        updates = ' '.join(call[0][0] for call in cursor.execute.call_args_list)
        self.assertIn('last_error', updates)

    def test_only_the_sources_due_at_that_boundary_are_recorded(self):
        # 17:30:00 UTC: the on-the-hour source is due at 17:59:55, the half-past
        # one not until 18:29:55, and recording both now would file the second
        # bulletin under an hour it does not belong to.
        now = 1787247000.0
        on_the_hour = {'slug': 'nos', 'minute_of_hour': 0, 'lead_seconds': 5}
        half_past = {'slug': 'other', 'minute_of_hour': 30, 'lead_seconds': 5}
        sources = [on_the_hour, half_past]
        capture_at = min(
            news.next_capture_at(now, s['minute_of_hour'], s['lead_seconds']) for s in sources
        )
        self.assertEqual(news.sources_due_at(sources, capture_at, now), [on_the_hour])

    @patch('services.music_manager.routers.news.capture_once', return_value=9)
    def test_success_clears_the_error_and_stamps_the_time(self, _mock_capture):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        news.record_source(conn, self._source(), 1787248795.0)
        updates = ' '.join(call[0][0] for call in cursor.execute.call_args_list)
        self.assertIn('last_success_at', updates)
        self.assertIn('last_error = NULL', updates)


class NewsEndpointsTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_lists_bulletins_newest_first(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {'id': 2, 'slug': 'nos', 'started_at': 1787248800.0, 'duration_ms': 612000,
             'size_bytes': 14688000},
        ]
        response = self.client.get('/api/news/bulletins?source=nos',
                                   headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'bulletins': [
            {'id': 2, 'source': 'nos', 'started_at': 1787248800.0,
             'duration_ms': 612000, 'size_bytes': 14688000},
        ]})
        self.assertIn('ORDER BY started_at DESC', cursor.execute.call_args[0][0])

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_lists_sources_with_their_health(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {'slug': 'nos', 'name': 'NOS Nieuws (NPO Radio 1)',
             'stream_url': news.DEFAULT_STREAM_URL, 'minute_of_hour': 0,
             'duration_seconds': 600, 'retention_count': 12, 'enabled': 1,
             'last_error': None, 'last_success_at': 1787248800.0},
        ]
        response = self.client.get('/api/news/sources', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        source = response.json()['sources'][0]
        self.assertEqual(source['slug'], 'nos')
        self.assertTrue(source['enabled'])
        self.assertIsNone(source['last_error'])

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_latest_returns_404_when_nothing_is_recorded_yet(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        response = self.client.get('/api/news/bulletins/latest?source=nos',
                                   headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 404)

    def test_bulletins_require_an_api_key(self):
        self.assertEqual(self.client.get('/api/news/bulletins').status_code, 401)


class NewsRangeTest(unittest.TestCase):

    def test_no_header_means_the_whole_file(self):
        self.assertIsNone(news.parse_range(None, 10))

    def test_open_ended_range_runs_to_the_last_byte(self):
        self.assertEqual(news.parse_range('bytes=2-', 10), (2, 9))

    def test_closed_range_is_clamped_to_the_file(self):
        self.assertEqual(news.parse_range('bytes=2-99', 10), (2, 9))

    def test_suffix_range_counts_back_from_the_end(self):
        self.assertEqual(news.parse_range('bytes=-3', 10), (7, 9))

    def test_nonsense_falls_back_to_the_whole_file(self):
        self.assertIsNone(news.parse_range('pages=1-2', 10))


class NewsStreamTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

    @staticmethod
    def _write_bulletin(tmpdir):
        path = os.path.join(tmpdir, 'nos-2026-08-20T18-00.mp3')
        with open(path, 'wb') as handle:
            handle.write(b'0123456789')
        return path

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_serves_the_whole_file_without_a_range_header(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {
            'filename': 'nos-2026-08-20T18-00.mp3'}
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_bulletin(tmpdir)
            with patch('services.music_manager.routers.news.news_dir', return_value=tmpdir):
                response = self.client.get('/api/news/bulletins/1/stream',
                                           headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'0123456789')
        self.assertEqual(response.headers['accept-ranges'], 'bytes')

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_serves_a_partial_range(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {
            'filename': 'nos-2026-08-20T18-00.mp3'}
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_bulletin(tmpdir)
            with patch('services.music_manager.routers.news.news_dir', return_value=tmpdir):
                response = self.client.get('/api/news/bulletins/1/stream',
                                           headers={'x-api-key': self.api_key,
                                                    'Range': 'bytes=2-5'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b'2345')
        self.assertEqual(response.headers['content-range'], 'bytes 2-5/10')

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_missing_file_is_a_404_not_a_crash(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {
            'filename': 'gone.mp3'}
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('services.music_manager.routers.news.news_dir', return_value=tmpdir):
                response = self.client.get('/api/news/bulletins/1/stream',
                                           headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 404)


class NewsManagementTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_updates_the_recording_settings(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {'id': 1, 'slug': 'nos'}
        response = self.client.put(
            '/api/news/sources/nos',
            headers={'x-api-key': self.api_key},
            json={'duration_seconds': 300, 'retention_count': 6},
        )
        self.assertEqual(response.status_code, 200)
        updates = ' '.join(call[0][0] for call in cursor.execute.call_args_list)
        self.assertIn('UPDATE news_sources SET', updates)

    @staticmethod
    def _source_row():
        return {'id': 1, 'slug': 'nos', 'stream_url': 'http://stream.test/mp3',
                'minute_of_hour': 0, 'duration_seconds': 600, 'lead_seconds': 5,
                'retention_count': 12}

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_record_now_answers_at_once_and_records_in_the_background(self, mock_get_db):
        # A capture takes as long as the recording, so holding the request open
        # would time out at the proxy for a capture that actually succeeded.
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = self._source_row()
        with patch('services.music_manager.routers.news.threading.Thread') as mock_thread:
            response = self.client.post('/api/news/sources/nos/record-now',
                                        headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {'started': True, 'slug': 'nos', 'duration_seconds': 600}
        )
        self.assertEqual(mock_thread.call_args.kwargs['target'], news._record_in_background)
        mock_thread.return_value.start.assert_called_once()

    @patch('services.music_manager.routers.news.record_source', return_value=None)
    @patch('services.music_manager.routers.news.get_db_connection')
    def test_the_background_capture_uses_its_own_connection(self, mock_get_db, mock_record):
        conn = MagicMock()
        mock_get_db.return_value = conn
        news._record_in_background(self._source_row())
        self.assertEqual(mock_record.call_count, 1)
        conn.close.assert_called_once()

    @patch('services.music_manager.routers.news.get_db_connection', return_value=None)
    def test_the_background_capture_survives_a_dead_database(self, _mock_get_db):
        news._record_in_background(self._source_row())

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_updating_an_unknown_source_is_a_404(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        response = self.client.put('/api/news/sources/bbc',
                                   headers={'x-api-key': self.api_key},
                                   json={'duration_seconds': 300})
        self.assertEqual(response.status_code, 404)
