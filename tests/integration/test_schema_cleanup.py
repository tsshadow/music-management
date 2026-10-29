"""tools/schema_cleanup_2026_11.py against a real MariaDB.

A fresh database gets the parts production has and the declaration left out: the six
tables, the six columns, the CASCADE foreign key on scrobble_listens and no foreign key on
rules_genres. The cleanup must bring it back to the fresh shape, and a second run must find
nothing to do.
"""

import pymysql
import pytest

from services.common import schema_reconcile
from tests.integration import schema_sources
from tests.integration.conftest import _connect, _unavailable
from tools import schema_cleanup_2026_11 as cleanup

pytestmark = pytest.mark.integration

LIVE = 'muma_test_cleanup_live'

PRODUCTION_ONLY = (
    'CREATE TABLE downloads_soundcloud_queue (id INT AUTO_INCREMENT PRIMARY KEY, url VARCHAR(767) NOT NULL)',
    'CREATE TABLE downloads_youtube_queue (id INT AUTO_INCREMENT PRIMARY KEY, url VARCHAR(767) NOT NULL)',
    'CREATE TABLE rules_genres_new (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL)',
    'CREATE TABLE rules_genres_old (genre VARCHAR(255) NOT NULL)',
    'CREATE TABLE library_broken_songs (id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY, path TEXT NOT NULL)',
    'CREATE TABLE library_broken_song_artist_lookup (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, raw_name TEXT)',
    'ALTER TABLE artist_external_ids ADD COLUMN confidence TINYINT',
    "ALTER TABLE downloads_soundcloud_accounts ADD COLUMN account_type VARCHAR(20) DEFAULT 'unknown',"
    ' ADD COLUMN image_enrichment_hint TINYINT DEFAULT 0, ADD COLUMN linked_artist_id INT',
    "ALTER TABLE library_artist_images ADD COLUMN status VARCHAR(50) DEFAULT 'active', ADD COLUMN error_message TEXT",
    'ALTER TABLE scrobble_listens DROP FOREIGN KEY scrobble_listens_ibfk_1',
    'ALTER TABLE scrobble_listens ADD CONSTRAINT scrobble_listens_ibfk_1 FOREIGN KEY (track_id)'
    ' REFERENCES library_tracks (id) ON DELETE CASCADE',
    'ALTER TABLE rules_genres DROP FOREIGN KEY fk_rules_genres_canonical',
)


@pytest.fixture(name='live')
def live_fixture(database):
    """A fresh database, dropped afterwards."""
    try:
        with database.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS `{LIVE}`')
            cursor.execute(f'CREATE DATABASE `{LIVE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
    except pymysql.err.MySQLError as exc:
        _unavailable(f'cannot create the scratch database {LIVE} ({exc}); see scripts/test/db-integration.sh')
    connection = _connect(database=LIVE)
    schema_sources.build_fresh(connection, LIVE)
    yield connection
    connection.close()
    with database.cursor() as cursor:
        cursor.execute(f'DROP DATABASE IF EXISTS `{LIVE}`')


def _run(connection, *statements):
    with connection.cursor() as cursor:
        cursor.execute(f'USE `{LIVE}`')
        for statement in statements:
            cursor.execute(statement)
    connection.commit()


def _snapshot(connection):
    with connection.cursor() as cursor:
        return schema_reconcile.snapshot_lines(schema_reconcile.read_schema(cursor, LIVE))


def _plan(connection):
    with connection.cursor() as cursor:
        return cleanup.plan(cursor, LIVE)


def test_a_fresh_database_needs_no_cleanup(live):
    assert _plan(live) == []


def test_the_production_leftovers_are_removed_and_a_second_run_does_nothing(live):
    fresh = _snapshot(live)
    _run(live, *PRODUCTION_ONLY)
    # A canonical id that points at no genre: the foreign key cannot be added over it.
    _run(
        live,
        "INSERT INTO rules_genres (id, name, normalized_name, canonical_id) VALUES (9001, 'Orphan', 'orphan', 9999)",
    )

    cleanup.apply(live, _plan(live), lock_wait_seconds=5)

    assert _snapshot(live) == fresh
    assert _plan(live) == []
    with live.cursor() as cursor:
        cursor.execute(f'SELECT canonical_id FROM `{LIVE}`.rules_genres WHERE id = 9001')
        assert cursor.fetchone()['canonical_id'] is None


def test_a_listen_outlives_its_track(live):
    _run(live, *PRODUCTION_ONLY)
    cleanup.apply(live, _plan(live), lock_wait_seconds=5)
    _run(
        live,
        "INSERT INTO library_tracks (id, title) VALUES (7, 'Track')",
        "INSERT INTO scrobble_listens (username, track_id, listened_at) VALUES ('user', 7, NOW())",
        'DELETE FROM library_tracks WHERE id = 7',
    )
    with live.cursor() as cursor:
        cursor.execute(f'SELECT track_id FROM `{LIVE}`.scrobble_listens')
        assert [row['track_id'] for row in cursor.fetchall()] == [None]
