"""The SoundCloud date repair's SQL against a real MariaDB (bug report 088).

The unit test mocks the cursor. What has to be proved here: MariaDB accepts the
JSON_VALUE/REGEXP candidate query and returns only rows inside the window with a full
upload date, and the queue upsert both creates a missing row and re-queues an existing one
with the dedicated reason and a reset backoff.
"""

import json

import pytest

pytestmark = pytest.mark.integration


def add_archive(connection, video_id, path, added_at, upload_date):
    """One downloads_soundcloud_archive row with a pruned info dict."""
    info = json.dumps({'id': video_id, 'upload_date': upload_date}) if upload_date is not None else None
    with connection.cursor() as cursor:
        cursor.execute(
            'INSERT INTO downloads_soundcloud_archive (account, video_id, filename, url, title, added_at, info_json) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            ('acc', video_id, path, 'https://soundcloud.com/x', 't', added_at, info),
        )
    connection.commit()


def test_candidates_are_the_window_rows_with_a_full_upload_date(db):
    from services.tagger import soundcloud_date_repair as repair

    add_archive(db, '1', '/m/before.mp3', '2026-09-21 12:00:00', '20260920')
    add_archive(db, '2', '/m/after.mp3', '2026-09-23 12:00:00', '20260831')
    add_archive(db, '3', '/m/no-date.mp3', '2026-09-23 12:00:00', None)
    add_archive(db, '4', '/m/partial.mp3', '2026-09-23 12:00:00', '2026')

    with db.cursor() as cursor:
        cursor.execute(repair.CANDIDATES_SQL, (repair.DEFAULT_SINCE,))
        rows = [tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in cursor.fetchall()]

    assert rows == [('/m/after.mp3', '20260831')]


def test_the_queue_upsert_creates_and_requeues(db):
    from services.tagger import soundcloud_date_repair as repair

    with db.cursor() as cursor:
        cursor.execute(
            'INSERT INTO tagger_processed_files (filepath, mtime, needs_rescan, rescan_reason, attempts) '
            "VALUES ('/m/known.mp3', 123.0, FALSE, 'failed', 5)"
        )
        repair.queue(cursor, ['/m/known.mp3', '/m/new.mp3'])
    db.commit()

    with db.cursor() as cursor:
        cursor.execute('SELECT filepath, needs_rescan, rescan_reason, attempts FROM tagger_processed_files')
        stored = {
            row['filepath']: (bool(row['needs_rescan']), row['rescan_reason'], row['attempts'])
            for row in cursor.fetchall()
        }

    assert stored == {
        '/m/known.mp3': (True, 'soundcloud_full_date', 0),
        '/m/new.mp3': (True, 'soundcloud_full_date', 0),
    }
