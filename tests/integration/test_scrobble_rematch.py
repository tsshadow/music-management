"""The rematch ladder and its worker, against a real MariaDB.

The unit suite pins the rules down (test_scrobble_matching.py) and mocks the
cursor everywhere else, so it can prove which SQL is produced but not that
MariaDB accepts it -- and this change adds an ENUM, a CASE expression built at
runtime, and four new indexed columns. This is where those fail instead.
"""

import pytest

from services.music_manager import scrobble_rematch
from services.music_manager.scrobble_matching import MatchTier

pytestmark = pytest.mark.integration


@pytest.fixture()
def library(database):
    with database.cursor() as cursor:
        for table in ('scrobble_listens', 'scrobble_unmatched_listens', 'library_tracks', 'library_artists'):
            cursor.execute(f'DELETE FROM {table}')

        cursor.execute('INSERT INTO library_artists (name) VALUES (%s)', ('Angerfist',))
        artist_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO library_tracks (track_uid, title, primary_artist_id) VALUES (%s, %s, %s)',
            ('uid-1', 'Raise Your Fist', artist_id),
        )
        track_id = cursor.lastrowid

    with database.cursor() as cursor:
        scrobble_rematch.backfill_normalized(cursor)

    yield {'artist_id': artist_id, 'track_id': track_id}


def _park(database, artist, title, username='user'):
    with database.cursor() as cursor:
        cursor.execute(
            'INSERT INTO scrobble_unmatched_listens '
            '(artist_name, track_title, listened_at, username, source) '
            'VALUES (%s, %s, NOW(), %s, %s)',
            (artist, title, username, 'listenbrainz_import'),
        )
        return cursor.lastrowid


def _find(database, artist, title):
    with database.cursor() as cursor:
        return scrobble_rematch.find_track(cursor, artist, title)


def test_backfill_fills_the_normalized_keys(database, library):
    with database.cursor() as cursor:
        cursor.execute(
            'SELECT normalized_title, normalized_base_title FROM library_tracks WHERE id = %s',
            (library['track_id'],),
        )
        row = cursor.fetchone()

    assert row['normalized_title'] == 'raise your fist'
    assert row['normalized_base_title'] == 'raise your fist'


def test_an_exact_spelling_matches_on_the_first_tier(database, library):
    found = _find(database, 'Angerfist', 'Raise Your Fist')

    assert found == (library['track_id'], MatchTier.EXACT, None)


def test_the_exact_tier_is_already_case_insensitive_here(database, library):
    """Pinned because it is the collation doing it, not the code.

    MariaDB's default utf8mb4 collation is case-insensitive, so `a.name = %s`
    folds case before the normalized tier ever gets a turn. Anyone reading the
    ladder would reasonably expect case to be the normalized tier's job; it is
    not, and a future switch to a binary collation would quietly change which
    tier answers.
    """
    found = _find(database, 'ANGERFIST', 'raise your fist')

    assert found == (library['track_id'], MatchTier.EXACT, None)


def test_punctuation_matches_on_the_normalized_tier(database, library):
    found = _find(database, 'Angerfist', 'Raise Your Fist!')

    assert found[0] == library['track_id']
    assert found[1] is MatchTier.NORMALIZED


def test_a_remix_suffix_matches_on_the_base_title_tier(database, library):
    found = _find(database, 'Angerfist', 'Raise Your Fist (Radio Edit)')

    assert found[0] == library['track_id']
    assert found[1] is MatchTier.BASE_TITLE


def test_a_typo_matches_on_the_fuzzy_tier_and_records_its_score(database, library):
    found = _find(database, 'Angerfist', 'Raise Your Fst')

    assert found[0] == library['track_id']
    assert found[1] is MatchTier.FUZZY
    assert found[2] >= scrobble_rematch.FUZZY_THRESHOLD


def test_music_the_library_does_not_have_matches_nothing(database, library):
    assert _find(database, 'Some Other Artist', 'Some Other Track') is None


def test_a_disabled_tier_is_not_tried(database, library, monkeypatch):
    monkeypatch.setenv('SCROBBLE_MATCH_TIERS', 'exact')

    assert _find(database, 'Angerfist', 'Raise Your Fist!') is None


def test_a_linked_listen_moves_out_of_the_unmatched_table(database, library):
    _park(database, 'Angerfist', 'Raise Your Fist!')

    stats = scrobble_rematch.rematch_once(database)

    assert stats['linked'] == 1
    with database.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) AS n FROM scrobble_unmatched_listens')
        assert cursor.fetchone()['n'] == 0
        cursor.execute('SELECT track_id, match_method FROM scrobble_listens')
        row = cursor.fetchone()
    assert row['track_id'] == library['track_id']
    assert row['match_method'] == 'normalized'


def test_a_miss_is_counted_and_stamped_rather_than_deleted(database, library):
    parked = _park(database, 'Nobody', 'Nothing At All')

    stats = scrobble_rematch.rematch_once(database)

    assert stats['linked'] == 0
    with database.cursor() as cursor:
        cursor.execute(
            'SELECT attempts, last_attempt_at FROM scrobble_unmatched_listens WHERE id = %s',
            (parked,),
        )
        row = cursor.fetchone()
    assert row['attempts'] == 1
    assert row['last_attempt_at'] is not None


def test_a_row_inside_its_retry_window_is_not_tried_again(database, library):
    _park(database, 'Nobody', 'Nothing At All')

    scrobble_rematch.rematch_once(database)
    second = scrobble_rematch.rematch_once(database)

    assert second['tried'] == 0


def test_the_worker_survives_a_library_with_nothing_to_do(database, library):
    stats = scrobble_rematch.rematch_once(database)

    assert stats == {'backfilled': 0, 'tried': 0, 'linked': 0}


def test_a_miss_leaves_the_moment_of_the_listen_alone(database, library):
    """docs/bug-reports/039: on MariaDB < 10.10 an undeclared DEFAULT gave listened_at
    ON UPDATE CURRENT_TIMESTAMP, so stamping a miss moved the listen to now -- and two
    listens of the same track that missed in the same second then collided on the
    UNIQUE key (username, listened_at, artist_name, track_title) with a 1062."""
    moments = ['2026-01-01 10:00:00', '2026-01-02 10:00:00']
    with database.cursor() as cursor:
        for moment in moments:
            cursor.execute(
                'INSERT INTO scrobble_unmatched_listens '
                '(artist_name, track_title, listened_at, username, source) '
                'VALUES (%s, %s, %s, %s, %s)',
                ('ISAB', 'The Secret Camo Tower', moment, 'user', 'lms'),
            )

    stats = scrobble_rematch.rematch_once(database)

    assert stats['tried'] == 2
    assert stats['linked'] == 0
    with database.cursor() as cursor:
        cursor.execute('SELECT listened_at, attempts FROM scrobble_unmatched_listens ORDER BY listened_at')
        rows = cursor.fetchall()
    assert [str(row['listened_at']) for row in rows] == moments
    assert [row['attempts'] for row in rows] == [1, 1]


def test_the_scanner_upsert_writes_both_matching_keys(database, library):
    """Bug report 137: the scanner's own statement fills the keys, a re-scan refreshes them."""
    from services.music_manager.routers.scanner import _UPSERT_TRACK
    from services.music_manager.scrobble_matching import normalized_title_keys

    def upsert(title):
        row = ('uid-137', title, 240.0, library['artist_id'], None, 'track', None)
        with database.cursor() as cursor:
            cursor.execute(_UPSERT_TRACK, (*row, *normalized_title_keys(title), *row[1:]))
            cursor.execute(
                'SELECT normalized_title, normalized_base_title FROM library_tracks WHERE track_uid = %s',
                ('uid-137',),
            )
            return cursor.fetchone()

    assert upsert('Raise Your Fist (Radio Edit)') == {
        'normalized_title': 'raise your fist radio edit',
        'normalized_base_title': 'raise your fist',
    }
    assert upsert('Raise Your Fist (Extended Mix)') == {
        'normalized_title': 'raise your fist extended mix',
        'normalized_base_title': 'raise your fist',
    }


def test_the_drain_fills_a_backlog_larger_than_one_batch(database, library):
    """Bug report 137: 500 rows an hour left a 67,331-row rescan's tail without keys for days."""
    with database.cursor() as cursor:
        for number in range(7):
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, primary_artist_id) VALUES (%s, %s, %s)',
                (f'uid-drain-{number}', f'Track {number} (Radio Edit)', library['artist_id']),
            )
        # Only one key missing still counts as missing.
        cursor.execute(
            "UPDATE library_tracks SET normalized_title = 'stale', normalized_base_title = NULL WHERE id = %s",
            (library['track_id'],),
        )

    assert scrobble_rematch.drain_normalized(database, limit=3) == 8

    with database.cursor() as cursor:
        cursor.execute(
            'SELECT COUNT(*) AS n FROM library_tracks WHERE normalized_title IS NULL OR normalized_base_title IS NULL'
        )
        assert cursor.fetchone()['n'] == 0
        cursor.execute('SELECT normalized_base_title FROM library_tracks WHERE track_uid = %s', ('uid-drain-4',))
        assert cursor.fetchone()['normalized_base_title'] == 'track 4'
