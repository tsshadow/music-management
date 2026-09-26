"""Coverage for /api/songs: reading a song's versions, pinning one, splitting one off,
and the curation list behind the Versions page in Beheer.

The router is thin on purpose -- the ranking lives in song_versions.py and the SQL
in song_version_worker.py -- so what is pinned here is the contract a client
sees: the shape of a song, which mistakes are a 404 and which a 400, and that
every hand correction ends in the canonical being recomputed for exactly the
works it touched. A pin that saved without recomputing would be invisible until
the hourly worker happened to notice, which is the kind of silence the split
endpoint exists to remove.
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import songs as songs_router
from services.music_manager.song_version_worker import RankingContext
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    assert_atomic,
    assert_rolled_back,
    transaction_log,
)

API_KEY = resolve_system_api_key()
CONTEXT = RankingContext(prefer_lossless=True, label_tree_roots=('/mnt/music/EPs',))

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
        'file_path': '/mnt/music/EPs/Label/a.flac',
        'file_size': 30_000_000,
        'duration_secs': 300,
        'has_label': 0,
        'from_soundcloud': 0,
        'from_youtube': 0,
        'rating': 5,
        'plays': 12,
    },
    {
        'track_id': 22,
        'title': 'Raise Your Fist (Radio Edit)',
        'version_kind': 'radio',
        'version_score': 700,
        'canonical_track_id': 21,
        'file_path': '/mnt/music/Soundcloud/b.mp3',
        'file_size': 4_800_000,
        'duration_secs': 300,
        'has_label': 1,
        'from_soundcloud': 1,
        'from_youtube': 0,
        'rating': None,
        'plays': 0,
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
        context = patch.object(songs_router, 'ranking_context', return_value=CONTEXT)
        context.start()
        self.addCleanup(context.stop)


class ReadSongTest(SongsTestCase):
    rules = (
        ('FROM library_works w LEFT JOIN library_artists', (5,), WORK),
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
        self.assertEqual(body['versions'][0]['file_path'], '/mnt/music/EPs/Label/a.flac')

    def test_each_version_says_what_it_is_and_where_it_came_from(self):
        body = self.client.get('/api/songs/5', headers=self.headers).json()
        release, rip = body['versions']
        self.assertEqual(
            {k: release[k] for k in ('format', 'bitrate_kbps', 'source', 'is_official', 'rating', 'plays')},
            {'format': 'flac', 'bitrate_kbps': 800, 'source': 'label', 'is_official': True, 'rating': 5, 'plays': 12},
        )
        # A labelled SoundCloud rip is a rip: the archive says where the bytes came from.
        self.assertEqual((rip['source'], rip['is_official'], rip['bitrate_kbps']), ('soundcloud', False, 128))
        self.assertEqual(body['canonical_track_id'], 21)

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
    rules = (
        ('SELECT work_id FROM library_tracks WHERE id', (22,), {'work_id': 5}),
        ('SELECT id FROM library_works WHERE id', (5,), {'id': 5}),
        ('SELECT id FROM library_works WHERE id', (6,), {'id': 6}),
    )

    def test_pin_updates_the_work_and_recomputes_it(self):
        response = self.client.post('/api/songs/5/pin', json={'track_id': 22}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'status': 'ok', 'work_id': 5, 'pinned_track_id': 22})
        updates = self.cursor.statements_matching('UPDATE library_works SET pinned_track_id')
        self.assertEqual([params for _sql, params in updates], [(22, 5)])
        self.recompute.assert_called_once_with(self.cursor, {5})
        self.conn.commit.assert_called_once()

    def test_a_pin_clears_the_rescore_flag(self):
        self.client.post('/api/songs/5/pin', json={'track_id': 22}, headers=self.headers)
        sql = self.cursor.statements_matching('UPDATE library_works SET pinned_track_id')[0][0]
        self.assertIn('previous_canonical_track_id = NULL', sql)
        self.assertIn('canonical_changed_at = NULL', sql)

    def test_an_unknown_song_is_a_404(self):
        response = self.client.post('/api/songs/77/pin', json={'track_id': None}, headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.cursor.statements_matching('UPDATE'), [])

    def test_pinning_needs_rules_manage(self):
        with (
            patch('services.music_manager.routers.users.verify_api_key', return_value={'role': 'user'}),
            patch('services.music_manager.rbac.has_permission', return_value=False),
        ):
            response = self.client.post('/api/songs/5/pin', json={'track_id': 22}, headers=self.headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.cursor.statements_matching('UPDATE'), [])

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

    def test_the_old_pin_is_cleared_when_it_named_the_track_that_left(self):
        # A pin is a statement about one group. Left behind, it keeps deciding for a
        # work the track no longer belongs to, and the recompute follows it.
        self.client.post('/api/songs/tracks/22/split', headers=self.headers)

        cleared = self.cursor.statements_matching('SET pinned_track_id = NULL')
        self.assertEqual(len(cleared), 1)
        # Conditional on the pin naming this track, so another version's pin stays.
        self.assertIn('WHERE id = %s AND pinned_track_id = %s', cleared[0][0])
        self.assertEqual(cleared[0][1], (5, 22))

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


CURATION_ROW = {
    'id': 5,
    'title': 'Raise Your Fist',
    'artist': 'Angerfist',
    'version_count': 3,
    'canonical_track_id': 21,
    'canonical_title': 'Raise Your Fist (Radio Edit)',
    'pinned_track_id': None,
    'previous_canonical_track_id': 22,
    'canonical_changed_at': None,
}


class CurationListTest(SongsTestCase):
    rules = (
        ('SELECT COUNT(*) AS n', None, {'n': 120}),
        ('SELECT w.id, w.title', None, [CURATION_ROW]),
    )

    def test_lists_works_with_several_versions_paged(self):
        response = self.client.get('/api/songs/curation?page=3&page_size=10', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body['total'], body['page'], body['page_size']), (120, 3, 10))
        self.assertEqual(body['items'][0]['work_id'], 5)
        self.assertEqual(body['items'][0]['version_count'], 3)
        sql, params = self.cursor.statements_matching('SELECT w.id, w.title')[0]
        self.assertIn('HAVING COUNT(*) > 1', sql)
        self.assertEqual(params[-2:], (10, 20))

    def test_search_matches_title_and_artist(self):
        self.client.get('/api/songs/curation?q=fist', headers=self.headers)
        _sql, params = self.cursor.statements_matching('SELECT COUNT(*) AS n')[0]
        self.assertEqual(params, ('fist', '%fist%', '%fist%', 0))

    def test_sorting_by_recent_change_puts_unchanged_works_last(self):
        self.client.get('/api/songs/curation?sort=changed&changed_only=true', headers=self.headers)
        sql, params = self.cursor.statements_matching('SELECT w.id, w.title')[0]
        # The sort is a bound parameter read by CASE, never text in the statement.
        self.assertIn("CASE WHEN %s = 'changed' THEN w.canonical_changed_at IS NULL END ASC", sql)
        self.assertEqual(params[3], 1)
        self.assertEqual(params[4:8], ('changed',) * 4)

    def test_sorting_by_version_count_is_the_default(self):
        self.client.get('/api/songs/curation', headers=self.headers)
        sql, params = self.cursor.statements_matching('SELECT w.id, w.title')[0]
        self.assertIn("CASE WHEN %s = 'versions' THEN counted.version_count END DESC", sql)
        self.assertEqual(params[4], 'versions')

    def test_an_unknown_sort_is_refused_not_interpolated(self):
        response = self.client.get('/api/songs/curation?sort=id;DROP', headers=self.headers)
        self.assertEqual(response.status_code, 422)

    def test_the_page_size_is_capped(self):
        response = self.client.get('/api/songs/curation?page_size=1000', headers=self.headers)
        self.assertEqual(response.status_code, 422)

    def test_requires_a_key(self):
        self.assertEqual(self.client.get('/api/songs/curation').status_code, 401)


class RankingStatusTest(SongsTestCase):
    rules = (('FROM library_works', None, {'pending': 7, 'changed': 3}),)

    def test_reports_the_signature_and_the_counts(self):
        body = self.client.get('/api/songs/ranking', headers=self.headers).json()
        self.assertEqual(
            body,
            {'signature': CONTEXT.signature, 'prefer_lossless': True, 'pending_works': 7, 'changed_works': 3},
        )


class DismissChangeTest(SongsTestCase):
    rules = (('SELECT id FROM library_works WHERE id', (5,), {'id': 5}),)

    def test_clears_the_flag_and_keeps_the_canonical(self):
        response = self.client.post('/api/songs/5/dismiss-change', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        ((sql, params),) = self.cursor.statements_matching('UPDATE library_works')
        self.assertIn('canonical_changed_at = NULL', sql)
        self.assertNotIn('canonical_track_id =', sql.replace('previous_canonical_track_id', ''))
        self.assertEqual(params, (5,))
        self.conn.commit.assert_called_once()

    def test_an_unknown_song_is_a_404(self):
        response = self.client.post('/api/songs/9/dismiss-change', headers=self.headers)
        self.assertEqual(response.status_code, 404)


class DatabaseDownTest(unittest.TestCase):
    def test_every_endpoint_answers_503_without_a_connection(self):
        client = TestClient(app)
        headers = {'x-api-key': API_KEY}
        with patch.object(songs_router, 'get_db_connection', return_value=None):
            self.assertEqual(client.get('/api/songs/5', headers=headers).status_code, 503)
            self.assertEqual(client.post('/api/songs/5/pin', json={'track_id': 1}, headers=headers).status_code, 503)
            self.assertEqual(client.post('/api/songs/tracks/1/split', headers=headers).status_code, 503)


class PinAtomicityTest(SongsTestCase):
    """The pin and the canonical recompute it triggers are one transaction."""

    rules = PinVersionTest.rules

    def test_the_pin_is_written_inside_a_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.recompute.side_effect = lambda *_a: log.append('RECOMPUTE')
        response = self.client.post('/api/songs/5/pin', json={'track_id': 22}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        assert_atomic(self, log, 'UPDATE library_works SET pinned_track_id', 'RECOMPUTE')


class SplitAtomicityTest(SongsTestCase):
    """A split's new work, the moved track and the recompute land together."""

    rules = SplitTrackTest.rules
    lastrowid = SplitTrackTest.lastrowid

    def test_the_split_is_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.post('/api/songs/tracks/22/split', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        assert_atomic(self, log, 'INSERT INTO library_works', 'UPDATE library_tracks SET work_id')

    def test_a_failing_recompute_rolls_the_split_back(self):
        log = transaction_log(self.conn, self.cursor)
        self.recompute.side_effect = RuntimeError('deadlock')
        with self.assertRaises(RuntimeError):
            self.client.post('/api/songs/tracks/22/split', headers=self.headers)
        assert_rolled_back(self, log)


if __name__ == '__main__':
    unittest.main()
