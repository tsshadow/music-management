"""The false-merge guard against a real MariaDB (bug report 098).

The unit suite pins the verdict and the statements (test_song_work_audit.py,
test_song_work_split.py); this proves MariaDB accepts the nested report query and the
split writes, and that a pass splits a misparsed series while leaving a real song whole.
"""

import pytest

from services.music_manager import song_version_worker

pytestmark = pytest.mark.integration


@pytest.fixture()
def library(database):
    """Thirteen different songs misparsed as "NEXT" by Q-Dance, plus one real two-cut song."""
    with database.cursor() as cursor:
        for table in (
            'library_track_labels',
            'library_media_files',
            'library_tracks',
            'library_works',
            'library_artists',
        ):
            cursor.execute(f'DELETE FROM {table}')
        cursor.execute('INSERT INTO library_artists (name) VALUES (%s)', ('Q-Dance',))
        qdance = cursor.lastrowid
        cursor.execute('INSERT INTO library_artists (name) VALUES (%s)', ('Dj Test',))
        dj = cursor.lastrowid

        series = []
        for index in range(13):
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id) VALUES (%s, %s, %s, %s)',
                (f'uid-next-{index}', 'NEXT', 120.0 + 10 * index, qdance),
            )
            series.append(cursor.lastrowid)

        song = []
        for uid, title, duration in (
            ('uid-lost', 'Lost On You', 210.0),
            ('uid-lost-vis', 'Lost On You - Official Hardcore Visualizer', 214.0),
        ):
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id) VALUES (%s, %s, %s, %s)',
                (uid, title, duration, dj),
            )
            song.append(cursor.lastrowid)
    database.commit()
    return {'series': series, 'song': song}


def _rows(database, track_ids):
    with database.cursor() as cursor:
        placeholders = ','.join(['%s'] * len(track_ids))
        cursor.execute(
            f'SELECT t.id, t.work_id, t.work_locked, w.work_key FROM library_tracks t '
            f'JOIN library_works w ON w.id = t.work_id WHERE t.id IN ({placeholders})',
            tuple(track_ids),
        )
        return cursor.fetchall()


def test_a_pass_splits_the_series_and_keeps_the_song_whole(database, library):
    song_version_worker.group_once(database)

    series = _rows(database, library['series'])
    assert len({row['work_id'] for row in series}) == 13
    assert all(row['work_locked'] == 1 and row['work_key'].startswith('split:') for row in series)

    song = _rows(database, library['song'])
    assert {row['work_key'] for row in song} == {'dj test:::lost on you'}
    assert all(row['work_locked'] == 0 for row in song)


def test_a_second_pass_changes_nothing(database, library):
    song_version_worker.group_once(database)
    before = _rows(database, library['series'] + library['song'])
    song_version_worker.group_once(database)
    assert _rows(database, library['series'] + library['song']) == before


def test_the_report_query_runs_and_finds_the_series(database, library):
    # Group without the guard, so the series sits in one work for the report to find.
    with database.cursor() as cursor:
        song_version_worker.assign_works(cursor)
        found = song_version_worker.find_suspicious_works(cursor)
    database.commit()
    assert [(work['work_key'], work['verdict'], work['members']) for work in found] == [('q dance:::next', 'split', 13)]
