"""The feeds' song collapse against a real MariaDB (bug report 096).

The unit suite (test_feeds_build.py, test_feeds_queries.py) pins the collapse down
over scripted rows; this proves MariaDB accepts the song-level `heard` and `rating`
expressions and the canonical fetch, and that they answer per work.
"""

from dataclasses import replace
from datetime import datetime

import pytest

from services.music_manager.feeds import build
from services.music_manager.feeds.policy import POLICIES
from tests.integration.conftest import run_sql

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 12, 0, 0)


def _add_track(db, uid, title, path, work_id, release_date):
    """One track with one file, in `work_id`, dated `release_date`."""
    run_sql(
        db,
        'INSERT INTO library_tracks (track_uid, title, duration_secs, work_id, release_date) VALUES (%s, %s, 300, %s, %s)',
        (uid, title, work_id, release_date),
    )
    track_id = run_sql(db, 'SELECT id FROM library_tracks WHERE track_uid = %s', (uid,))[0]['id']
    run_sql(
        db,
        'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, SHA2(%s, 256), %s)',
        (path, path, track_id),
    )
    return track_id


@pytest.fixture
def one_song_two_versions(db):
    """ERABREAK - Elevate: an official release outside the radar window, a rip inside it."""
    run_sql(db, "INSERT INTO library_works (work_key, title) VALUES ('erabreak|elevate', 'Elevate')")
    work_id = run_sql(db, "SELECT id FROM library_works WHERE work_key = 'erabreak|elevate'")[0]['id']
    official = _add_track(db, 'uid-official', 'Elevate', '/mnt/music/Labels/Elevate.flac', work_id, '2026-08-01')
    rip = _add_track(db, 'uid-rip', 'Elevate', '/mnt/music/soundcloud/Elevate.mp3', work_id, '2026-09-24')
    run_sql(db, 'UPDATE library_works SET canonical_track_id = %s WHERE id = %s', (official, work_id))
    return {'official': official, 'rip': rip, 'work_id': work_id}


def test_the_radar_plays_the_canonical_of_a_song_only_its_rip_qualified_for(db, one_song_two_versions):
    candidates = build._load_candidates(db, 'user', POLICIES['release-radar'], NOW)
    assert [c['id'] for c in candidates] == [one_song_two_versions['official']]
    assert candidates[0]['file_path'] == '/mnt/music/Labels/Elevate.flac'
    assert candidates[0]['release_date'] == '2026-09-24'
    assert candidates[0]['heard'] is False


def test_a_listen_and_a_rating_of_any_version_are_the_song_s(db, one_song_two_versions):
    run_sql(
        db,
        "INSERT INTO scrobble_listens (track_id, username, listened_at) VALUES (%s, 'user', '2026-09-20 10:00:00')",
        (one_song_two_versions['official'],),
    )
    run_sql(
        db,
        "INSERT INTO rating_tracks (entity_type, entity_id, username, rating) VALUES ('track', 'uid-rip', 'user', 5)",
    )
    candidates = build._load_candidates(db, 'user', POLICIES['release-radar'], NOW)
    assert len(candidates) == 1
    assert candidates[0]['heard'] is True
    assert candidates[0]['rating'] == 5


def test_the_unheard_pool_drops_a_rip_of_a_song_heard_in_another_version(db, one_song_two_versions):
    run_sql(
        db,
        "INSERT INTO scrobble_listens (track_id, username, listened_at) VALUES (%s, 'user', '2026-09-20 10:00:00')",
        (one_song_two_versions['official'],),
    )
    unheard_only = replace(
        POLICIES['daily-mix-mid'], pools=frozenset({'unheard'}), hardness_band=None, release_window_days=None
    )
    assert build._load_candidates(db, 'user', unheard_only, NOW) == []


def test_a_rating_on_the_canonical_is_the_song_s_even_when_a_version_has_a_higher_one(db, one_song_two_versions):
    """A rating given from a list is written to the canonical; it has to be what shows."""
    run_sql(
        db,
        "INSERT INTO rating_tracks (entity_type, entity_id, username, rating) VALUES "
        "('track', 'uid-rip', 'user', 5), ('track', 'uid-official', 'user', 3)",
    )
    candidates = build._load_candidates(db, 'user', POLICIES['release-radar'], NOW)
    assert candidates[0]['rating'] == 3
