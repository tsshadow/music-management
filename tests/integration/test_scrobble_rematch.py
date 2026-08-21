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
        for table in ('scrobble_listens', 'scrobble_unmatched_listens',
                      'library_tracks', 'library_artists'):
            cursor.execute(f'DELETE FROM {table}')

        cursor.execute('INSERT INTO library_artists (name) VALUES (%s)', ('Angerfist',))
        artist_id = cursor.lastrowid
        cursor.execute(
            'INSERT INTO library_tracks (track_uid, title, primary_artist_id) '
            'VALUES (%s, %s, %s)',
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
