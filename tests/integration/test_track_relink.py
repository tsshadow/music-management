"""Bug report 042 against a real MariaDB: a retag must not strand ratings and listens.

The scanner runs for real here -- only the tag reader is replaced, so a "retag" is a different
answer from the stub for the same file on disk. Everything else is the production SQL: the track
upsert, the media-file repoint, the relink in its transaction, the label and channel refresh.
"""

from datetime import datetime

import pytest

from services.music_manager import song_version_worker, track_relink
from services.music_manager.routers import rating
from services.music_manager.routers import scanner as scanner_router
from tests.integration.conftest import run_sql

pytestmark = pytest.mark.integration

RATED_AT = datetime(2026, 3, 1, 12, 0, 0)
LISTENED_AT = datetime(2026, 3, 2, 20, 30, 0)


class FakeSong:
    """What ReadonlySong would read from a file: only the fields process_file asks for."""

    def __init__(self, artists, title='Raise Your Fist', publisher=None, length=300):
        self._artists = list(artists)
        self._title = title
        self._publisher = publisher
        self._length = length

    def library_artists(self):
        return self._artists

    def publisher(self):
        return self._publisher

    def title(self):
        return self._title

    def length(self):
        return self._length

    def original_artist(self):
        return None

    def rules_genres(self):
        return []


@pytest.fixture
def library(db, tmp_path, monkeypatch):
    """A scanner rooted at a temporary music folder, reading tags from `tags[path]`."""
    with db.cursor() as cursor:
        rating.init_db(cursor)
    tags = {}
    monkeypatch.setattr(scanner_router, 'ReadonlySong', lambda path: tags[str(path)])
    manager = scanner_router.ScannerManager()
    manager.music_path = str(tmp_path)

    def add_file(relative):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'not really audio')
        return str(path)

    def scan(path, song):
        tags[path] = song
        assert manager.process_file(db, path, force=True)
        return _track_of(db, manager, path)

    return {'db': db, 'add_file': add_file, 'scan': scan, 'manager': manager}


def _track_of(db, manager, path):
    rows = run_sql(
        db,
        'SELECT t.id, t.track_uid FROM library_media_files mf JOIN library_tracks t ON t.id = mf.track_id '
        'WHERE mf.file_path_hash = %s',
        (manager.get_file_hash(path),),
    )
    return rows[0]


def _rate_and_listen(db, track):
    run_sql(
        db,
        "INSERT INTO rating_tracks (entity_type, entity_id, username, rating, updated_at) VALUES ('track', %s, 'user', 5, %s)",
        (track['track_uid'], RATED_AT),
    )
    run_sql(
        db,
        "INSERT INTO scrobble_listens (track_id, listened_at, username, source) VALUES (%s, %s, 'user', 'lms')",
        (track['id'], LISTENED_AT),
    )


def test_a_retag_of_the_primary_artist_carries_rating_and_listen_to_the_new_track(library):
    db = library['db']
    path = library['add_file']('Songs/raise.mp3')
    old = library['scan'](path, FakeSong(['Angerfist']))
    _rate_and_listen(db, old)

    new = library['scan'](path, FakeSong(['Outsiders', 'Angerfist']))

    assert new['id'] != old['id']
    assert not run_sql(db, 'SELECT id FROM library_tracks WHERE id = %s', (old['id'],))
    ratings = run_sql(db, 'SELECT entity_id, rating, updated_at FROM rating_tracks')
    assert ratings == [{'entity_id': new['track_uid'], 'rating': 5, 'updated_at': RATED_AT}]
    listens = run_sql(db, 'SELECT track_id, listened_at FROM scrobble_listens')
    assert listens == [{'track_id': new['id'], 'listened_at': LISTENED_AT}]


def test_a_rating_already_on_the_new_track_is_kept_when_newer(library):
    db = library['db']
    path = library['add_file']('Songs/raise.mp3')
    old = library['scan'](path, FakeSong(['Angerfist']))
    _rate_and_listen(db, old)
    # The same listen already recorded against the successor: a duplicate, not a second listen.
    other = library['add_file']('Songs/raise-copy.mp3')
    successor = library['scan'](other, FakeSong(['Outsiders', 'Angerfist']))
    run_sql(
        db,
        "INSERT INTO rating_tracks (entity_type, entity_id, username, rating, updated_at) VALUES ('track', %s, 'user', 2, %s)",
        (successor['track_uid'], datetime(2026, 9, 1)),
    )
    run_sql(
        db,
        "INSERT INTO scrobble_listens (track_id, listened_at, username, source) VALUES (%s, %s, 'user', 'lms')",
        (successor['id'], LISTENED_AT),
    )

    library['scan'](path, FakeSong(['Outsiders', 'Angerfist']))

    assert run_sql(db, 'SELECT entity_id, rating FROM rating_tracks') == [
        {'entity_id': successor['track_uid'], 'rating': 2}
    ]
    assert run_sql(db, 'SELECT track_id FROM scrobble_listens') == [{'track_id': successor['id']}]


def test_a_track_that_keeps_another_file_is_not_deleted(library):
    db = library['db']
    first = library['add_file']('Songs/raise.mp3')
    second = library['add_file']('Songs/raise.flac')
    old = library['scan'](first, FakeSong(['Angerfist']))
    assert library['scan'](second, FakeSong(['Angerfist']))['id'] == old['id']
    _rate_and_listen(db, old)

    library['scan'](first, FakeSong(['Outsiders', 'Angerfist']))

    assert run_sql(db, 'SELECT id FROM library_tracks WHERE id = %s', (old['id'],)) == [{'id': old['id']}]
    assert run_sql(db, 'SELECT entity_id FROM rating_tracks') == [{'entity_id': old['track_uid']}]
    assert run_sql(db, 'SELECT track_id FROM scrobble_listens') == [{'track_id': old['id']}]


def test_a_corrected_publisher_replaces_the_label_link(library):
    db = library['db']
    path = library['add_file']('EPs/Label One/LO001/raise.mp3')
    track = library['scan'](path, FakeSong(['Angerfist'], publisher='Label One'))

    library['scan'](path, FakeSong(['Angerfist'], publisher='Label Two'))

    labels = run_sql(
        db,
        'SELECT l.name FROM library_track_labels tl JOIN library_labels l ON l.id = tl.label_id WHERE tl.track_id = %s',
        (track['id'],),
    )
    assert labels == [{'name': 'Label Two'}]


def test_a_label_a_sibling_file_still_carries_is_kept(library):
    db = library['db']
    first = library['add_file']('EPs/Label One/LO001/raise.mp3')
    second = library['add_file']('EPs/Label One/LO001/raise.flac')
    track = library['scan'](first, FakeSong(['Angerfist'], publisher='Label One'))
    library['scan'](second, FakeSong(['Angerfist'], publisher='Label One'))

    library['scan'](first, FakeSong(['Angerfist'], publisher='Label Two'))

    labels = run_sql(
        db,
        'SELECT l.name FROM library_track_labels tl JOIN library_labels l ON l.id = tl.label_id '
        'WHERE tl.track_id = %s ORDER BY l.name',
        (track['id'],),
    )
    assert labels == [{'name': 'Label One'}, {'name': 'Label Two'}]


def _seed_orphan(db):
    """A fileless track and its successor, the way a pre-fix retag left them."""
    run_sql(db, "INSERT INTO library_artists (name) VALUES ('Angerfist')")
    artist = run_sql(db, "SELECT id FROM library_artists WHERE name = 'Angerfist'")[0]['id']
    run_sql(
        db,
        'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id, created_at) '
        "VALUES ('uid-old', 'Raise Your Fist', 300, %s, '2025-01-01')",
        (artist,),
    )
    old = run_sql(db, "SELECT id, track_uid FROM library_tracks WHERE track_uid = 'uid-old'")[0]
    run_sql(
        db,
        'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id) '
        "VALUES ('uid-new', 'Raise your Fist!', 300, %s)",
        (artist,),
    )
    new = run_sql(db, "SELECT id, track_uid FROM library_tracks WHERE track_uid = 'uid-new'")[0]
    run_sql(
        db,
        'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, SHA2(%s, 256), %s)',
        ('/music/raise.mp3', '/music/raise.mp3', new['id']),
    )
    _rate_and_listen(db, old)
    return old, new


def test_relink_orphaned_tracks_repairs_a_seeded_orphan_and_is_idempotent(db):
    with db.cursor() as cursor:
        rating.init_db(cursor)
    old, new = _seed_orphan(db)

    first = track_relink.relink_orphaned_tracks(db)
    second = track_relink.relink_orphaned_tracks(db)

    assert (first['orphans'], first['relinked'], first['ratings_moved'], first['listens_moved']) == (1, 1, 1, 1)
    assert (second['orphans'], second['relinked']) == (0, 0)
    assert not run_sql(db, 'SELECT id FROM library_tracks WHERE id = %s', (old['id'],))
    assert run_sql(db, 'SELECT entity_id FROM rating_tracks') == [{'entity_id': new['track_uid']}]
    assert run_sql(db, 'SELECT track_id, listened_at FROM scrobble_listens') == [
        {'track_id': new['id'], 'listened_at': LISTENED_AT}
    ]


def test_the_relink_endpoint_runs_the_repair(api, headers, db):
    with db.cursor() as cursor:
        rating.init_db(cursor)
    _old, new = _seed_orphan(db)

    response = api.post('/api/scanner/relink-orphans', headers=headers)
    status = api.get('/api/scanner/relink-orphans', headers=headers).json()

    assert response.status_code == 200
    assert status['last']['relinked'] == 1
    assert run_sql(db, 'SELECT entity_id FROM rating_tracks') == [{'entity_id': new['track_uid']}]


def test_a_fileless_track_never_becomes_canonical(db):
    run_sql(db, "INSERT INTO library_works (work_key, title) VALUES ('angerfist|raise your fist', 'Raise Your Fist')")
    work = run_sql(db, 'SELECT id FROM library_works')[0]['id']
    run_sql(
        db,
        'INSERT INTO library_tracks (track_uid, title, work_id, version_score, created_at) '
        "VALUES ('uid-old', 'Raise Your Fist', %s, 10, '2025-01-01')",
        (work,),
    )
    run_sql(
        db,
        "INSERT INTO library_tracks (track_uid, title, work_id, version_score) VALUES ('uid-new', 'Raise Your Fist', %s, 10)",
        (work,),
    )
    new = run_sql(db, "SELECT id FROM library_tracks WHERE track_uid = 'uid-new'")[0]['id']
    run_sql(
        db,
        'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, SHA2(%s, 256), %s)',
        ('/music/raise.mp3', '/music/raise.mp3', new),
    )

    with db.cursor() as cursor:
        song_version_worker.recompute_canonicals(cursor, {work})

    assert run_sql(db, 'SELECT canonical_track_id FROM library_works WHERE id = %s', (work,)) == [
        {'canonical_track_id': new}
    ]
