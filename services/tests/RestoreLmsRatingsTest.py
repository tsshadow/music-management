"""Covers scripts/restore_lms_ratings.py.

The script writes into a live LMS database and there is no undo, so what has to hold:
an existing rating is never touched, the music-management mirror beats the file tag,
paths are matched across both library roots, and a second run changes nothing.
"""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore_lms_ratings.py"

spec = importlib.util.spec_from_file_location("restore_lms_ratings", SCRIPT)
restore_lms_ratings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore_lms_ratings)


def build_lms_database(path):
    """A stand-in for the tables Wt::Dbo creates in the real LMS database."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE user (id INTEGER PRIMARY KEY, login_name TEXT);
        CREATE TABLE track (id INTEGER PRIMARY KEY, absolute_file_path TEXT);
        CREATE TABLE rated_track (
            id INTEGER PRIMARY KEY AUTOINCREMENT, version INTEGER NOT NULL,
            rating INTEGER NOT NULL, last_updated TEXT, track_id INTEGER, user_id INTEGER);
        CREATE TABLE cluster_type (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE cluster (id INTEGER PRIMARY KEY, name TEXT, cluster_type_id INTEGER);
        CREATE TABLE track_cluster (track_id INTEGER, cluster_id INTEGER);
        """
    )
    conn.execute("INSERT INTO user (id, login_name) VALUES (1, 'user')")
    for track_id, name in (
        (10, "/music/Soundcloud/a.mp3"),
        (11, "/music/Youtube/b.m4a"),
        (12, "/music/EPs/c.flac"),
        (13, "/music/EPs/d.flac"),
    ):
        conn.execute("INSERT INTO track (id, absolute_file_path) VALUES (?, ?)", (track_id, name))
    conn.execute("INSERT INTO cluster_type (id, name) VALUES (103, 'RATING')")
    for cluster_id, name in ((1, "80"), (2, "100"), (3, "Clean")):
        conn.execute("INSERT INTO cluster (id, name, cluster_type_id) VALUES (?, ?, 103)", (cluster_id, name))
    conn.commit()
    return conn


def tag(conn, track_id, cluster_id):
    conn.execute("INSERT INTO track_cluster (track_id, cluster_id) VALUES (?, ?)", (track_id, cluster_id))
    conn.commit()


def muma_entry(path, rating, username="user", updated_at="2026-07-20T10:00:00"):
    return {"username": username, "rating": rating, "path": path, "updated_at": updated_at}


def run(tmp_path, db_path, entries, extra=()):
    muma_json = tmp_path / "muma.json"
    muma_json.write_text(json.dumps(entries), encoding="utf-8")
    argv = [
        "restore",
        "--database",
        str(db_path),
        "--muma-json",
        str(muma_json),
        "--user",
        "user",
        "--export",
        str(tmp_path / "before.json"),
        "--apply",
        *extra,
    ]
    return restore_lms_ratings.main(argv)


def ratings(conn, user_id=1):
    return dict(conn.execute("SELECT track_id, rating FROM rated_track WHERE user_id = ?", (user_id,)))


@pytest.fixture
def lms_db(tmp_path):
    path = tmp_path / "lms.db"
    conn = build_lms_database(path)
    yield path, conn
    conn.close()


def test_restores_from_both_sources(lms_db, tmp_path):
    path, conn = lms_db
    tag(conn, 12, 1)  # /music/EPs/c.flac -> 4 stars from its RATING tag
    entries = [muma_entry("/mnt/music/Soundcloud/a.mp3", 5)]

    assert run(tmp_path, path, entries) == 0

    assert ratings(conn) == {10: 5, 12: 4}


def test_bridges_the_two_library_roots(lms_db, tmp_path):
    """music-management reports /mnt/music/..., LMS stores /music/... for the same file."""
    path, conn = lms_db
    run(tmp_path, path, [muma_entry("/mnt/music/Youtube/b.m4a", 3)], extra=["--no-tags"])

    assert ratings(conn) == {11: 3}


def test_never_touches_an_existing_rating(lms_db, tmp_path):
    path, conn = lms_db
    conn.execute(
        "INSERT INTO rated_track (version, rating, last_updated, track_id, user_id)"
        " VALUES (0, 2, '2026-08-15T00:17:31.000', 10, 1)"
    )
    conn.commit()
    tag(conn, 10, 2)

    run(tmp_path, path, [muma_entry("/mnt/music/Soundcloud/a.mp3", 5)])

    assert ratings(conn) == {10: 2}


def test_mirror_beats_the_file_tag(lms_db, tmp_path):
    path, conn = lms_db
    tag(conn, 12, 1)  # tag says 4
    run(tmp_path, path, [muma_entry("/mnt/music/EPs/c.flac", 5)])

    assert ratings(conn) == {12: 5}


def test_skips_tag_values_that_are_not_ratings(lms_db, tmp_path):
    path, conn = lms_db
    tag(conn, 13, 3)  # "Clean"
    run(tmp_path, path, [])

    assert ratings(conn) == {}


def test_secondary_username_only_fills_gaps(lms_db, tmp_path):
    path, conn = lms_db
    entries = [
        muma_entry("/mnt/music/Soundcloud/a.mp3", 5),
        muma_entry("/mnt/music/Soundcloud/a.mp3", 1, username="lms_user"),
        muma_entry("/mnt/music/Youtube/b.m4a", 2, username="lms_user"),
    ]
    run(tmp_path, path, entries, extra=["--no-tags", "--also-user", "lms_user"])

    assert ratings(conn) == {10: 5, 11: 2}


def test_ignores_unknown_usernames(lms_db, tmp_path):
    path, conn = lms_db
    run(tmp_path, path, [muma_entry("/mnt/music/Soundcloud/a.mp3", 4, username="someone-else")], extra=["--no-tags"])

    assert ratings(conn) == {}


def test_unmatched_paths_are_counted_not_inserted(lms_db, tmp_path):
    path, conn = lms_db
    run(tmp_path, path, [muma_entry("/mnt/music/gone/missing.mp3", 4)], extra=["--no-tags"])

    assert ratings(conn) == {}


def test_second_run_is_a_no_op(lms_db, tmp_path):
    path, conn = lms_db
    tag(conn, 12, 1)
    entries = [muma_entry("/mnt/music/Soundcloud/a.mp3", 5)]
    run(tmp_path, path, entries)
    first = ratings(conn)
    run(tmp_path, path, entries)

    assert ratings(conn) == first
    assert conn.execute("SELECT count(*) FROM rated_track").fetchone()[0] == len(first)


def test_dry_run_writes_nothing(lms_db, tmp_path):
    path, conn = lms_db
    muma_json = tmp_path / "muma.json"
    muma_json.write_text(json.dumps([muma_entry("/mnt/music/Soundcloud/a.mp3", 5)]), encoding="utf-8")
    restore_lms_ratings.main(["restore", "--database", str(path), "--muma-json", str(muma_json), "--user", "user"])

    assert ratings(conn) == {}


def test_exports_the_previous_rows_before_writing(lms_db, tmp_path):
    path, conn = lms_db
    conn.execute(
        "INSERT INTO rated_track (version, rating, last_updated, track_id, user_id)"
        " VALUES (0, 2, '2026-08-15T00:17:31.000', 11, 1)"
    )
    conn.commit()
    run(tmp_path, path, [muma_entry("/mnt/music/Soundcloud/a.mp3", 5)], extra=["--no-tags"])

    exported = json.loads((tmp_path / "before.json").read_text(encoding="utf-8"))
    assert [(row["track_id"], row["rating"]) for row in exported] == [(11, 2)]


def test_rejects_a_database_that_is_not_lms(tmp_path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    with pytest.raises(restore_lms_ratings.SchemaError):
        restore_lms_ratings.main(["restore", "--database", str(path), "--user", "user"])


def test_rejects_an_unknown_user(lms_db):
    path, _ = lms_db
    with pytest.raises(restore_lms_ratings.SchemaError):
        restore_lms_ratings.main(["restore", "--database", str(path), "--user", "nobody"])


def test_export_lms_writes_paths_and_ratings(lms_db, tmp_path):
    path, conn = lms_db
    conn.execute(
        "INSERT INTO rated_track (version, rating, last_updated, track_id, user_id)"
        " VALUES (0, 4, '2026-08-15T00:17:31.000', 12, 1)"
    )
    conn.commit()
    out = tmp_path / "lms.json"
    restore_lms_ratings.main(["export-lms", "--database", str(path), "--user", "user", "--out", str(out)])

    assert json.loads(out.read_text(encoding="utf-8")) == [
        {
            "username": "user",
            "rating": 4,
            "path": "/music/EPs/c.flac",
            "updated_at": "2026-08-15T00:17:31.000",
        }
    ]


class FakeCursor:
    """Enough of a PyMySQL cursor to drive import-muma."""

    def __init__(self, resolvable):
        self.resolvable = resolvable
        self.executed = []
        self.upserted = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if "library_media_files" in sql:
            match = next((p for p in params if p in self.resolvable), None)
            self._row = {"track_uid": self.resolvable[match]} if match else None
        elif "count(*)" in sql:
            self._row = {"n": len(self.upserted)}

    def executemany(self, sql, rows):
        self.executed.append((sql, rows))
        self.upserted.extend(rows)

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        pass


@pytest.fixture
def fake_muma(monkeypatch):
    """Stands in for services.music_manager.database, which import-muma imports lazily."""
    import sys
    import types

    cursor = FakeCursor({"/mnt/music/EPs/c.flac": "uid-c"})
    connection = FakeConnection(cursor)
    module = types.ModuleType("services.music_manager.database")
    module.get_db_connection = lambda: connection
    monkeypatch.setitem(sys.modules, "services.music_manager.database", module)
    return cursor, connection


def test_import_muma_upserts_resolved_paths(fake_muma, tmp_path):
    cursor, connection = fake_muma
    source = tmp_path / "lms.json"
    source.write_text(
        json.dumps(
            [
                {"username": "user", "rating": 4, "path": "/music/EPs/c.flac", "updated_at": None},
                {"username": "user", "rating": 5, "path": "/music/gone/missing.mp3", "updated_at": None},
            ]
        ),
        encoding="utf-8",
    )
    restore_lms_ratings.main(["import-muma", "--json", str(source), "--apply"])

    assert cursor.upserted == [("uid-c", "user", 4)]
    assert connection.committed
    upsert_sql = next(sql for sql, _ in cursor.executed if "INSERT INTO rating_tracks" in sql)
    assert "ON DUPLICATE KEY UPDATE" in upsert_sql


def test_import_muma_dry_run_writes_nothing(fake_muma, tmp_path):
    cursor, connection = fake_muma
    source = tmp_path / "lms.json"
    source.write_text(
        json.dumps([{"username": "user", "rating": 4, "path": "/music/EPs/c.flac", "updated_at": None}]),
        encoding="utf-8",
    )
    restore_lms_ratings.main(["import-muma", "--json", str(source)])

    assert cursor.upserted == []
    assert not connection.committed


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/music/a/b.mp3", ["/music/a/b.mp3", "/mnt/music/a/b.mp3", "a/b.mp3"]),
        ("/mnt/music/a/b.mp3", ["/mnt/music/a/b.mp3", "/music/a/b.mp3", "a/b.mp3"]),
        ("a/b.mp3", ["a/b.mp3", "/mnt/music/a/b.mp3", "/music/a/b.mp3"]),
    ],
)
def test_candidate_paths(path, expected):
    assert restore_lms_ratings.candidate_paths(path) == expected


def test_candidate_paths_is_the_shared_copy():
    """One implementation of the path spellings: the webhook and this script cannot drift."""
    from services.music_manager import library_paths

    assert restore_lms_ratings.candidate_paths is library_paths.candidate_paths
