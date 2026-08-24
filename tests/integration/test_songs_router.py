"""The two manual corrections, against a real MariaDB.

A pin has to beat the computation and survive the next pass; a split has to stay
split. Both are the whole point of the curation page, so both are proven here
rather than mocked.
"""
import pytest
from fastapi.testclient import TestClient

from services.music_manager import song_version_worker

pytestmark = pytest.mark.integration

HEADERS = {'X-API-Key': 'test-api-key'}


@pytest.fixture()
def client():
    from services.music_manager.main import app
    return TestClient(app)


@pytest.fixture()
def grouped(database):
    with database.cursor() as cursor:
        for table in ('library_track_labels', 'library_media_files', 'library_tracks',
                      'library_works', 'library_labels', 'library_artists'):
            cursor.execute(f'DELETE FROM {table}')
        cursor.execute('INSERT INTO library_artists (name) VALUES (%s)', ('Angerfist',))
        artist_id = cursor.lastrowid
        ids = {}
        for uid, title, path in (
            ('uid-radio', 'Raise Your Fist (Radio Edit)', '/mnt/music/a.mp3'),
            ('uid-ext', 'Raise Your Fist (Extended Mix)', '/mnt/music/b.mp3'),
        ):
            cursor.execute(
                'INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id) '
                'VALUES (%s, %s, %s, %s)',
                (uid, title, 300.0, artist_id),
            )
            track_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO library_media_files (file_path, file_path_hash, track_id, file_size, duration_secs) '
                'VALUES (%s, SHA2(%s, 256), %s, %s, %s)',
                (path, path, track_id, 7_200_000, 300.0),
            )
            ids[uid] = track_id
    database.commit()
    song_version_worker.group_once(database)

    with database.cursor() as cursor:
        cursor.execute('SELECT work_id FROM library_tracks WHERE id = %s', (ids['uid-radio'],))
        work_id = cursor.fetchone()['work_id']
    return {'work_id': work_id, **ids}


def _canonical(database, work_id):
    with database.cursor() as cursor:
        cursor.execute('SELECT canonical_track_id FROM library_works WHERE id = %s', (work_id,))
        return cursor.fetchone()['canonical_track_id']


def test_the_song_endpoint_lists_every_version_with_the_canonical_marked(client, grouped):
    response = client.get(f"/api/songs/{grouped['work_id']}", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert len(body['versions']) == 2
    canonical = [v for v in body['versions'] if v['is_canonical']]
    assert len(canonical) == 1
    assert canonical[0]['track_id'] == grouped['uid-radio']


def test_pinning_overrides_the_computed_canonical(client, database, grouped):
    response = client.post(
        f"/api/songs/{grouped['work_id']}/pin",
        json={'track_id': grouped['uid-ext']},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert _canonical(database, grouped['work_id']) == grouped['uid-ext']


def test_clearing_the_pin_hands_the_choice_back_to_the_rules(client, database, grouped):
    client.post(f"/api/songs/{grouped['work_id']}/pin",
                json={'track_id': grouped['uid-ext']}, headers=HEADERS)
    client.post(f"/api/songs/{grouped['work_id']}/pin",
                json={'track_id': None}, headers=HEADERS)
    assert _canonical(database, grouped['work_id']) == grouped['uid-radio']


def test_a_pin_on_a_track_from_another_work_is_refused(client, database, grouped):
    with database.cursor() as cursor:
        cursor.execute(
            'INSERT INTO library_tracks (track_uid, title, duration_secs) VALUES (%s, %s, %s)',
            ('uid-other', 'Stitches', 300.0),
        )
        stranger = cursor.lastrowid
    database.commit()

    response = client.post(f"/api/songs/{grouped['work_id']}/pin",
                           json={'track_id': stranger}, headers=HEADERS)
    assert response.status_code == 400


def test_splitting_gives_the_track_its_own_work_and_locks_it(client, database, grouped):
    response = client.post(f"/api/songs/tracks/{grouped['uid-ext']}/split", headers=HEADERS)
    assert response.status_code == 200

    with database.cursor() as cursor:
        cursor.execute('SELECT work_id, work_locked FROM library_tracks WHERE id = %s',
                       (grouped['uid-ext'],))
        row = cursor.fetchone()
    assert row['work_locked'] == 1
    assert row['work_id'] != grouped['work_id']


def test_a_split_survives_the_next_grouping_pass(client, database, grouped):
    client.post(f"/api/songs/tracks/{grouped['uid-ext']}/split", headers=HEADERS)
    song_version_worker.group_once(database)

    with database.cursor() as cursor:
        cursor.execute('SELECT work_id FROM library_tracks WHERE id = %s', (grouped['uid-ext'],))
        assert cursor.fetchone()['work_id'] != grouped['work_id']
