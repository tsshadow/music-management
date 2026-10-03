"""The scanner's vanished-file pass (GitLab issue #170), against SQLite and a real folder tree.

A media row whose file is gone is deleted after a full walk; its track never is, so ratings and
listens survive. A move within the library keeps its history: on the same track when the tags
are unchanged, relinked to the new track when the move came with a retag. An unmounted share, a
folder that cannot be listed, or more than 10% of the rows gone stops the pass with nothing
deleted.
"""

# pylint: disable=redefined-outer-name  # pytest fixtures
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

from services.common import vanished_files
from services.common.vanished_files import LibraryUnreadable
from services.music_manager import vanished_media
from services.music_manager.routers import scanner as scanner_router


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


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
    """The pooled connection's surface: cursor(), begin/commit/rollback, close."""

    def __init__(self, path):
        self._connection = sqlite3.connect(path)
        self._connection.create_function('SHA2', 2, lambda text, _bits: _sha(text))

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


SCHEMA = """
CREATE TABLE library_tracks (id INTEGER PRIMARY KEY, track_uid TEXT UNIQUE, title TEXT, duration_secs REAL,
    primary_artist_id INTEGER, work_id INTEGER);
CREATE TABLE library_media_files (id INTEGER PRIMARY KEY, file_path TEXT, file_path_hash TEXT UNIQUE,
    track_id INTEGER);
CREATE TABLE rating_tracks (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id TEXT, username TEXT, rating INTEGER,
    updated_at TEXT, UNIQUE (entity_type, entity_id, username));
CREATE TABLE scrobble_listens (id INTEGER PRIMARY KEY, track_id INTEGER, listened_at TEXT, username TEXT,
    UNIQUE (username, listened_at, track_id));
CREATE TABLE library_works (id INTEGER PRIMARY KEY, canonical_track_id INTEGER, pinned_track_id INTEGER);
CREATE TABLE library_track_audio_features (id INTEGER PRIMARY KEY, internal_track_id INTEGER);
CREATE TABLE library_track_ml_labels (id INTEGER PRIMARY KEY, track_id TEXT, internal_track_id INTEGER,
    updated_at TEXT);
CREATE TABLE library_track_artists (track_id INTEGER, artist_id INTEGER);
"""


class Library:
    """A music root on disk and a muma database whose rows point into it."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path / 'music'
        self.root.mkdir()
        self.db = tmp_path / 'muma.db'
        connection = sqlite3.connect(self.db)
        connection.executescript(SCHEMA)
        connection.commit()
        connection.close()

    def file(self, relative: str, tags: str = 'Song|300|7') -> str:
        """Create a file whose content stands in for its tags: `title|duration|artist id`."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tags)
        return str(path)

    def sql(self, statement: str, params=()):
        connection = sqlite3.connect(self.db)
        try:
            rows = connection.execute(statement, params).fetchall()
            connection.commit()
            return rows
        finally:
            connection.close()

    def track(self, track_id: int, title='Song', duration=300.0, artist=7) -> None:
        uid = _sha(f'{title}-{int(duration)}-{artist}')
        self.sql(
            'INSERT INTO library_tracks (id, track_uid, title, duration_secs, primary_artist_id) VALUES (?, ?, ?, ?, ?)',
            (track_id, uid, title, duration, artist),
        )
        self.sql('INSERT INTO library_track_artists VALUES (?, ?)', (track_id, artist))

    def media(self, media_id: int, path: str, track_id: int | None, file_hash: str | None = None) -> None:
        self.sql(
            'INSERT INTO library_media_files VALUES (?, ?, ?, ?)', (media_id, path, file_hash or _sha(path), track_id)
        )

    def media_ids(self) -> set[int]:
        return {row[0] for row in self.sql('SELECT id FROM library_media_files')}

    def track_ids(self) -> set[int]:
        return {row[0] for row in self.sql('SELECT id FROM library_tracks')}

    def connection(self) -> _Connection:
        return _Connection(self.db)

    def walk(self) -> set[str]:
        """What the scanner's walk would have seen."""
        return {str(path) for path in self.root.rglob('*') if path.is_file()}

    def drop(self) -> dict[str, int]:
        connection = self.connection()
        try:
            return vanished_media.drop_vanished_media(connection, str(self.root), self.walk())
        finally:
            connection.close()


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """A tiny library: the 10% brake would stop every test, so it is off unless a test sets it."""
    monkeypatch.setattr(vanished_files, 'MAX_GONE_SHARE', 1.0)
    return Library(tmp_path)


def test_a_vanished_file_loses_its_row_and_keeps_its_track(lib):
    kept = lib.file('EPs/Label/R1/01.mp3')
    lib.track(1)
    lib.media(10, kept, 1)
    lib.media(11, str(lib.root / 'EPs/__TODO/R1/01.mp3'), 1)  # the old place, folder gone
    lib.track(2, title='Alone')
    lib.media(20, str(lib.root / 'EPs/Label/R1/02.mp3'), 2)  # folder there, file gone
    lib.sql("INSERT INTO rating_tracks VALUES (1, 'track', ?, 'user', 5, '2026-01-01')", (_sha('Alone-300-7'),))
    lib.sql("INSERT INTO scrobble_listens VALUES (1, 2, '2026-06-01 10:00:00', 'user')")

    totals = lib.drop()

    assert lib.media_ids() == {10}
    assert lib.track_ids() == {1, 2}
    assert lib.sql('SELECT track_id FROM scrobble_listens') == [(2,)]
    assert lib.sql('SELECT COUNT(*) FROM rating_tracks') == [(1,)]
    assert totals['deleted'] == 2
    assert totals['left_without_file'] == 1
    assert totals['kept_without_file'] == 1


def test_an_empty_library_folder_is_an_unmounted_share(lib):
    lib.file('Soundcloud/a.mp3')
    (lib.root / 'EPs').mkdir()  # the mount point is there, the share is not
    lib.track(1)
    lib.media(10, str(lib.root / 'EPs/Label/R1/01.mp3'), 1)

    with pytest.raises(LibraryUnreadable, match='is the share mounted'):
        lib.drop()

    assert lib.media_ids() == {10}


def test_a_missing_music_root_deletes_nothing(lib, tmp_path):
    lib.track(1)
    lib.media(10, str(lib.root / 'EPs/R/01.mp3'), 1)
    lib.root.rmdir()

    with pytest.raises(LibraryUnreadable):
        lib.drop()

    assert lib.media_ids() == {10}


def test_a_folder_that_cannot_be_listed_stops_the_pass(lib, monkeypatch):
    lib.file('EPs/Other/x.mp3')
    lib.track(1)
    lib.media(10, str(lib.root / 'EPs/R/01.mp3'), 1)
    real = vanished_files.list_dir

    def refuse(folder):
        if folder.endswith('/R'):
            raise LibraryUnreadable(f'cannot list {folder}: permission denied')
        return real(folder)

    monkeypatch.setattr(vanished_files, 'list_dir', refuse)

    with pytest.raises(LibraryUnreadable, match='permission denied'):
        lib.drop()
    assert lib.media_ids() == {10}


def test_more_than_a_tenth_gone_stops_the_pass(lib, monkeypatch):
    monkeypatch.setattr(vanished_files, 'MAX_GONE_SHARE', 0.10)
    lib.track(1)
    for i in range(9):
        lib.media(100 + i, lib.file(f'EPs/R/{i:02d}.mp3'), 1)
    lib.media(200, str(lib.root / 'EPs/Gone/01.mp3'), 1)
    lib.media(201, str(lib.root / 'EPs/Gone/02.mp3'), 1)

    with pytest.raises(LibraryUnreadable, match='2 of 11 rows look gone'):
        lib.drop()

    assert {200, 201} <= lib.media_ids()


def test_one_tenth_gone_is_still_allowed(lib, monkeypatch):
    monkeypatch.setattr(vanished_files, 'MAX_GONE_SHARE', 0.10)
    lib.track(1)
    for i in range(9):
        lib.media(100 + i, lib.file(f'EPs/R/{i:02d}.mp3'), 1)
    lib.media(200, str(lib.root / 'EPs/Gone/01.mp3'), 1)

    assert lib.drop()['deleted'] == 1
    assert 200 not in lib.media_ids()


def test_a_file_seen_elsewhere_than_the_walk_is_kept(lib):
    """A row the walk did not meet (a hidden folder) is kept when the listing finds its file."""
    hidden = lib.file('EPs/.hidden/01.mp3')
    lib.track(1)
    lib.media(10, hidden, 1)
    connection = lib.connection()
    try:
        totals = vanished_media.drop_vanished_media(connection, str(lib.root), set())
    finally:
        connection.close()

    assert totals['unseen'] == 1 and totals['gone'] == 0
    assert lib.media_ids() == {10}


def test_a_file_that_came_back_before_the_delete_is_kept(lib, monkeypatch):
    lib.file('EPs/R/02.mp3')
    lib.track(1)
    lib.media(10, str(lib.root / 'EPs/R/01.mp3'), 1)
    monkeypatch.setattr(vanished_files, 'path_exists', lambda path: True)

    totals = lib.drop()

    assert lib.media_ids() == {10}
    assert totals['changed'] == 1 and totals['deleted'] == 0


def test_a_stale_row_with_a_wrong_hash_is_left_to_the_operator_script(lib):
    lib.file('EPs/R/02.mp3')
    lib.track(1)
    lib.media(10, str(lib.root / 'EPs/R/01.mp3'), 1, file_hash='not-the-sha-of-the-path')

    assert lib.drop()['rows'] == 0
    assert lib.media_ids() == {10}


def test_a_row_outside_the_music_root_is_not_the_scanners(lib):
    lib.file('EPs/R/02.mp3')
    lib.track(1)
    lib.media(10, '/elsewhere/01.mp3', 1)

    assert lib.drop()['rows'] == 0
    assert lib.media_ids() == {10}


def test_a_file_directly_in_the_music_root_belongs_to_the_root():
    assert vanished_files.library_root('/mnt/music/Thumbs.db', '/mnt/music') == '/mnt/music'
    assert vanished_files.library_root('/mnt/music/EPs/R/01.mp3', '/mnt/music/') == '/mnt/music/EPs'
    assert vanished_files.library_root('/mnt/music/EPs/R/01.mp3') == '/mnt/music/EPs'


# --- through the scanner's full walk ----------------------------------------------------------------


def _fake_process_file(lib: Library):
    """process_file without mutagen: the file's content is its tags, the track keyed as the scanner keys it."""

    def process(conn, path, force=False):
        title, duration, artist = Path(path).read_text().split('|')
        uid = _sha(f'{title}-{duration}-{artist}')
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM library_media_files WHERE file_path_hash = %s', (_sha(path),))
            if cursor.fetchone():
                return False
            cursor.execute('SELECT id FROM library_tracks WHERE track_uid = %s', (uid,))
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id) '
                    'VALUES (%s, %s, %s, %s)',
                    (uid, title, float(duration), int(artist)),
                )
                cursor.execute('SELECT id FROM library_tracks WHERE track_uid = %s', (uid,))
                row = cursor.fetchone()
                cursor.execute('INSERT INTO library_track_artists VALUES (%s, %s)', (row['id'], int(artist)))
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, %s, %s)',
                (path, _sha(path), row['id']),
            )
        conn.commit()
        return True

    return process


@pytest.fixture
def scanner(lib):
    """A ScannerManager over the tmp library, with the database and LMS replaced."""
    manager = scanner_router.ScannerManager()
    manager.music_path = str(lib.root)
    with (
        patch.object(manager, '_reload_rules'),
        patch.object(manager, 'process_file', side_effect=_fake_process_file(lib)),
        patch.object(scanner_router, 'get_db_connection', side_effect=lib.connection),
        patch.object(scanner_router.lms_scan_trigger, 'trigger') as trigger,
    ):
        manager.lms_trigger = trigger
        yield manager


def _scan_and_move(lib: Library, scanner, new_tags: str) -> None:
    old = lib.file('EPs/__TODO/R1/01.mp3', 'Song|300|7')
    lib.file('EPs/Label/R0/keep.mp3', 'Other|200|8')
    scanner.run_full()
    old_track = lib.sql('SELECT track_id FROM library_media_files WHERE file_path = ?', (old,))[0][0]
    lib.sql("INSERT INTO rating_tracks VALUES (1, 'track', ?, 'user', 5, '2026-01-01')", (_sha('Song-300-7'),))
    lib.sql("INSERT INTO scrobble_listens VALUES (1, ?, '2026-06-01 10:00:00', 'user')", (old_track,))
    new = lib.root / 'EPs/Label/R1/01.mp3'
    new.parent.mkdir(parents=True)
    Path(old).rename(new)
    new.write_text(new_tags)
    (lib.root / 'EPs/__TODO/R1').rmdir()


def test_a_move_keeps_the_track_and_its_history(lib, scanner):
    _scan_and_move(lib, scanner, 'Song|300|7')
    tracks_before = lib.track_ids()

    scanner.run_full()

    paths = {row[0] for row in lib.sql('SELECT file_path FROM library_media_files')}
    assert paths == {str(lib.root / 'EPs/Label/R1/01.mp3'), str(lib.root / 'EPs/Label/R0/keep.mp3')}
    assert lib.track_ids() == tracks_before
    song = lib.sql('SELECT id FROM library_tracks WHERE title = ?', ('Song',))[0][0]
    assert lib.sql('SELECT track_id FROM scrobble_listens') == [(song,)]
    assert lib.sql('SELECT entity_id FROM rating_tracks') == [(_sha('Song-300-7'),)]
    scanner.lms_trigger.assert_called()


def test_a_move_with_a_retag_relinks_the_history_to_the_new_track(lib, scanner):
    # Same recording, the artist credit re-cased into a new title: a new track_uid, same metadata key.
    _scan_and_move(lib, scanner, 'SONG|300|7')

    scanner.run_full()

    titles = {row[0] for row in lib.sql('SELECT title FROM library_tracks')}
    assert titles == {'SONG', 'Other'}  # the old row was merged into the new one and deleted
    new_track = lib.sql('SELECT id FROM library_tracks WHERE title = ?', ('SONG',))[0][0]
    assert lib.sql('SELECT track_id FROM scrobble_listens') == [(new_track,)]
    assert lib.sql('SELECT entity_id FROM rating_tracks') == [(_sha('SONG-300-7'),)]


def test_an_unmounted_share_skips_the_pass_and_the_scan_still_finishes(lib, scanner, caplog):
    lib.file('EPs/Label/R0/keep.mp3', 'Other|200|8')
    scanner.run_full()
    lib.track(5, title='Elsewhere')
    lib.media(50, str(lib.root / 'Youtube/Channel/v.mp3'), 5)
    (lib.root / 'Youtube').mkdir()

    scanner.run_full()

    assert 50 in lib.media_ids()
    assert 'Vanished-file cleanup skipped' in caplog.text
    assert scanner.lms_trigger.call_count == 2


def test_the_pass_can_be_switched_off(lib, scanner):
    lib.track(5, title='Gone')
    lib.media(50, str(lib.root / 'EPs/Gone/v.mp3'), 5)
    lib.file('EPs/Label/R0/keep.mp3', 'Other|200|8')
    real_get = scanner.settings.get
    with patch.object(
        scanner.settings,
        'get',
        side_effect=lambda key, default=None: False if key == 'scanner_drop_vanished_media' else real_get(key, default),
    ):
        scanner.run_full()

    assert 50 in lib.media_ids()
