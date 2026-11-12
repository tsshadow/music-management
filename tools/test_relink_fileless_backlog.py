"""tools/relink_fileless_backlog.py against SQLite: the dry run writes nothing, the apply relinks,
purges and keeps the right tracks behind a backup, and the rollback puts every row back.
"""

# pylint: disable=redefined-outer-name  # pytest fixtures
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

from tools import relink_fileless_backlog as backlog

TABLES = (
    'library_tracks',
    'library_media_files',
    'rating_tracks',
    'scrobble_listens',
    'library_works',
    'library_track_audio_features',
    'library_track_ml_labels',
    'library_track_artists',
    'library_track_genres',
    'library_track_labels',
    'library_track_channels',
    'library_track_effective_bpm',
    'library_track_bpm',
    'library_track_bpm_manual',
)

SCHEMA = """
CREATE TABLE library_tracks (id INTEGER PRIMARY KEY, track_uid TEXT UNIQUE, title TEXT, duration_secs REAL,
    primary_artist_id INTEGER, work_id INTEGER, created_at TEXT);
CREATE TABLE library_media_files (id INTEGER PRIMARY KEY, file_path TEXT, track_id INTEGER);
CREATE TABLE rating_tracks (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id TEXT, username TEXT, rating INTEGER,
    updated_at TEXT, UNIQUE (entity_type, entity_id, username));
CREATE TABLE scrobble_listens (id INTEGER PRIMARY KEY, track_id INTEGER, listened_at TEXT, username TEXT,
    UNIQUE (username, listened_at, track_id));
CREATE TABLE library_works (id INTEGER PRIMARY KEY, canonical_track_id INTEGER, pinned_track_id INTEGER,
    previous_canonical_track_id INTEGER);
CREATE TABLE library_track_audio_features (id INTEGER PRIMARY KEY, internal_track_id INTEGER);
CREATE TABLE library_track_ml_labels (id INTEGER PRIMARY KEY, track_id TEXT, internal_track_id INTEGER,
    ml_review_status TEXT, approved_for_training INTEGER, updated_at TEXT);
CREATE TABLE library_track_artists (track_id INTEGER, artist_id INTEGER);
CREATE TABLE library_track_genres (track_id INTEGER, genre_id INTEGER);
CREATE TABLE library_track_labels (track_id INTEGER, label_id INTEGER);
CREATE TABLE library_track_channels (track_id INTEGER, channel_id INTEGER);
CREATE TABLE library_track_effective_bpm (track_id INTEGER PRIMARY KEY, bpm REAL);
CREATE TABLE library_track_bpm (track_uid TEXT PRIMARY KEY, bpm REAL);
CREATE TABLE library_track_bpm_manual (track_uid TEXT PRIMARY KEY, bpm REAL);
"""


class _Cursor:
    """pymysql's DictCursor surface over SQLite: %s placeholders, UPDATE IGNORE, FOR UPDATE."""

    def __init__(self, connection):
        self._cursor = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def execute(self, sql, params=()):
        sql = sql.replace('%s', '?').replace('UPDATE IGNORE', 'UPDATE OR IGNORE').replace(' FOR UPDATE', '')
        self._cursor.execute(sql, tuple(params))
        return self._cursor.rowcount

    def _row(self, row):
        return None if row is None else {d[0]: v for d, v in zip(self._cursor.description, row, strict=True)}

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self._cursor.fetchall()]


class _Connection:
    """The pymysql connection's surface: cursor(), begin/commit/rollback, close."""

    def __init__(self, path):
        self._connection = sqlite3.connect(path)

    def cursor(self):
        return _Cursor(self._connection)

    def begin(self):
        pass

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class Db:
    """A muma database with a handful of tracks, files and history."""

    def __init__(self, path: Path):
        self.path = path
        connection = sqlite3.connect(path)
        connection.executescript(SCHEMA)
        connection.close()

    def sql(self, statement: str, params=()):
        connection = sqlite3.connect(self.path)
        try:
            rows = connection.execute(statement, params).fetchall()
            connection.commit()
            return rows
        finally:
            connection.close()

    def track(self, track_id, title, duration=300.0, created='2026-11-01 10:00:00', path=None):
        self.sql(
            'INSERT INTO library_tracks (id, track_uid, title, duration_secs, primary_artist_id, created_at) '
            'VALUES (?, ?, ?, ?, 7, ?)',
            (track_id, _sha(f'{track_id}'), title, duration, created),
        )
        self.sql('INSERT INTO library_track_artists VALUES (?, 7)', (track_id,))
        if path:
            self.sql('INSERT INTO library_media_files (file_path, track_id) VALUES (?, ?)', (path, track_id))

    def listen(self, listen_id, track_id):
        self.sql("INSERT INTO scrobble_listens VALUES (?, ?, '2026-11-02 21:00:00', 'teun')", (listen_id, track_id))

    def dump(self) -> dict[str, list]:
        return {table: sorted(self.sql(f'SELECT * FROM {table}'), key=repr) for table in TABLES}

    def track_ids(self) -> set[int]:
        return {row[0] for row in self.sql('SELECT id FROM library_tracks')}

    def run(self, *argv: str) -> int:
        connection = _Connection(self.path)
        try:
            return backlog.run(connection, connection.cursor(), backlog.parse_args(list(argv)))
        finally:
            connection.close()


@pytest.fixture
def db(tmp_path, monkeypatch):
    """The backlog the 2026-11-12 survey describes, in miniature."""
    monkeypatch.setattr(backlog, 'BACKUP_DIR', str(tmp_path / 'backups'))
    db = Db(tmp_path / 'muma.db')
    # A recent pack track: its successor has the same title and length, and a listen to move.
    db.track(1, 'Wake Up', 241.512, '2026-11-02 08:00:00')
    db.track(2, 'Wake Up', 241.513, '2026-11-02 09:00:00', '/mnt/music/EPs/Label/LBL001/01 Wake Up.flac')
    db.listen(1, 1)
    db.sql("INSERT INTO rating_tracks VALUES (1, 'track', ?, 'teun', 5, '2026-11-03')", (_sha('1'),))
    # An older orphan with a single match, listed separately for a person to read.
    db.track(3, 'Intro', 60.0, '2026-07-01 08:00:00')
    db.track(4, 'Intro', 60.0, '2026-07-02 08:00:00', '/mnt/music/EPs/Other/OTH002/01 Intro.mp3')
    # A recent orphan whose length differs by 10 ms: not the same file. No history, so purged.
    db.track(5, 'Close Call', 200.0, '2026-11-02 08:00:00')
    db.track(6, 'Close Call', 200.01, '2026-11-02 09:00:00', '/mnt/music/EPs/Label/LBL001/02 Close Call.flac')
    # An orphan with two candidates and a listen: kept for a person.
    db.track(7, 'Anthem', 300.0, '2026-11-02 08:00:00')
    db.track(8, 'Anthem', 300.0, created='2026-11-02 09:00:00', path='/mnt/music/EPs/A/A1/01 Anthem.flac')
    db.track(9, 'Anthem', 300.0, created='2026-11-02 09:00:00', path='/mnt/music/EPs/B/B1/01 Anthem.flac')
    db.listen(2, 7)
    return db


def test_the_dry_run_writes_nothing_and_lists_the_older_matches(db, capsys):
    before = db.dump()

    assert db.run() == 0

    assert db.dump() == before
    out = capsys.readouterr().out
    older = out.split('Older matches')[1].split('Recent relinks')[0]
    assert 'orphan 3 ' in older and '/mnt/music/EPs/Other/OTH002/01 Intro.mp3' in older
    assert 'orphan 1 ' not in older
    assert 'track 7 ' in out.split('Kept for a person')[1]
    assert not Path(backlog.BACKUP_DIR).exists()


def test_the_plan_matches_title_and_length_within_five_milliseconds(db):
    connection = _Connection(db.path)
    try:
        plans = {plan['orphan_id']: plan for plan in backlog.survey(connection.cursor())}
    finally:
        connection.close()

    assert {track_id: plan['bucket'] for track_id, plan in plans.items()} == {
        1: 'relink',
        3: 'relink',
        5: 'purge',
        7: 'keep',
    }
    assert plans[1]['target_id'] == 2 and plans[1]['recent']
    assert plans[3]['target_id'] == 4 and not plans[3]['recent']
    assert plans[7]['matches'] == 2 and plans[7]['listens'] == 1


def test_apply_relinks_purges_and_keeps(db):
    assert db.run('--apply') == 0

    assert db.track_ids() == {2, 4, 6, 7, 8, 9}
    assert db.sql('SELECT id, track_id FROM scrobble_listens ORDER BY id') == [(1, 2), (2, 7)]
    assert db.sql('SELECT entity_id FROM rating_tracks') == [(_sha('2'),)]
    backups = list(Path(backlog.BACKUP_DIR).iterdir())
    assert len(backups) == 1
    assert oct(os.stat(backups[0]).st_mode & 0o777) == '0o600'


def test_a_second_apply_finds_only_the_kept_track(db, capsys):
    db.run('--apply')
    capsys.readouterr()

    db.run('--apply')

    assert db.track_ids() == {2, 4, 6, 7, 8, 9}
    assert 'relinked' not in capsys.readouterr().out.split('Done:')[1]


def test_skip_older_leaves_the_older_match_to_the_purge(db):
    db.run('--apply', '--skip-older')

    assert 3 not in db.track_ids()
    assert db.sql('SELECT COUNT(*) FROM scrobble_listens WHERE track_id = 4') == [(0,)]


def test_skip_older_keeps_an_older_match_with_history(db):
    db.listen(3, 3)

    db.run('--apply', '--skip-older')

    assert 3 in db.track_ids()


def test_rollback_puts_every_row_back(db):
    db.sql("INSERT INTO library_works VALUES (1, NULL, 1, NULL)")  # a curator's pin follows the relink
    db.sql("INSERT INTO library_track_bpm VALUES (?, 174.0)", (_sha('1'),))  # moves to track 2's uid
    db.sql("INSERT INTO library_track_effective_bpm VALUES (5, 128.0)")
    db.sql("INSERT INTO library_track_ml_labels VALUES (1, ?, 5, 'unreviewed', 0, '2026-01-01')", (_sha('5'),))
    before = db.dump()

    db.run('--apply')
    assert db.sql('SELECT pinned_track_id FROM library_works') == [(2,)]
    assert db.sql('SELECT track_uid FROM library_track_bpm') == [(_sha('2'),)]
    backup = next(Path(backlog.BACKUP_DIR).iterdir())

    db.run('--rollback', str(backup))

    assert db.dump() == before


def test_rollback_refuses_a_column_name_it_did_not_write(db, tmp_path):
    forged = tmp_path / 'forged.json'
    forged.write_text(json.dumps({'rows': {'library_tracks': [{'id': 1, 'title; DROP': 'x'}]}, 'absent': []}))

    with pytest.raises(ValueError):
        db.run('--rollback', str(forged))
