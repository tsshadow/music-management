"""Covers scripts/migrate_stars_to_ratings.py.

The migration runs once, against a live library, and there is no undo. What has to hold:
an explicit rating is never overwritten, a star without a rating becomes rating 5, and a
second run changes nothing.
"""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_stars_to_ratings.py"

spec = importlib.util.spec_from_file_location("migrate_stars_to_ratings", SCRIPT)
assert spec is not None and spec.loader is not None
migrate_stars_to_ratings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate_stars_to_ratings)


ENTITY_TABLES = (
    ("starred_track", "rated_track", "track_id"),
    ("starred_release", "rated_release", "release_id"),
    ("starred_artist", "rated_artist", "artist_id"),
)


def build_lms_database(path):
    """A stand-in for the tables Wt::Dbo creates in the real LMS database."""
    conn = sqlite3.connect(path)
    for starred, rated, foreign_key in ENTITY_TABLES:
        conn.execute(
            f"CREATE TABLE {starred} ("
            f"id INTEGER PRIMARY KEY, {foreign_key} INTEGER, user_id INTEGER, "
            "backend INTEGER, sync_state INTEGER, date_time TEXT)"
        )
        conn.execute(
            f"CREATE TABLE {rated} ("
            f"id INTEGER PRIMARY KEY, {foreign_key} INTEGER, user_id INTEGER, "
            "rating INTEGER, last_updated TEXT)"
        )
    conn.commit()
    return conn


def star(conn, table, foreign_key, object_id, user_id, date_time="2026-01-01T12:00:00"):
    conn.execute(
        f"INSERT INTO {table} ({foreign_key}, user_id, backend, sync_state, date_time) VALUES (?, ?, 2, 0, ?)",
        (object_id, user_id, date_time),
    )
    conn.commit()


def rate(conn, table, foreign_key, object_id, user_id, rating):
    conn.execute(
        f"INSERT INTO {table} ({foreign_key}, user_id, rating, last_updated) VALUES (?, ?, ?, ?)",
        (object_id, user_id, rating, "2026-02-02T09:00:00"),
    )
    conn.commit()


def ratings_in(conn, table, foreign_key):
    return {(row[0], row[1]): row[2] for row in conn.execute(f"SELECT {foreign_key}, user_id, rating FROM {table}")}


@pytest.fixture(name="conn")
def fixture_conn(tmp_path):
    conn = build_lms_database(tmp_path / "lms.db")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def run(conn, dry_run=False):
    report, export = migrate_stars_to_ratings.migrate(conn, dry_run=dry_run)
    conn.commit()
    return report, export


def test_a_star_without_a_rating_becomes_rating_five(conn):
    star(conn, "starred_track", "track_id", object_id=10, user_id=1)

    run(conn)

    assert ratings_in(conn, "rated_track", "track_id") == {(10, 1): 5}


def test_an_explicit_rating_is_never_overwritten(conn):
    star(conn, "starred_track", "track_id", object_id=10, user_id=1)
    rate(conn, "rated_track", "track_id", object_id=10, user_id=1, rating=2)

    report, _ = run(conn)

    assert ratings_in(conn, "rated_track", "track_id") == {(10, 1): 2}
    assert report.entities[0].kept_explicit_rating == 1
    assert report.entities[0].rated == 0


def test_the_star_timestamp_is_carried_into_the_rating(conn):
    star(conn, "starred_track", "track_id", object_id=10, user_id=1, date_time="2025-07-04T08:30:00")

    run(conn)

    last_updated = conn.execute("SELECT last_updated FROM rated_track").fetchone()[0]
    assert last_updated == "2025-07-04T08:30:00"


def test_releases_and_artists_are_migrated_too(conn):
    star(conn, "starred_release", "release_id", object_id=20, user_id=1)
    star(conn, "starred_artist", "artist_id", object_id=30, user_id=1)

    run(conn)

    assert ratings_in(conn, "rated_release", "release_id") == {(20, 1): 5}
    assert ratings_in(conn, "rated_artist", "artist_id") == {(30, 1): 5}


def test_the_same_object_starred_by_two_users_gets_two_ratings(conn):
    star(conn, "starred_track", "track_id", object_id=10, user_id=1)
    star(conn, "starred_track", "track_id", object_id=10, user_id=2)

    run(conn)

    assert ratings_in(conn, "rated_track", "track_id") == {(10, 1): 5, (10, 2): 5}


def test_a_second_run_changes_nothing(conn):
    star(conn, "starred_track", "track_id", object_id=10, user_id=1)
    star(conn, "starred_release", "release_id", object_id=20, user_id=1)

    run(conn)
    first = ratings_in(conn, "rated_track", "track_id")

    second_report, _ = run(conn)

    assert ratings_in(conn, "rated_track", "track_id") == first
    assert conn.execute("SELECT COUNT(*) FROM rated_track").fetchone()[0] == 1
    assert second_report.entities[0].rated == 0
    assert second_report.entities[0].kept_explicit_rating == 1


def test_a_dry_run_writes_nothing_but_still_reports(conn):
    star(conn, "starred_track", "track_id", object_id=10, user_id=1)

    report, export = migrate_stars_to_ratings.migrate(conn, dry_run=True)

    assert ratings_in(conn, "rated_track", "track_id") == {}
    assert report.entities[0].rated == 1
    assert len(export) == 1


def test_the_starred_rows_are_left_in_place(conn):
    star(conn, "starred_track", "track_id", object_id=10, user_id=1)

    run(conn)

    assert conn.execute("SELECT COUNT(*) FROM starred_track").fetchone()[0] == 1


def test_the_export_records_every_star_including_the_untouched_ones(conn):
    star(conn, "starred_track", "track_id", object_id=10, user_id=1)
    star(conn, "starred_track", "track_id", object_id=11, user_id=1)
    rate(conn, "rated_track", "track_id", object_id=11, user_id=1, rating=3)

    _, export = run(conn)

    by_object = {entry["object_id"]: entry for entry in export}
    assert by_object[10]["imported_as_rating5"] is True
    assert by_object[10]["had_explicit_rating"] is False
    assert by_object[11]["imported_as_rating5"] is False
    assert by_object[11]["had_explicit_rating"] is True
    # The export has to be writable as JSON, since that is the fallback copy.
    json.dumps(export, default=str)


def test_a_database_without_the_lms_tables_is_rejected(tmp_path):
    conn = sqlite3.connect(tmp_path / "empty.db")
    conn.row_factory = sqlite3.Row
    try:
        with pytest.raises(migrate_stars_to_ratings.SchemaError):
            migrate_stars_to_ratings.migrate(conn, dry_run=True)
    finally:
        conn.close()
