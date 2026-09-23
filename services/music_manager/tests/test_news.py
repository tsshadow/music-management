import os
import sys
import tempfile
import threading
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
            'nos-2026-08-20T18-00-00.mp3',
        )

    def test_two_captures_in_the_same_minute_get_different_files(self):
        # Minute resolution made two record-now calls share one .part file and one filename.
        self.assertNotEqual(
            news.bulletin_filename('nos', 1787248800.0),
            news.bulletin_filename('nos', 1787248830.0),
        )


def _capture_source(**overrides):
    """A source row as the recorder reads it, with the fields a capture needs."""
    source = {
        'id': 1,
        'slug': 'nos',
        'stream_url': 'http://stream.test/mp3',
        'duration_seconds': 600,
        'lead_seconds': 5,
        'retention_count': 12,
    }
    source.update(overrides)
    return source


def _writing_capture(size=14688000):
    """A capture_stream stand-in that leaves a real `.part` file behind, as the real one does."""

    def capture(_url, target, _duration):
        with open(target, 'wb') as handle:
            handle.write(b'mp3')
        return size

    return capture


class NewsCaptureTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name
        patcher = patch('services.music_manager.routers.news.news_dir', return_value=self.tmpdir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _files(self):
        return sorted(os.listdir(self.tmpdir))

    @patch('services.music_manager.routers.news.prune_bulletins', return_value=0)
    @patch('services.music_manager.routers.news.probe_duration_ms', return_value=612000)
    @patch('services.music_manager.routers.news.capture_stream')
    @patch('services.music_manager.routers.news.get_db_connection')
    def test_stores_a_finished_capture(self, mock_get_db, mock_capture, _mock_probe, _mock_prune):
        mock_capture.side_effect = _writing_capture()
        conn = MagicMock()
        mock_get_db.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.lastrowid = 42
        bulletin_id = news.capture_once(_capture_source(), 1787248795.0)
        self.assertEqual(bulletin_id, 42)
        self.assertTrue(mock_capture.call_args[0][1].endswith('.part'))
        self.assertEqual(self._files(), ['nos-2026-08-20T18-00-00.mp3'])
        insert = cursor.execute.call_args[0][0]
        self.assertIn('INSERT INTO news_bulletins', insert)
        self.assertEqual(cursor.execute.call_args[0][1][1], 1787248800.0)
        conn.close.assert_called_once()

    @patch('services.music_manager.routers.news.get_db_connection')
    @patch('services.music_manager.routers.news.probe_duration_ms', return_value=612000)
    @patch('services.music_manager.routers.news.capture_stream')
    def test_holds_no_connection_while_the_stream_is_captured(self, mock_capture, _mock_probe, mock_get_db):
        # A capture takes ten minutes; a pool connection parked for that long starves the API.
        seen_during_capture = []

        def capture(url, target, duration):
            seen_during_capture.append(mock_get_db.call_count)
            return _writing_capture()(url, target, duration)

        mock_capture.side_effect = capture
        mock_get_db.return_value = MagicMock()
        with patch('services.music_manager.routers.news.prune_bulletins', return_value=0):
            news.capture_once(_capture_source(), 1787248795.0)
        self.assertEqual(seen_during_capture, [0])
        self.assertEqual(mock_get_db.call_count, 1)

    @patch('services.music_manager.routers.news.get_db_connection')
    @patch('services.music_manager.routers.news.probe_duration_ms', return_value=30000)
    @patch('services.music_manager.routers.news.capture_stream')
    def test_discards_a_capture_shorter_than_a_minute(self, mock_capture, _mock_probe, mock_get_db):
        mock_capture.side_effect = _writing_capture(720000)
        bulletin_id = news.capture_once(_capture_source(), 1787248795.0)
        self.assertIsNone(bulletin_id)
        self.assertEqual(self._files(), [])
        mock_get_db.assert_not_called()

    @patch('services.music_manager.routers.news.capture_stream')
    def test_a_stream_that_drops_leaves_no_part_file(self, mock_capture):
        def dropping(_url, target, _duration):
            with open(target, 'wb') as handle:
                handle.write(b'half a bulletin')
            raise ConnectionError('stream dropped')

        mock_capture.side_effect = dropping
        with self.assertRaises(ConnectionError):
            news.capture_once(_capture_source(), 1787248795.0)
        self.assertEqual(self._files(), [])

    @patch('services.music_manager.routers.news.probe_duration_ms', side_effect=ValueError('not an mp3'))
    @patch('services.music_manager.routers.news.capture_stream')
    def test_an_unreadable_capture_leaves_no_part_file(self, mock_capture, _mock_probe):
        mock_capture.side_effect = _writing_capture()
        with self.assertRaises(ValueError):
            news.capture_once(_capture_source(), 1787248795.0)
        self.assertEqual(self._files(), [])

    @patch('services.music_manager.routers.news.get_db_connection', return_value=None)
    @patch('services.music_manager.routers.news.probe_duration_ms', return_value=612000)
    @patch('services.music_manager.routers.news.capture_stream')
    def test_a_capture_whose_row_cannot_be_stored_removes_its_file(self, mock_capture, _mock_probe, _mock_get_db):
        # Without its row nothing would ever serve or prune the file.
        mock_capture.side_effect = _writing_capture()
        with self.assertRaises(RuntimeError):
            news.capture_once(_capture_source(), 1787248795.0)
        self.assertEqual(self._files(), [])

    def test_prune_deletes_files_and_rows_beyond_retention(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{'id': 7, 'filename': 'nos-old.mp3'}]
        with (
            patch('services.music_manager.routers.news.os.path.exists', return_value=True),
            patch('services.music_manager.routers.news.os.remove') as mock_remove,
        ):
            removed = news.prune_bulletins(conn, _capture_source())
        self.assertEqual(removed, 1)
        mock_remove.assert_called_once_with(os.path.join(self.tmpdir, 'nos-old.mp3'))
        self.assertIn('DELETE FROM news_bulletins', cursor.execute.call_args[0][0])

    def test_prune_keeps_at_least_the_bulletin_just_recorded(self):
        # A row stored before validation existed can still hold 0 or a negative count:
        # 0 pruned the new bulletin, a negative OFFSET failed after the insert.
        for stored in (0, -3, None):
            conn = MagicMock()
            cursor = conn.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = []
            news.prune_bulletins(conn, _capture_source(retention_count=stored))
            self.assertEqual(cursor.execute.call_args[0][1], (1, 1), stored)

    def test_a_file_that_cannot_be_deleted_does_not_stop_the_prune(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [{'id': 7, 'filename': 'a.mp3'}, {'id': 8, 'filename': 'b.mp3'}]
        with (
            patch('services.music_manager.routers.news.os.path.exists', return_value=True),
            patch('services.music_manager.routers.news.os.remove', side_effect=PermissionError('read-only')),
        ):
            removed = news.prune_bulletins(conn, _capture_source())
        self.assertEqual(removed, 2)
        deletes = [c for c in cursor.execute.call_args_list if 'DELETE' in c[0][0]]
        self.assertEqual(len(deletes), 2)


class NewsRecorderTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('services.music_manager.routers.news.get_db_connection')
        self.mock_get_db = patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = MagicMock()
        self.mock_get_db.return_value = self.conn
        self.cursor = self.conn.cursor.return_value.__enter__.return_value

    def _updates(self):
        return ' '.join(call[0][0] for call in self.cursor.execute.call_args_list)

    @patch('services.music_manager.routers.news.capture_once')
    def test_retries_once_after_a_failure(self, mock_capture):
        mock_capture.side_effect = [ConnectionError('boom'), 5]
        with patch('services.music_manager.routers.news.time.sleep') as mock_sleep:
            bulletin_id = news.record_source(_capture_source(), 1787248795.0)
        self.assertEqual(bulletin_id, 5)
        self.assertEqual(mock_capture.call_count, 2)
        mock_sleep.assert_called_once_with(news.RETRY_DELAY_SECONDS)

    @patch('services.music_manager.routers.news.capture_once')
    def test_gives_up_on_the_hour_and_records_the_error(self, mock_capture):
        mock_capture.side_effect = ConnectionError('still down')
        with patch('services.music_manager.routers.news.time.sleep'):
            bulletin_id = news.record_source(_capture_source(), 1787248795.0)
        self.assertIsNone(bulletin_id)
        self.assertIn('last_error', self._updates())

    def test_only_the_sources_due_at_that_boundary_are_recorded(self):
        # 17:30:00 UTC: the on-the-hour source is due at 17:59:55, the half-past
        # one not until 18:29:55, and recording both now would file the second
        # bulletin under an hour it does not belong to.
        now = 1787247000.0
        on_the_hour = {'slug': 'nos', 'minute_of_hour': 0, 'lead_seconds': 5}
        half_past = {'slug': 'other', 'minute_of_hour': 30, 'lead_seconds': 5}
        sources = [on_the_hour, half_past]
        capture_at = min(news.next_capture_at(now, s['minute_of_hour'], s['lead_seconds']) for s in sources)
        self.assertEqual(news.sources_due_at(sources, capture_at, now), [on_the_hour])

    @patch('services.music_manager.routers.news.capture_once', return_value=9)
    def test_success_clears_the_error_and_stamps_the_time(self, _mock_capture):
        news.record_source(_capture_source(), 1787248795.0)
        self.assertIn('last_success_at', self._updates())
        self.assertIn('last_error = NULL', self._updates())
        self.conn.close.assert_called_once()

    @patch('services.music_manager.routers.news.capture_once', return_value=9)
    def test_a_failure_to_store_the_outcome_is_not_retried_as_a_capture(self, mock_capture):
        # Marking the source used to sit inside the retry: a database hiccup after a good
        # capture recorded the whole bulletin a second time.
        self.mock_get_db.return_value = None
        with self.assertRaises(RuntimeError):
            news.record_source(_capture_source(), 1787248795.0)
        self.assertEqual(mock_capture.call_count, 1)

    @patch('services.music_manager.routers.news.capture_once')
    def test_a_source_records_one_capture_at_a_time(self, mock_capture):
        source = _capture_source(id=77)
        lock = news._source_lock(77)
        lock.acquire()
        try:
            self.assertTrue(news.is_recording(77))
            self.assertIsNone(news.record_source(source, 1787248795.0))
        finally:
            lock.release()
        mock_capture.assert_not_called()
        self.assertFalse(news.is_recording(77))

    @patch('services.music_manager.routers.news.capture_once', side_effect=ConnectionError('down'))
    def test_the_lock_is_released_after_a_failed_capture(self, _mock_capture):
        with patch('services.music_manager.routers.news.time.sleep'):
            news.record_source(_capture_source(id=78), 1787248795.0)
        self.assertFalse(news.is_recording(78))

    def test_due_sources_are_captured_side_by_side(self):
        # Two sources due at the same boundary: the second must not wait ten minutes
        # for the first. Each capture blocks until both have started.
        started = threading.Barrier(2, timeout=5)

        def capture(source, _capture_at):
            started.wait()
            return source['id']

        with patch('services.music_manager.routers.news.record_source', side_effect=capture) as mock_record:
            news.record_due_sources([_capture_source(id=1), _capture_source(id=2, slug='bnr')], 1787248795.0)
        self.assertEqual(mock_record.call_count, 2)

    def test_one_failing_source_does_not_hide_the_others(self):
        calls = []

        def record(source, _capture_at):
            calls.append(source['slug'])
            if source['slug'] == 'nos':
                raise RuntimeError('Database unavailable')
            return 3

        with (
            patch('services.music_manager.routers.news.record_source', side_effect=record),
            self.assertLogs('music-manager.news', level='ERROR') as logs,
        ):
            news.record_due_sources([_capture_source(), _capture_source(id=2, slug='bnr')], 1787248795.0)
        self.assertEqual(sorted(calls), ['bnr', 'nos'])
        self.assertIn('nos', logs.output[0])

    def test_nothing_due_starts_no_pool(self):
        with patch('services.music_manager.routers.news.ThreadPoolExecutor') as mock_pool:
            news.record_due_sources([], 1787248795.0)
        mock_pool.assert_not_called()


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
            {'id': 2, 'slug': 'nos', 'started_at': 1787248800.0, 'duration_ms': 612000, 'size_bytes': 14688000},
        ]
        response = self.client.get('/api/news/bulletins?source=nos', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'bulletins': [
                    {
                        'id': 2,
                        'source': 'nos',
                        'started_at': 1787248800.0,
                        'duration_ms': 612000,
                        'size_bytes': 14688000,
                    },
                ]
            },
        )
        self.assertIn('ORDER BY started_at DESC', cursor.execute.call_args[0][0])

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_lists_sources_with_their_health(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                'slug': 'nos',
                'name': 'NOS Nieuws (NPO Radio 1)',
                'stream_url': news.DEFAULT_STREAM_URL,
                'minute_of_hour': 0,
                'duration_seconds': 600,
                'retention_count': 12,
                'enabled': 1,
                'last_error': None,
                'last_success_at': 1787248800.0,
            },
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
        response = self.client.get('/api/news/bulletins/latest?source=nos', headers={'x-api-key': self.api_key})
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

    def test_an_inverted_range_is_not_satisfiable(self):
        # bytes=10-5 used to produce a negative Content-Length.
        start, end = news.parse_range('bytes=8-5', 10)
        self.assertFalse(news.range_is_satisfiable(start, end, 10))

    def test_a_range_past_the_end_is_not_satisfiable(self):
        start, end = news.parse_range('bytes=10-', 10)
        self.assertFalse(news.range_is_satisfiable(start, end, 10))

    def test_an_empty_suffix_is_not_satisfiable(self):
        start, end = news.parse_range('bytes=-0', 10)
        self.assertFalse(news.range_is_satisfiable(start, end, 10))

    def test_a_normal_range_is_satisfiable(self):
        self.assertTrue(news.range_is_satisfiable(2, 5, 10))
        self.assertTrue(news.range_is_satisfiable(9, 9, 10))


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
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'filename': 'nos-2026-08-20T18-00.mp3'}
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_bulletin(tmpdir)
            with patch('services.music_manager.routers.news.news_dir', return_value=tmpdir):
                response = self.client.get('/api/news/bulletins/1/stream', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'0123456789')
        self.assertEqual(response.headers['accept-ranges'], 'bytes')

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_serves_a_partial_range(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'filename': 'nos-2026-08-20T18-00.mp3'}
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_bulletin(tmpdir)
            with patch('services.music_manager.routers.news.news_dir', return_value=tmpdir):
                response = self.client.get(
                    '/api/news/bulletins/1/stream', headers={'x-api-key': self.api_key, 'Range': 'bytes=2-5'}
                )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b'2345')
        self.assertEqual(response.headers['content-range'], 'bytes 2-5/10')

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_an_inverted_range_answers_416(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'filename': 'nos-2026-08-20T18-00.mp3'}
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_bulletin(tmpdir)
            with patch('services.music_manager.routers.news.news_dir', return_value=tmpdir):
                response = self.client.get(
                    '/api/news/bulletins/1/stream', headers={'x-api-key': self.api_key, 'Range': 'bytes=8-5'}
                )
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response.headers['content-range'], 'bytes */10')

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_missing_file_is_a_404_not_a_crash(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'filename': 'gone.mp3'}
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('services.music_manager.routers.news.news_dir', return_value=tmpdir):
                response = self.client.get('/api/news/bulletins/1/stream', headers={'x-api-key': self.api_key})
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
        return {
            'id': 1,
            'slug': 'nos',
            'stream_url': 'http://stream.test/mp3',
            'minute_of_hour': 0,
            'duration_seconds': 600,
            'lead_seconds': 5,
            'retention_count': 12,
        }

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_record_now_answers_at_once_and_records_in_the_background(self, mock_get_db):
        # A capture takes as long as the recording, so holding the request open
        # would time out at the proxy for a capture that actually succeeded.
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = self._source_row()
        with patch('services.music_manager.routers.news.threading.Thread') as mock_thread:
            response = self.client.post('/api/news/sources/nos/record-now', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'started': True, 'slug': 'nos', 'duration_seconds': 600})
        self.assertEqual(mock_thread.call_args.kwargs['target'], news._record_in_background)
        mock_thread.return_value.start.assert_called_once()

    @patch('services.music_manager.routers.news.record_source', return_value=None)
    @patch('services.music_manager.routers.news.get_db_connection')
    def test_the_background_capture_holds_no_connection_itself(self, mock_get_db, mock_record):
        news._record_in_background(self._source_row())
        self.assertEqual(mock_record.call_count, 1)
        mock_get_db.assert_not_called()

    @patch('services.music_manager.routers.news.capture_once', return_value=4)
    @patch('services.music_manager.routers.news.get_db_connection', return_value=None)
    def test_the_background_capture_survives_a_dead_database(self, _mock_get_db, _mock_capture):
        with self.assertLogs('music-manager.news', level='ERROR'):
            news._record_in_background(self._source_row())

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_record_now_refuses_a_source_that_is_already_recording(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = self._source_row()
        lock = news._source_lock(1)
        lock.acquire()
        try:
            with patch('services.music_manager.routers.news.threading.Thread') as mock_thread:
                response = self.client.post('/api/news/sources/nos/record-now', headers={'x-api-key': self.api_key})
        finally:
            lock.release()
        self.assertEqual(response.status_code, 409)
        mock_thread.assert_not_called()

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_create_refuses_out_of_range_settings(self, mock_get_db):
        base = {'slug': 'bnr', 'name': 'BNR', 'stream_url': 'http://stream.test/bnr'}
        for field, value in (
            ('minute_of_hour', 60),
            ('minute_of_hour', -1),
            ('duration_seconds', 0),
            ('duration_seconds', news.MAX_BULLETIN_SECONDS + 1),
            ('retention_count', 0),
            ('retention_count', -5),
            ('lead_seconds', -1),
        ):
            response = self.client.post(
                '/api/news/sources', headers={'x-api-key': self.api_key}, json={**base, field: value}
            )
            self.assertEqual(response.status_code, 422, (field, value))
        mock_get_db.assert_not_called()

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_update_refuses_out_of_range_settings(self, mock_get_db):
        for body in ({'retention_count': 0}, {'minute_of_hour': 75}, {'duration_seconds': -10}):
            response = self.client.put('/api/news/sources/nos', headers={'x-api-key': self.api_key}, json=body)
            self.assertEqual(response.status_code, 422, body)
        mock_get_db.assert_not_called()

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_create_accepts_settings_in_range(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        response = self.client.post(
            '/api/news/sources',
            headers={'x-api-key': self.api_key},
            json={
                'slug': 'bnr',
                'name': 'BNR',
                'stream_url': 'http://stream.test/bnr',
                'minute_of_hour': 59,
                'duration_seconds': 60,
                'retention_count': 1,
            },
        )
        self.assertEqual(response.status_code, 201)

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_delete_removes_the_bulletin_files_too(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = self._source_row()
        cursor.fetchall.return_value = [{'filename': 'nos-a.mp3'}, {'filename': 'nos-gone.mp3'}]
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'nos-a.mp3'), 'wb') as handle:
                handle.write(b'x')
            with open(os.path.join(tmpdir, 'keep.mp3'), 'wb') as handle:
                handle.write(b'x')
            with patch('services.music_manager.routers.news.news_dir', return_value=tmpdir):
                response = self.client.delete('/api/news/sources/nos', headers={'x-api-key': self.api_key})
            remaining = os.listdir(tmpdir)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(remaining, ['keep.mp3'])
        statements = ' '.join(call[0][0] for call in cursor.execute.call_args_list)
        self.assertIn('DELETE FROM news_bulletins', statements)
        self.assertIn('DELETE FROM news_sources', statements)

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_delete_survives_a_file_that_cannot_be_removed(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = self._source_row()
        cursor.fetchall.return_value = [{'filename': 'nos-a.mp3'}]
        with (
            patch('services.music_manager.routers.news.news_dir', return_value='/tmp/news'),
            patch('services.music_manager.routers.news.os.path.exists', return_value=True),
            patch('services.music_manager.routers.news.os.remove', side_effect=PermissionError('read-only')),
        ):
            response = self.client.delete('/api/news/sources/nos', headers={'x-api-key': self.api_key})
        self.assertEqual(response.status_code, 200)
        conn.commit.assert_called_once()

    @patch('services.music_manager.routers.news.get_db_connection')
    def test_updating_an_unknown_source_is_a_404(self, mock_get_db):
        conn = MagicMock()
        mock_get_db.return_value = conn
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        response = self.client.put(
            '/api/news/sources/bbc', headers={'x-api-key': self.api_key}, json={'duration_seconds': 300}
        )
        self.assertEqual(response.status_code, 404)
