"""Audio features reach the tracks they belong to.

The unit suite mocks the cursor, so it can prove which columns a query names but
not that the two sides of a join hold the same kind of value. This bug was
exactly that: `library_track_audio_features.track_id` holds a
`library_media_files.file_path_hash`, and the readers joined it against
`library_tracks.track_uid`. Both are opaque strings, so every mocked test
passed and production reported 0% coverage on everything anyone had listened to.

These tests run the real relink against a real MariaDB.
"""
import pytest

pytestmark = pytest.mark.integration

RELINK = 'migrate_v10_audio_features_relink.sql'


@pytest.fixture()
def library(database):
    """One scanner track and one analyzer track, each with a media file."""
    with database.cursor() as cursor:
        for table in ('library_track_audio_features', 'library_media_files', 'library_tracks'):
            cursor.execute(f'DELETE FROM {table}')

        # A scanner row: track_uid is the scanner's own id, unrelated to the path.
        cursor.execute(
            'INSERT INTO library_tracks (track_uid, title) VALUES (%s, %s)',
            ('scanner-uid-1', 'Played Track'),
        )
        scanner_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO library_media_files (file_path, file_path_hash, track_id) '
            'VALUES (%s, %s, %s)',
            ('/music/played.mp3', 'hash-played', scanner_id),
        )

        # An analyzer row: track_uid *is* the path hash, which is why some rows
        # matched under the old join and hid the bug.
        cursor.execute(
            'INSERT INTO library_tracks (track_uid, title) VALUES (%s, %s)',
            ('hash-analyzed', 'Analyzed Track'),
        )
        analyzer_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO library_media_files (file_path, file_path_hash, track_id) '
            'VALUES (%s, %s, %s)',
            ('/music/analyzed.mp3', 'hash-analyzed', analyzer_id),
        )

    yield {'scanner_id': scanner_id, 'analyzer_id': analyzer_id}


def _run_relink(database):
    from tests.integration.conftest import ROOT, _split_statements

    sql = (ROOT / RELINK).read_text()
    with database.cursor() as cursor:
        for statement in _split_statements(sql):
            cursor.execute(statement)


def _internal_id(database, track_id):
    with database.cursor() as cursor:
        cursor.execute(
            'SELECT internal_track_id FROM library_track_audio_features WHERE track_id = %s',
            (track_id,),
        )
        return cursor.fetchone()['internal_track_id']


def test_a_features_row_keyed_by_path_hash_finds_its_track(database, library):
    with database.cursor() as cursor:
        cursor.execute(
            'INSERT INTO library_track_audio_features (track_id, tempo) VALUES (%s, %s)',
            ('hash-played', 150.0),
        )

    _run_relink(database)

    assert _internal_id(database, 'hash-played') == library['scanner_id']


def test_a_features_row_with_only_a_path_finds_its_track(database, library):
    with database.cursor() as cursor:
        cursor.execute(
            'INSERT INTO library_track_audio_features (track_id, file_path, tempo) '
            'VALUES (%s, %s, %s)',
            ('some-other-key', '/music/played.mp3', 150.0),
        )

    _run_relink(database)

    assert _internal_id(database, 'some-other-key') == library['scanner_id']


def test_a_wrong_internal_id_is_repaired_not_left_alone(database, library):
    """migrate_paths.py only fills NULLs, so a row pointing at the wrong track stayed wrong."""
    with database.cursor() as cursor:
        cursor.execute(
            'INSERT INTO library_track_audio_features (track_id, internal_track_id, tempo) '
            'VALUES (%s, %s, %s)',
            ('hash-played', library['analyzer_id'], 150.0),
        )

    _run_relink(database)

    assert _internal_id(database, 'hash-played') == library['scanner_id']


def test_a_row_the_library_does_not_know_is_left_unlinked(database, library):
    with database.cursor() as cursor:
        cursor.execute(
            'INSERT INTO library_track_audio_features (track_id, file_path, tempo) '
            'VALUES (%s, %s, %s)',
            ('hash-deleted', '/music/gone.mp3', 150.0),
        )

    _run_relink(database)

    assert _internal_id(database, 'hash-deleted') is None


def test_the_reader_join_reaches_a_scanner_track(database, library):
    """The join the endpoints actually use, against the track that gets played."""
    with database.cursor() as cursor:
        cursor.execute(
            'INSERT INTO library_track_audio_features (track_id, tempo) VALUES (%s, %s)',
            ('hash-played', 150.0),
        )

    _run_relink(database)

    with database.cursor() as cursor:
        cursor.execute(
            'SELECT COALESCE(af.tempo, af.bpm_tag) AS bpm FROM library_tracks t '
            'LEFT JOIN library_track_audio_features af ON af.internal_track_id = t.id '
            'WHERE t.id = %s',
            (library['scanner_id'],),
        )
        assert cursor.fetchone()['bpm'] == pytest.approx(150.0)


def test_the_old_join_key_would_have_missed_it(database, library):
    """Guards the diagnosis itself, so nobody re-derives it from scratch."""
    with database.cursor() as cursor:
        cursor.execute(
            'INSERT INTO library_track_audio_features (track_id, tempo) VALUES (%s, %s)',
            ('hash-played', 150.0),
        )

    _run_relink(database)

    with database.cursor() as cursor:
        cursor.execute(
            'SELECT af.tempo AS bpm FROM library_tracks t '
            'LEFT JOIN library_track_audio_features af ON t.track_uid = af.track_id '
            'WHERE t.id = %s',
            (library['scanner_id'],),
        )
        assert cursor.fetchone()['bpm'] is None
