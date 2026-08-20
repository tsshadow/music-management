import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.mp3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)

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

    @patch('services.music_manager.routers.news.capture_once', return_value=9)
    def test_success_clears_the_error_and_stamps_the_time(self, _mock_capture):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        news.record_source(conn, self._source(), 1787248795.0)
        updates = ' '.join(call[0][0] for call in cursor.execute.call_args_list)
        self.assertIn('last_success_at', updates)
        self.assertIn('last_error = NULL', updates)
