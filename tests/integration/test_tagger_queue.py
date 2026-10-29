"""The tagger's queue table against a real MariaDB: binary paths, backoff and parking.

The unit tests mock the cursor, so they can only assert the SQL text. What has to be
proved here is what MariaDB makes of it: that two paths differing only in case or in an
emoji are two rows (they were one under utf8mb4_general_ci), that the backoff interval
arithmetic is accepted and actually holds a failed row back, and that the anti-join
against library_media_files -- a _ci column against a _bin one -- still runs.
See docs/bug-reports/051-a-failing-file-is-retried-every-round-forever.md.
"""

import hashlib

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def helper(db):
    """A ProcessedFilesHelper on the test database (it reads DB_* from the environment)."""
    from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper

    return ProcessedFilesHelper()


def rows(connection):
    """filepath -> (mtime, needs_rescan, rescan_reason, attempts), exactly as stored."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT filepath, mtime, needs_rescan, rescan_reason, attempts FROM tagger_processed_files')
        return {
            row['filepath']: (row['mtime'], bool(row['needs_rescan']), row['rescan_reason'], row['attempts'])
            for row in cursor.fetchall()
        }


def add_media_file(connection, path):
    with connection.cursor() as cursor:
        cursor.execute(
            'INSERT INTO library_media_files (file_path, file_path_hash) VALUES (%s, %s)',
            (path, hashlib.sha256(path.encode('utf-8')).hexdigest()),
        )


def test_the_path_column_compares_byte_for_byte(db):
    with db.cursor() as cursor:
        cursor.execute(
            'SELECT collation_name FROM information_schema.columns '
            "WHERE table_schema = DATABASE() AND table_name = 'tagger_processed_files' AND column_name = 'filepath'"
        )
        assert cursor.fetchone()['collation_name'] == 'utf8mb4_bin'


@pytest.mark.parametrize(
    ('first', 'second'),
    [
        ('/music/Youtube/Chan/Track.m4a', '/music/Youtube/Chan/track.m4a'),
        ('/music/Youtube/Chan/Cafe.m4a', '/music/Youtube/Chan/Café.m4a'),
        ('/music/Youtube/Chan/Set 😀.m4a', '/music/Youtube/Chan/Set 😃.m4a'),
    ],
)
def test_two_files_that_differ_only_in_case_accent_or_emoji_get_two_rows(db, helper, first, second):
    helper.mark_processed(first, 100.0)
    helper.mark_processed(second, 200.0)
    stored = rows(db)
    assert set(stored) == {first, second}
    assert stored[first][0] == 100.0, 'the second file no longer overwrites the first one mtime'
    assert stored[second][0] == 200.0


def test_the_case_twin_the_table_never_had_is_queued_as_new(db, helper):
    helper.mark_processed('/music/Youtube/Chan/Track.m4a', 1.0)
    add_media_file(db, '/music/Youtube/Chan/Track.m4a')
    add_media_file(db, '/music/Youtube/Chan/track.m4a')

    assert helper.queue_new_library_files(['/music/Youtube'], ('m4a',)) == 1
    assert rows(db)['/music/Youtube/Chan/track.m4a'][1:3] == (True, 'new_in_library')


def test_a_failing_file_backs_off_and_is_parked_after_five_attempts(db, helper):
    path = '/music/Youtube/Chan/Broken.m4a'
    helper.mark_paths_for_rescan([path], 'genre_decision')  # no row yet: nothing to mark
    assert helper.mark_failed(path, 55.0) == 1
    assert rows(db)[path] == (0.0, True, 'retry', 1)

    # Within its backoff the row is not handed out; once it has run out, it is.
    assert helper.pending_paths(10, reason='retry') == []
    with db.cursor() as cursor:
        cursor.execute(
            'UPDATE tagger_processed_files SET last_attempt = NOW() - INTERVAL 11 MINUTE WHERE filepath = %s', (path,)
        )
    assert helper.pending_paths(10, reason='retry') == [path]

    for expected in (2, 3, 4):
        assert helper.mark_failed(path, 55.0) == expected
    assert rows(db)[path][1] is True
    assert helper.mark_failed(path, 55.0) == 5

    assert rows(db)[path] == (55.0, False, 'failed', 5)
    summary = helper.pending_summary()
    assert summary['total'] == 0
    assert summary['failed'] == 1


def test_a_queued_file_keeps_its_reason_while_it_fails(db, helper):
    path = '/music/Youtube/Chan/Queued.m4a'
    helper.mark_processed(path, 1.0)
    helper.mark_paths_for_rescan([path], 'genre_decision')
    helper.mark_failed(path, 1.0)
    assert rows(db)[path][1:] == (True, 'genre_decision', 1)


def test_a_retag_request_takes_a_parked_file_back_with_a_fresh_count(db, helper):
    path = '/music/Youtube/Chan/Parked.m4a'
    helper.mark_failed(path, 1.0, park_after=1)
    assert rows(db)[path][1:] == (False, 'failed', 1)

    helper.mark_for_rescan(path, reason='manual')

    assert rows(db)[path][1:] == (True, 'manual', 0)
    assert helper.pending_paths(10, reason='manual') == [path]


def test_tagging_a_file_clears_its_failures(db, helper):
    path = '/music/Youtube/Chan/Fixed.m4a'
    helper.mark_failed(path, 1.0)
    helper.mark_processed(path, 2.0)
    assert rows(db)[path] == (2.0, False, None, 0)


def test_paths_under_pages_one_subtree_and_stops_at_its_edge(db, helper):
    """The `__TODO` label repair's walk (bug report 087): a primary-key range, nothing next to it."""
    inside = ['/music/EPs/A/r/1.mp3', '/music/EPs/B/r/2.mp3', '/music/EPs/__TODO/r/3.mp3']
    outside = ['/music/EPs0.mp3', '/music/EPsX/r/4.mp3', '/music/Youtube/c/5.m4a']
    for path in inside + outside:
        helper.mark_processed(path, 1.0)

    first = helper.paths_under(['/music/EPs'], '', 2)
    rest = helper.paths_under(['/music/EPs'], first[-1], 2)

    assert first + rest == sorted(inside)
    assert helper.paths_under(['/music/EPs', '/music/Youtube'], '', 10) == sorted(inside + ['/music/Youtube/c/5.m4a'])
