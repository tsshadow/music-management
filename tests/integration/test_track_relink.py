"""Bug report 042 against a real MariaDB: a retag must not strand ratings and listens.

The scanner runs for real here -- only the tag reader is replaced, so a "retag" is a different
answer from the stub for the same file on disk. Everything else is the production SQL: the track
upsert, the media-file repoint, the relink in its transaction, the label and channel refresh.
"""

from datetime import datetime

import pytest

from services.music_manager import orphan_purge, song_version_worker, track_relink
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

    return {'db': db, 'add_file': add_file, 'scan': scan, 'manager': manager, 'tags': tags, 'root': tmp_path}


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


def test_a_retag_keeps_the_measured_and_the_hand_set_bpm(library):
    db = library['db']
    path = library['add_file']('Songs/raise.mp3')
    old = library['scan'](path, FakeSong(['Angerfist']))
    run_sql(
        db,
        "INSERT INTO library_track_bpm (track_uid, bpm, method, analyzed_at) VALUES (%s, 175.00, 'test', %s)",
        (old['track_uid'], RATED_AT),
    )
    run_sql(
        db,
        'INSERT INTO library_track_bpm_manual (track_uid, bpm, set_at) VALUES (%s, 87.50, %s)',
        (old['track_uid'], RATED_AT),
    )

    new = library['scan'](path, FakeSong(['Outsiders', 'Angerfist']))

    assert new['track_uid'] != old['track_uid']
    assert run_sql(db, 'SELECT track_uid, bpm FROM library_track_bpm') == [{'track_uid': new['track_uid'], 'bpm': 175}]
    assert run_sql(db, 'SELECT track_uid, bpm FROM library_track_bpm_manual') == [
        {'track_uid': new['track_uid'], 'bpm': 87.5}
    ]


def test_a_bpm_the_new_uid_already_has_is_kept(library):
    db = library['db']
    path = library['add_file']('Songs/raise.mp3')
    old = library['scan'](path, FakeSong(['Angerfist']))
    other = library['add_file']('Songs/raise-copy.mp3')
    successor = library['scan'](other, FakeSong(['Outsiders', 'Angerfist']))
    for uid, bpm in ((old['track_uid'], 87.5), (successor['track_uid'], 175)):
        run_sql(
            db,
            'INSERT INTO library_track_bpm_manual (track_uid, bpm, set_at) VALUES (%s, %s, %s)',
            (uid, bpm, RATED_AT),
        )

    library['scan'](path, FakeSong(['Outsiders', 'Angerfist']))

    assert run_sql(db, 'SELECT track_uid, bpm FROM library_track_bpm_manual') == [
        {'track_uid': successor['track_uid'], 'bpm': 175}
    ]


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


# --- bug report 104: the file-name key and the purge -------------------------------------------


def _track(db, uid, title, duration=None, artist=None):
    run_sql(
        db,
        'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id, created_at) '
        "VALUES (%s, %s, %s, %s, '2026-05-01')",
        (uid, title, duration, artist),
    )
    return run_sql(db, 'SELECT id, track_uid FROM library_tracks WHERE track_uid = %s', (uid,))[0]


def _file(db, path, track_id):
    run_sql(
        db,
        'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, SHA2(%s, 256), %s)',
        (path, path, track_id),
    )


def _seed_first_scan_stubs(db):
    """Three May-2026 stubs: one named like exactly one file, one like two tracks' files, one like nothing."""
    unique = _track(db, 'stub-unique', '04-lucy_furr_and_meander_-_damnation')
    shared = _track(db, 'stub-shared', '01-intro')
    lonely = _track(db, 'stub-lonely', 'gone-for-good')
    damnation = _track(db, 'real-damnation', 'Damnation', 301, None)
    intro_a = _track(db, 'real-intro-a', 'Intro', 60, None)
    intro_b = _track(db, 'real-intro-b', 'Intro', 75, None)
    _file(db, '/music/Labels/X/04-lucy_furr_and_meander_-_damnation.mp3', damnation['id'])
    _file(db, '/music/Labels/X/01-intro.mp3', intro_a['id'])
    _file(db, '/music/Labels/Y/01-intro.flac', intro_b['id'])
    return {'unique': unique, 'shared': shared, 'lonely': lonely, 'damnation': damnation}


def test_a_first_scan_stub_is_relinked_by_its_file_name(db):
    seeded = _seed_first_scan_stubs(db)
    _rate_and_listen(db, seeded['unique'])

    dry = track_relink.relink_orphaned_tracks(db, dry_run=True)
    assert (dry['relinked_file_name'], dry['ambiguous_file_name'], dry['unmatched']) == (1, 1, 2)
    assert run_sql(db, 'SELECT COUNT(*) AS n FROM library_tracks')[0]['n'] == 6

    first = track_relink.relink_orphaned_tracks(db)
    second = track_relink.relink_orphaned_tracks(db)

    assert (first['relinked'], first['relinked_file_name'], first['relinked_metadata']) == (1, 1, 0)
    assert (first['listens_moved'], first['ratings_moved']) == (1, 1)
    assert (second['relinked'], second['orphans']) == (0, 2)
    assert not run_sql(db, 'SELECT id FROM library_tracks WHERE id = %s', (seeded['unique']['id'],))
    assert run_sql(db, 'SELECT track_id FROM scrobble_listens') == [{'track_id': seeded['damnation']['id']}]
    # The ambiguous stub is still there: two different tracks carry its name.
    assert run_sql(db, 'SELECT id FROM library_tracks WHERE id = %s', (seeded['shared']['id'],))


def test_the_purge_deletes_unreferenced_orphans_and_keeps_the_rest(db):
    run_sql(db, "INSERT INTO library_artists (name) VALUES ('Angerfist')")
    artist = run_sql(db, "SELECT id FROM library_artists WHERE name = 'Angerfist'")[0]['id']
    free = _track(db, 'free', 'free stub')
    listened = _track(db, 'listened', 'listened stub')
    pinned = _track(db, 'pinned', 'pinned stub')
    live = _track(db, 'live', 'Raise Your Fist', 300, artist)
    _file(db, '/music/raise.mp3', live['id'])
    run_sql(
        db,
        "INSERT INTO library_track_artists (track_id, artist_id, role) VALUES (%s, %s, 'primary')",
        (free['id'], artist),
    )
    run_sql(db, "INSERT INTO library_track_ml_labels (track_id, ml_genre) VALUES ('free', 'Hardcore')")
    run_sql(
        db,
        "INSERT INTO library_track_ml_labels (track_id, ml_genre, ml_review_status) VALUES ('pinned', 'Hardcore', 'human_verified')",
    )
    run_sql(
        db,
        "INSERT INTO scrobble_listens (username, track_id, listened_at) VALUES ('user', %s, %s)",
        (listened['id'], LISTENED_AT),
    )
    run_sql(
        db,
        "INSERT INTO library_works (work_key, title, pinned_track_id, previous_canonical_track_id) "
        "VALUES ('a|pinned', 'pinned', %s, %s)",
        (pinned['id'], free['id']),
    )

    dry = orphan_purge.purge_orphaned_tracks(db, dry_run=True)
    assert (dry['orphans'], dry['purged'], dry['kept'], dry['kept_listens'], dry['kept_pinned']) == (3, 1, 2, 1, 1)
    assert run_sql(db, 'SELECT COUNT(*) AS n FROM library_tracks')[0]['n'] == 4

    first = orphan_purge.purge_orphaned_tracks(db)
    second = orphan_purge.purge_orphaned_tracks(db)

    assert (first['purged'], first['links_deleted'], first['ml_labels_deleted'], first['works_cleared']) == (1, 1, 1, 1)
    assert (second['purged'], second['kept']) == (0, 2)
    ids = {row['id'] for row in run_sql(db, 'SELECT id FROM library_tracks')}
    assert ids == {listened['id'], pinned['id'], live['id']}
    assert run_sql(db, 'SELECT track_id FROM library_track_ml_labels') == [{'track_id': 'pinned'}]
    assert run_sql(db, 'SELECT previous_canonical_track_id FROM library_works') == [
        {'previous_canonical_track_id': None}
    ]
    assert run_sql(db, 'SELECT COUNT(*) AS n FROM scrobble_listens')[0]['n'] == 1


def test_the_dry_run_endpoints_write_nothing(api, headers, db):
    _seed_first_scan_stubs(db)

    relink = api.post('/api/scanner/relink-orphans?dry_run=1', headers=headers)
    relink_status = api.get('/api/scanner/relink-orphans', headers=headers).json()
    purge = api.post('/api/scanner/purge-orphans?dry_run=1', headers=headers)
    purge_status = api.get('/api/scanner/purge-orphans', headers=headers).json()

    assert (relink.status_code, purge.status_code) == (200, 200)
    assert relink_status['keys'] == ['metadata', 'file_name']
    assert relink_status['last']['dry_run'] is True
    assert relink_status['last']['relinked_file_name'] == 1
    assert purge_status['last']['purged'] == 3
    assert run_sql(db, 'SELECT COUNT(*) AS n FROM library_tracks')[0]['n'] == 6


# --- issue #170: the scanner removes the media row of a file gone from disk ------------------------


@pytest.fixture
def moved(library, monkeypatch):
    """A rated and played file scanned at its old place, then moved; the walk has not seen it yet.

    Two files is a tiny library, where one gone row is 50%: the 10% brake is lifted here and
    tested in services/music_manager/tests/test_vanished_media.py. The pass is off by default, so
    it is switched on here.
    """
    from services.common import vanished_files

    monkeypatch.setattr(vanished_files, 'MAX_GONE_SHARE', 1.0)
    settings = library['manager'].settings
    real_get = settings.get
    monkeypatch.setattr(
        settings,
        'get',
        lambda key, default=None: True if key == 'scanner_drop_vanished_media' else real_get(key, default),
    )
    db = library['db']
    library['scan'](library['add_file']('EPs/Label/R0/keep.mp3'), FakeSong(['Outsiders'], title='Keep'))
    path = library['add_file']('EPs/__TODO/R1/raise.mp3')
    old = library['scan'](path, FakeSong(['Angerfist']))
    _rate_and_listen(db, old)
    new_path = library['root'] / 'EPs/Label/R1/raise.mp3'
    new_path.parent.mkdir(parents=True)
    (library['root'] / 'EPs/__TODO/R1/raise.mp3').rename(new_path)
    return {**library, 'old': old, 'new_path': str(new_path)}


def _walk_and_drop(manager, db):
    """One full walk and the vanished-file pass after it, on the fixture's connection."""
    seen: set[str] = set()
    manager._scan_recursive(db, False, seen)
    return manager._drop_vanished(db, seen)


def test_a_moved_file_keeps_its_track_and_loses_only_the_old_row(moved):
    db, old = moved['db'], moved['old']
    moved['tags'][moved['new_path']] = FakeSong(['Angerfist'])

    totals = _walk_and_drop(moved['manager'], db)

    assert (totals['deleted'], totals['left_without_file']) == (1, 0)
    assert run_sql(db, 'SELECT file_path FROM library_media_files WHERE track_id = %s', (old['id'],)) == [
        {'file_path': moved['new_path']}
    ]
    assert run_sql(db, 'SELECT entity_id FROM rating_tracks') == [{'entity_id': old['track_uid']}]
    assert run_sql(db, 'SELECT track_id FROM scrobble_listens') == [{'track_id': old['id']}]


def test_a_moved_and_retagged_file_takes_its_history_to_the_new_track(moved):
    db, old = moved['db'], moved['old']
    moved['tags'][moved['new_path']] = FakeSong(['Angerfist'], title='Raise your Fist!')

    totals = _walk_and_drop(moved['manager'], db)

    new = _track_of(db, moved['manager'], moved['new_path'])
    assert new['id'] != old['id']
    assert (totals['deleted'], totals['relinked'], totals['ratings_moved'], totals['listens_moved']) == (1, 1, 1, 1)
    assert not run_sql(db, 'SELECT id FROM library_tracks WHERE id = %s', (old['id'],))
    assert run_sql(db, 'SELECT entity_id FROM rating_tracks') == [{'entity_id': new['track_uid']}]
    assert run_sql(db, 'SELECT track_id FROM scrobble_listens') == [{'track_id': new['id']}]


def test_a_deleted_file_keeps_its_track_for_relink_orphans(moved):
    db, old = moved['db'], moved['old']
    (moved['root'] / 'EPs/Label/R1/raise.mp3').unlink()

    totals = _walk_and_drop(moved['manager'], db)

    assert (totals['deleted'], totals['kept_without_file']) == (1, 1)
    assert run_sql(db, 'SELECT id FROM library_tracks WHERE id = %s', (old['id'],)) == [{'id': old['id']}]
    assert run_sql(db, 'SELECT entity_id FROM rating_tracks') == [{'entity_id': old['track_uid']}]
