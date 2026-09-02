"""Coverage for /api/songs: reading a song's versions, pinning one, splitting one off.

The router is thin on purpose -- the ranking lives in song_versions.py and the SQL
in song_version_worker.py -- so what is pinned here is the contract a client
sees: the shape of a song, which mistakes are a 404 and which a 400, and that
every hand correction ends in the canonical being recomputed for exactly the
works it touched. A pin that saved without recomputing would be invisible until
the hourly worker happened to notice, which is the kind of silence the split
endpoint exists to remove.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import songs as songs_router
from services.music_manager.tests.scripted_cursor import ScriptedCursor

API_KEY = resolve_system_api_key()

WORK = {
    'id': 5,
    'title': 'Raise Your Fist',
    'work_key': 'angerfist|raise your fist',
    'canonical_track_id': 21,
    'pinned_track_id': None,
}
VERSIONS = [
    {
        'track_id': 21,
        'title': 'Raise Your Fist (Extended Mix)',
        'version_kind': 'extended',
        'version_score': 900,
        'canonical_track_id': 21,
        'file_path': '/mnt/music/a.flac',
    },
    {
        'track_id': 22,
        'title': 'Raise Your Fist (Radio Edit)',
        'version_kind': 'radio',
        'version_score': 700,
        'canonical_track_id': 21,
        'file_path': '/mnt/music/b.mp3',
    },
]


class SongsTestCase(unittest.TestCase):
    rules = ()
    lastrowid = None

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.cursor = ScriptedCursor(self.rules, lastrowid=self.lastrowid)
        self.conn = MagicMock()
        self.conn.cursor.return_value = self.cursor
        patcher = patch.object(songs_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        recompute = patch.object(songs_router, 'recompute_canonicals')
        self.recompute = recompute.start()
        self.addCleanup(recompute.stop)


class ReadSongTest(SongsTestCase):
    rules = (
        ('FROM library_works WHERE id', (5,), WORK),
        ('JOIN library_works w', (5,), VERSIONS),
    )

    def test_song_lists_its_versions_and_marks_the_canonical(self):
        response = self.client.get('/api/songs/5', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['work_id'], 5)
        self.assertEqual(body['title'], 'Raise Your Fist')
        self.assertIsNone(body['pinned_track_id'])
        self.assertEqual([v['track_id'] for v in body['versions']], [21, 22])
        self.assertEqual([v['is_canonical'] for v in body['versions']], [True, False])
        # The file path is what the UI links to; a version without one is a row
        # the scanner has not attached a file to, and that has to be visible.
        self.assertEqual(body['versions'][0]['file_path'], '/mnt/music/a.flac')

    def test_unknown_song_is_a_404(self):
        response = self.client.get('/api/songs/999', headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_requires_a_key(self):
        response = self.client.get('/api/songs/5')
        self.assertEqual(response.status_code, 401)

    def test_connection_always_closed(self):
        self.client.get('/api/songs/999', headers=self.headers)
        self.conn.close.assert_called_once()


class PinVersionTest(SongsTestCase):
    rules = (('SELECT work_id FROM library_tracks WHERE id', (22,), {'work_id': 5}),)

    def test_pin_updates_the_work_and_recomputes_it(self):
        response = self.client.post('/api/songs/5/pin', json={'track_id': 22}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'status': 'ok', 'work_id': 5, 'pinned_track_id': 22})
        updates = self.cursor.statements_matching('UPDATE library_works SET pinned_track_id')
        self.assertEqual([params for _sql, params in updates], [(22, 5)])
        self.recompute.assert_called_once_with(self.cursor, {5})
        self.conn.commit.assert_called_once()

    def test_clearing_the_pin_sends_null_and_still_recomputes(self):
        # A cleared pin has to hand the choice back to the ranking; skipping the
        # recompute would leave the old pinned track as canonical forever.
        response = self.client.post('/api/songs/5/pin', json={'track_id': None}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        updates = self.cursor.statements_matching('UPDATE library_works SET pinned_track_id')
        self.assertEqual([params for _sql, params in updates], [(None, 5)])
        self.recompute.assert_called_once_with(self.cursor, {5})

    def test_a_track_that_does_not_exist_is_a_404(self):
        response = self.client.post('/api/songs/5/pin', json={'track_id': 404}, headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.cursor.statements_matching('UPDATE'), [])
        self.recompute.assert_not_called()

    def test_a_track_from_another_song_is_a_400(self):
        # The distinction matters to the UI: 404 is a stale page, 400 is a
        # request that can never be right and must not be retried.
        response = self.client.post('/api/songs/6/pin', json={'track_id': 22}, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('different song', response.json()['detail'])
        self.assertEqual(self.cursor.statements_matching('UPDATE'), [])
        self.conn.commit.assert_not_called()


class SplitTrackTest(SongsTestCase):
    rules = (
        (
            'SELECT work_id, title, primary_artist_id FROM library_tracks',
            (22,),
            {'work_id': 5, 'title': 'Raise Your Fist (Radio Edit)', 'primary_artist_id': 7},
        ),
    )
    lastrowid = 80

    def test_split_gives_the_track_its_own_locked_work(self):
        response = self.client.post('/api/songs/tracks/22/split', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'status': 'ok', 'track_id': 22, 'work_id': 80})

        inserts = self.cursor.statements_matching('INSERT INTO library_works')
        self.assertEqual(len(inserts), 1)
        # The key carries the track id so it can never collide with the group it
        # left, nor with another split; the title and artist are the track's own.
        self.assertEqual(inserts[0][1], ('split:22', 'Raise Your Fist (Radio Edit)', 7))

        moves = self.cursor.statements_matching('UPDATE library_tracks SET work_id')
        self.assertEqual(len(moves), 1)
        self.assertIn('work_locked = 1', moves[0][0])
        self.assertEqual(moves[0][1], (80, 22))

    def test_both_the_old_and_the_new_work_are_recomputed(self):
        # The old group lost a candidate and may need a new canonical; the new
        # one has exactly one and needs it set. Missing either leaves a stale
        # canonical pointing at a track that is no longer in that work.
        self.client.post('/api/songs/tracks/22/split', headers=self.headers)
        self.recompute.assert_called_once_with(self.cursor, {5, 80})
        self.conn.commit.assert_called_once()

    def test_unknown_track_is_a_404_and_writes_nothing(self):
        response = self.client.post('/api/songs/tracks/404/split', headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.cursor.statements_matching('INSERT'), [])
        self.recompute.assert_not_called()
        self.conn.commit.assert_not_called()


class UngroupedTrackSplitTest(SongsTestCase):
    """A track the worker has not reached yet has no old work to recompute."""

    rules = (
        (
            'SELECT work_id, title, primary_artist_id FROM library_tracks',
            (23,),
            {'work_id': None, 'title': 'Loose Track', 'primary_artist_id': None},
        ),
    )
    lastrowid = 81

    def test_only_the_new_work_is_recomputed(self):
        response = self.client.post('/api/songs/tracks/23/split', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.recompute.assert_called_once_with(self.cursor, {81})


class DatabaseDownTest(unittest.TestCase):
    def test_every_endpoint_answers_503_without_a_connection(self):
        client = TestClient(app)
        headers = {'x-api-key': API_KEY}
        with patch.object(songs_router, 'get_db_connection', return_value=None):
            self.assertEqual(client.get('/api/songs/5', headers=headers).status_code, 503)
            self.assertEqual(client.post('/api/songs/5/pin', json={'track_id': 1}, headers=headers).status_code, 503)
            self.assertEqual(client.post('/api/songs/tracks/1/split', headers=headers).status_code, 503)


if __name__ == '__main__':
    unittest.main()
