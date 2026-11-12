"""tools/backfill_arrival_dates.py: which date a track gets, and the rollback file."""

import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from services.music_manager.tests.scripted_cursor import ScriptedCursor
from tools import backfill_arrival_dates as backfill

ROOT = '/mnt/music'
CREATED = datetime(2026, 7, 4, 12, 0)


def cursor_with(tracks, soundcloud=(), youtube=(), ingestion=()):
    return ScriptedCursor(
        [
            ('SELECT id, created_at FROM library_tracks', None, list(tracks)),
            ('JOIN downloads_soundcloud_archive', None, list(soundcloud)),
            ('JOIN downloads_youtube_archive', None, list(youtube)),
            ('JOIN library_ingestion_records', None, list(ingestion)),
        ]
    )


def row(track_id, path, at):
    return {'track_id': track_id, 'file_path': path, 'at': at}


class PlanTest(unittest.TestCase):
    def test_the_earliest_date_wins_and_names_its_file(self):
        cursor = cursor_with(
            [{'id': 1, 'created_at': CREATED}],
            soundcloud=[row(1, f'{ROOT}/Soundcloud/a/x.m4a', datetime(2024, 5, 1))],
            ingestion=[row(1, f'{ROOT}/import/x.flac', datetime(2023, 1, 1))],
        )
        result = backfill.plan(cursor, ROOT)
        self.assertEqual(result.fills, [backfill.Arrival(1, datetime(2023, 1, 1), 'import', 'ingestion')])

    def test_a_date_after_the_row_is_a_redownload_and_stays_unknown(self):
        cursor = cursor_with(
            [{'id': 2, 'created_at': CREATED}, {'id': 3, 'created_at': CREATED}],
            youtube=[row(2, f'{ROOT}/Youtube/c/y.m4a', datetime(2026, 9, 1))],
        )
        result = backfill.plan(cursor, ROOT)
        self.assertEqual(result.fills, [])
        self.assertEqual((result.too_late, result.unknown), (1, 1))

    def test_a_date_within_the_hour_after_the_row_counts(self):
        cursor = cursor_with(
            [{'id': 4, 'created_at': CREATED}],
            youtube=[row(4, f'{ROOT}/Youtube/c/y.m4a', datetime(2026, 7, 4, 12, 59))],
        )
        (fill,) = backfill.plan(cursor, ROOT).fills
        self.assertEqual(fill.source, 'youtube')

    def test_the_report_has_counts_and_no_paths(self):
        cursor = cursor_with(
            [{'id': 1, 'created_at': CREATED}],
            soundcloud=[row(1, f'{ROOT}/Soundcloud/secret/x.m4a', datetime(2024, 5, 1))],
        )
        text = backfill.plan(cursor, ROOT).describe()
        self.assertIn('Tracks to fill: 1', text)
        self.assertNotIn('secret', text)


class ApplyUndoTest(unittest.TestCase):
    def test_apply_writes_the_rollback_file_then_only_null_rows_and_undo_resets_them(self):
        fills = [backfill.Arrival(1, datetime(2024, 1, 1), 'soundcloud', 'soundcloud_archive')]
        cursor = ScriptedCursor()
        conn = MagicMock()
        conn.cursor.return_value = cursor
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'ids.txt')
            self.assertEqual(backfill.apply(conn, fills, path), 1)
            with open(path, encoding='utf-8') as handle:
                self.assertEqual(handle.read(), '1\n')
            ((sql, params),) = cursor.statements_matching('UPDATE library_tracks SET arrived_at = %s')
            self.assertIn('arrived_at IS NULL', sql)
            self.assertEqual(params, (datetime(2024, 1, 1), 'soundcloud', 1))
            self.assertEqual(backfill.undo(conn, path), 1)
            self.assertEqual(cursor.statements_matching('SET arrived_at = NULL')[0][1], (1,))
