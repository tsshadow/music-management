"""Bug report 039's repair against a real MariaDB and a throwaway SQLite standing in for `lms.db`.

The SQLite file carries only the LMS columns the reconcile reads (`user.login_name`,
`track.absolute_file_path`, `listen.date_time/backend/sync_state/user_id/track_id`), in LMS's own
spelling: `date_time` as Wt::Dbo writes it, ISO 8601 text in UTC with milliseconds.
"""

import os
import sqlite3
import time
from datetime import UTC, datetime

import pytest

from tests.integration.conftest import run_sql

pytestmark = pytest.mark.integration

PLAYED = datetime(2026, 8, 21, 19, 2, 5, tzinfo=UTC)  # the real moment of the shifted play
SHIFTED_TO = datetime(2026, 9, 1, 3, 0, 0, tzinfo=UTC)  # where bug 039 moved it
EXACT = datetime(2026, 8, 22, 10, 0, 0, tzinfo=UTC)
LOST = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)


def _ts(moment):
    return int(moment.timestamp())


def _lms_text(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%S.123')


@pytest.fixture
def utc_process():
    """Run the app in UTC, as the music-manager image does; the relay's naive datetimes depend on it."""
    previous = os.environ.get('TZ')
    os.environ['TZ'] = 'UTC'
    time.tzset()
    yield
    if previous is None:
        os.environ.pop('TZ', None)
    else:
        os.environ['TZ'] = previous
    time.tzset()


@pytest.fixture
def lms_db(tmp_path, monkeypatch):
    """An `lms.db` with one user and three tracks, visible to music-manager as its only server."""
    path = tmp_path / 'lms.db'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE "user" ("id" integer primary key autoincrement, "login_name" text not null)')
    conn.execute('CREATE TABLE "track" ("id" integer primary key autoincrement, "absolute_file_path" text not null)')
    conn.execute(
        'CREATE TABLE "listen" ("id" integer primary key autoincrement, "date_time" text, '
        '"backend" integer not null, "sync_state" integer not null, "user_id" bigint, "track_id" bigint)'
    )
    conn.execute('INSERT INTO "user" (login_name) VALUES (\'user\')')
    for name in ('shifted', 'exact', 'lost'):
        conn.execute('INSERT INTO "track" (absolute_file_path) VALUES (?)', (f'/music/Sets/{name}.mp3',))
    for track_id, moment in ((1, PLAYED), (2, EXACT), (3, LOST)):
        conn.execute(
            'INSERT INTO "listen" (date_time, backend, sync_state, user_id, track_id) VALUES (?, 0, 1, 1, ?)',
            (_lms_text(moment), track_id),
        )
    conn.commit()
    conn.close()
    monkeypatch.setenv('MUMA_SERVER_DB_PATH', str(path))
    monkeypatch.setenv('MUMA_SERVER_DB_ROOT', str(tmp_path / 'no-root'))
    return path


@pytest.fixture
def seeded(db):
    """Three muma tracks under /mnt/music, one shifted listen, one exact listen, none for the lost one."""
    ids = {}
    for name in ('shifted', 'exact', 'lost'):
        run_sql(db, 'INSERT INTO library_tracks (track_uid, title) VALUES (%s, %s)', (f'uid-{name}', name))
        ids[name] = run_sql(db, 'SELECT id FROM library_tracks WHERE track_uid = %s', (f'uid-{name}',))[0]['id']
        run_sql(
            db,
            'INSERT INTO library_media_files (file_path, file_path_hash, track_id) VALUES (%s, %s, %s)',
            (f'/mnt/music/Sets/{name}.mp3', f'hash-{name}', ids[name]),
        )
    run_sql(db, "SET time_zone = '+00:00'")
    try:
        # Shifted: created when the relay delivered it, listened_at moved later by an UPDATE.
        run_sql(
            db,
            'INSERT INTO scrobble_listens (track_id, listened_at, username, source, created_at) '
            "VALUES (%s, FROM_UNIXTIME(%s), 'user', 'lms', FROM_UNIXTIME(%s))",
            (ids['shifted'], _ts(SHIFTED_TO), _ts(PLAYED)),
        )
        run_sql(
            db,
            'INSERT INTO scrobble_listens (track_id, listened_at, username, source, created_at) '
            "VALUES (%s, FROM_UNIXTIME(%s), 'user', 'lms', FROM_UNIXTIME(%s))",
            (ids['exact'], _ts(EXACT), _ts(EXACT)),
        )
        # A ListenBrainz import LMS knows nothing about.
        run_sql(
            db,
            'INSERT INTO scrobble_listens (track_id, listened_at, username, source) '
            "VALUES (%s, FROM_UNIXTIME(%s), 'user', 'listenbrainz')",
            (ids['exact'], _ts(EXACT) - 86400),
        )
    finally:
        run_sql(db, 'SET time_zone = DEFAULT')
    return ids


def _listens(db):
    run_sql(db, "SET time_zone = '+00:00'")
    try:
        return run_sql(
            db,
            'SELECT track_id, UNIX_TIMESTAMP(listened_at) AS at, source, match_method '
            'FROM scrobble_listens ORDER BY track_id, listened_at',
        )
    finally:
        run_sql(db, 'SET time_zone = DEFAULT')


def test_the_dry_run_classifies_without_writing(api, headers, db, lms_db, seeded, utc_process):
    before = _listens(db)
    response = api.get('/api/scrobble/reconcile/lms', headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['zones']['consistent'] is True, body['zones']
    assert body['totals'] == {
        'exact': 1,
        'shifted': 1,
        'muma_only': 1,
        'lms_only': 1,
        'lms_only_insertable': 1,
        'lms_unmapped': 0,
    }
    shifted = body['sample']['shifted'][0]
    assert shifted['lms_listened_at'] == '2026-08-21T19:02:05Z'
    assert shifted['delta_seconds'] == _ts(SHIFTED_TO) - _ts(PLAYED)
    assert body['users'] == {'user': body['totals']}
    assert _listens(db) == before

    only_anna = api.get('/api/scrobble/reconcile/lms?username=anna', headers=headers).json()
    assert only_anna['totals']['shifted'] == 0


def test_apply_restores_the_time_inserts_the_lost_listen_and_is_idempotent(
    api, headers, db, lms_db, seeded, utc_process
):
    started = api.post(
        '/api/scrobble/reconcile/lms',
        headers=headers,
        json={'apply_shifted': True, 'insert_lms_only': True},
    )
    assert started.status_code == 200, started.text
    status = api.get('/api/scrobble/reconcile/lms/status', headers=headers).json()
    assert status['error'] is None, status
    assert status['running'] is False
    assert status['last']['written'] == {
        'shifted_fixed': 1,
        'lms_only_inserted': 1,
        'collisions': 0,
        'changed_since_read': 0,
    }

    rows = {(row['track_id'], row['at']): row for row in _listens(db)}
    assert (seeded['shifted'], _ts(PLAYED)) in rows
    assert (seeded['shifted'], _ts(SHIFTED_TO)) not in rows
    lost = rows[(seeded['lost'], _ts(LOST))]
    assert (lost['source'], lost['match_method']) == ('lms-reconcile', 'exact')

    # A second apply finds everything exact and writes nothing.
    before = _listens(db)
    api.post('/api/scrobble/reconcile/lms', headers=headers, json={'apply_shifted': True, 'insert_lms_only': True})
    again = api.get('/api/scrobble/reconcile/lms/status', headers=headers).json()['last']
    assert again['written'] == {'shifted_fixed': 0, 'lms_only_inserted': 0, 'collisions': 0, 'changed_since_read': 0}
    assert again['found']['exact'] == 3
    assert _listens(db) == before


def test_a_repair_onto_an_occupied_moment_is_skipped_and_counted(db, lms_db, seeded, utc_process, monkeypatch):
    """UNIQUE (username, listened_at, track_id): another row takes LMS's second between read and write."""
    from services.music_manager import scrobble_reconcile
    from services.music_manager.routers.users import lms_db_targets
    from tests.integration.conftest import _connect

    original = scrobble_reconcile._analyse

    def analyse_then_race(cursor, servers, username):
        """Classify, then let a relay insert the very listen the repair is about to write."""
        result = original(cursor, servers, username)
        run_sql(db, "SET time_zone = '+00:00'")
        try:
            run_sql(
                db,
                'INSERT INTO scrobble_listens (track_id, listened_at, username, source) '
                "VALUES (%s, FROM_UNIXTIME(%s), 'user', 'lms')",
                (seeded['shifted'], _ts(PLAYED)),
            )
        finally:
            run_sql(db, 'SET time_zone = DEFAULT')
        return result

    monkeypatch.setattr(scrobble_reconcile, '_analyse', analyse_then_race)
    conn = _connect()
    servers = scrobble_reconcile.open_servers(lms_db_targets())
    try:
        result = scrobble_reconcile.apply(conn, servers, None, apply_shifted=True, insert_lms_only=False)
    finally:
        for server_conn, _ in servers:
            server_conn.close()
        conn.close()
    assert result['written']['collisions'] == 1
    assert result['written']['shifted_fixed'] == 0
    # The shifted row is untouched and the racing row stands.
    at_times = sorted(row['at'] for row in _listens(db) if row['track_id'] == seeded['shifted'])
    assert at_times == [_ts(PLAYED), _ts(SHIFTED_TO)]


def test_without_an_lms_database_the_dry_run_is_a_503(api, headers, db, tmp_path, monkeypatch):
    monkeypatch.setenv('MUMA_SERVER_DB_PATH', str(tmp_path / 'missing.db'))
    monkeypatch.setenv('MUMA_SERVER_DB_ROOT', str(tmp_path / 'no-root'))
    assert os.path.exists(tmp_path / 'missing.db') is False
    assert api.get('/api/scrobble/reconcile/lms', headers=headers).status_code == 503


def test_the_backfill_loop_inserts_only_the_recent_lost_listen_once_and_never_repairs(db, lms_db, seeded, utc_process):
    """Bug report 075: the `lms-listen-backfill` round, against the real schema.

    A second lost listen, three days older, is as insertable as the recent one for a full-history
    run; the loop's window leaves it alone. The shifted row is inside the window's muma side but
    is never moved back: that stays the manual reconcile's job.
    """
    from services.music_manager import lms_listen_backfill as loop

    old_lost = _ts(LOST) - 3 * 86400
    lms = sqlite3.connect(lms_db)
    lms.execute(
        'INSERT INTO "listen" (date_time, backend, sync_state, user_id, track_id) VALUES (?, 0, 1, 1, 3)',
        (_lms_text(datetime.fromtimestamp(old_lost, tz=UTC)),),
    )
    lms.commit()
    lms.close()
    now = _ts(LOST) + 5 * 3600

    first = loop.run_once(now, 24 * 3600)
    assert first['written'] == {'lms_only_inserted': 1, 'collisions': 0}
    assert first['found']['shifted'] == 0
    rows = {(row['track_id'], row['at']): row for row in _listens(db)}
    assert rows[(seeded['lost'], _ts(LOST))]['source'] == 'lms-backfill'
    assert (seeded['lost'], old_lost) not in rows
    assert (seeded['shifted'], _ts(SHIFTED_TO)) in rows
    assert (seeded['shifted'], _ts(PLAYED)) not in rows

    before = _listens(db)
    second = loop.run_once(now + 900, 24 * 3600)
    assert second['written'] == {'lms_only_inserted': 0, 'collisions': 0}
    assert second['found']['exact'] == 1
    assert _listens(db) == before
