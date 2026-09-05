"""Coverage for the /api/feeds HTTP surface: auth, the 404/400/422 edges the
design pins explicitly, and that a non-ok state never carries tracks.

Auth is swapped out via FastAPI's own `app.dependency_overrides`, not by
patching `verify_api_key` as a module attribute: `Depends(verify_api_key)`
binds the function object at route-registration time, so reassigning the
module attribute afterwards has no effect on an already-built dependency
graph. `dependency_overrides` is the mechanism FastAPI provides for exactly
this. build_feed is still patched where this router looks it up (services.
music_manager.routers.feeds.build_feed), not where it is defined -- see
test_library_router.py.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.feeds.build import Feed
from services.music_manager.main import app
from services.music_manager.routers import feeds as feeds_router

client = TestClient(app)


class _ClosingConnection:
    """Stands in for a real connection: enough to prove a handler closed it
    without needing a real cursor. Every test that uses this instead of a bare
    object() asserts `.closed` at the end, so a reintroduced connection leak
    fails loudly rather than silently exhausting the pool in production."""

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FeedsAuthTestCase(unittest.TestCase):
    """Base class for anything that needs to stand in for verify_api_key."""

    def tearDown(self):
        app.dependency_overrides.pop(feeds_router.verify_api_key, None)
        super().tearDown()

    def _auth(self, auth: dict) -> None:
        app.dependency_overrides[feeds_router.verify_api_key] = lambda: auth


class FeedsRealAuthTest(unittest.TestCase):
    """Exercises the real `verify_api_key` body, not a dependency override.

    Every other test class here replaces the dependency wholesale, which never
    runs feeds.py's own system-key detection, its deferred `verify_token` call,
    or its `except Exception` rejection path -- a regression in any of those
    would leave the rest of this file green. Same pattern as
    test_library_router.py's LibraryAuthTest: a real system key, a patched
    `verify_token` for the user-key path, and a `side_effect` exception for the
    rejection path, all one level below `verify_api_key` itself.
    """

    def test_the_real_system_key_is_accepted(self):
        response = client.get('/api/feeds', headers={'X-API-Key': resolve_system_api_key()})
        self.assertEqual(response.status_code, 200)

    def test_a_user_key_that_verifies_is_accepted(self):
        with patch.object(
            users_router,
            'verify_token',
            return_value={'status': 'ok', 'type': 'user', 'user': {'username': 'user'}},
        ):
            response = client.get('/api/feeds', headers={'X-API-Key': 'user-key'})
        self.assertEqual(response.status_code, 200)

    def test_a_key_that_does_not_verify_is_rejected(self):
        with patch.object(users_router, 'verify_token', side_effect=Exception('nope')):
            response = client.get('/api/feeds', headers={'X-API-Key': 'bad'})
        self.assertEqual(response.status_code, 401)


class FeedsRouterTest(_FeedsAuthTestCase):
    def test_listing_the_feeds_needs_a_key(self):
        self.assertEqual(client.get('/api/feeds').status_code, 401)

    def test_listing_the_feeds_describes_every_policy(self):
        self._auth({'type': 'system'})
        response = client.get('/api/feeds', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        slugs = {feed['slug'] for feed in response.json()['feeds']}
        self.assertEqual(slugs, {'release-radar', 'daily-mix'})

    def test_an_unknown_slug_is_a_404(self):
        self._auth({'type': 'system'})
        response = client.get('/api/feeds/no-such-feed?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 404)

    def test_the_system_key_must_say_who_it_is_asking_for(self):
        self._auth({'type': 'system'})
        response = client.get('/api/feeds/release-radar', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 400)

    def test_an_empty_feed_is_a_state_and_never_an_empty_ok(self):
        empty = Feed(slug='release-radar', state='no_matches', scope='user', tracks=[], funnel={'candidates': 0})
        self._auth({'type': 'system'})
        conn = _ClosingConnection()
        with (
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=conn),
            patch('services.music_manager.routers.feeds.build_feed', return_value=empty),
        ):
            response = client.get('/api/feeds/release-radar?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['state'], 'no_matches')
        self.assertEqual(body['tracks'], [])
        self.assertTrue(conn.closed, 'the connection get_feed opened was never closed')

    def test_an_unknown_exclusion_type_is_refused(self):
        self._auth({'type': 'system'})
        response = client.put(
            '/api/feeds/profile/exclusions?username=user',
            json={'entity_type': 'bpm', 'entity_name': 'x', 'excluded': True},
            headers={'X-API-Key': 'k'},
        )
        self.assertEqual(response.status_code, 422)

    def test_a_user_key_cannot_read_someone_else_s_feed(self):
        self._auth({'type': 'user', 'user': {'username': 'user'}})
        seen = {}

        def fake_build(conn, username, policy, now):
            seen['username'] = username
            return Feed(slug=policy.slug, state='ok', scope='user', tracks=[], funnel={})

        conn = _ClosingConnection()
        with (
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=conn),
            patch('services.music_manager.routers.feeds.build_feed', side_effect=fake_build),
        ):
            client.get('/api/feeds/release-radar?username=someone-else', headers={'X-API-Key': 'k'})
        self.assertEqual(seen['username'], 'user')
        self.assertTrue(conn.closed, 'the connection get_feed opened was never closed')

    def test_a_missing_database_is_a_500(self):
        self._auth({'type': 'system'})
        with patch('services.music_manager.routers.feeds.get_db_connection', return_value=None):
            response = client.get('/api/feeds/release-radar?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 500)

    def test_an_ok_feed_carries_the_documented_track_shape_plus_bucket_and_reason(self):
        ok = Feed(
            slug='release-radar',
            state='ok',
            scope='user',
            tracks=[
                {
                    'id': 1,
                    'title': 'Track',
                    'track_uid': 'uid-1',
                    'artist': 'Someone',
                    'label': 'A Label',
                    'genres': ['uptempo'],
                    'duration_secs': 200,
                    'bpm': 180,
                    'release_date': '2026-09-01',
                    'file_path': '/music/1.flac',
                    'heard': False,
                    'has_label': True,
                    'is_soundcloud': False,
                    'rating': None,
                    'release_year': 2026,
                    'bucket': 'uptempo',
                    'reason': 'genre',
                }
            ],
            funnel={'candidates': 1, 'emitted': 1},
        )
        self._auth({'type': 'system'})
        conn = _ClosingConnection()
        with (
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=conn),
            patch('services.music_manager.routers.feeds.build_feed', return_value=ok),
        ):
            response = client.get('/api/feeds/release-radar?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        track = response.json()['tracks'][0]
        self.assertEqual(
            set(track),
            {
                'id',
                'title',
                'artist',
                'label',
                'genres',
                'duration_secs',
                'bpm',
                'release_date',
                'file_path',
                'bucket',
                'reason',
            },
        )
        self.assertEqual(track['bucket'], 'uptempo')
        self.assertEqual(track['reason'], 'genre')
        self.assertTrue(conn.closed, 'the connection get_feed opened was never closed')


class FeedsProfileRouterTest(_FeedsAuthTestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch('services.music_manager.routers.feeds.get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_profile_needs_a_key(self):
        self.assertEqual(client.get('/api/feeds/profile').status_code, 401)

    def test_the_system_key_must_say_who_it_is_asking_for(self):
        self._auth({'type': 'system'})
        response = client.get('/api/feeds/profile', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 400)

    def test_a_user_key_reads_its_own_profile(self):
        self._auth({'type': 'user', 'user': {'username': 'user'}})
        canned = MagicMock(scope='user', distinct_tracks=3, artists={'x': 1.0}, labels={}, genres={'uptempo': 1.0})
        self.cursor.fetchall.return_value = []
        with patch('services.music_manager.routers.feeds._taste_profile', return_value=canned) as taste:
            response = client.get('/api/feeds/profile?username=someone-else', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(taste.call_args.args[1], 'user')
        body = response.json()
        self.assertEqual(body['scope'], 'user')
        self.assertEqual(body['artists'], [{'name': 'x', 'affinity': 1.0}])
        self.assertEqual(body['excluded'], [])
        self.assertTrue(self.conn.close.called, 'the connection get_profile opened was never closed')

    def test_a_missing_database_is_a_500(self):
        self._auth({'type': 'system'})
        with patch('services.music_manager.routers.feeds.get_db_connection', return_value=None):
            response = client.get('/api/feeds/profile?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 500)


class FeedsExclusionsRouterTest(_FeedsAuthTestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.cursor = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor
        self.conn.cursor.return_value.__exit__.return_value = False
        patcher = patch('services.music_manager.routers.feeds.get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exclusions_need_a_key(self):
        response = client.put(
            '/api/feeds/profile/exclusions', json={'entity_type': 'label', 'entity_name': 'x', 'excluded': True}
        )
        self.assertEqual(response.status_code, 401)

    def test_excluding_a_label_writes_the_row(self):
        self._auth({'type': 'system'})
        response = client.put(
            '/api/feeds/profile/exclusions?username=user',
            json={'entity_type': 'label', 'entity_name': 'Neophyte Records', 'excluded': True},
            headers={'X-API-Key': 'k'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        statement, params = self.cursor.execute.call_args.args
        self.assertIn('INSERT', statement)
        self.assertEqual(params, ('user', 'label', 'neophyte records'))
        self.assertTrue(self.conn.close.called, 'the connection update_exclusion opened was never closed')

    def test_un_excluding_deletes_the_row(self):
        self._auth({'type': 'system'})
        response = client.put(
            '/api/feeds/profile/exclusions?username=user',
            json={'entity_type': 'artist', 'entity_name': 'Radium', 'excluded': False},
            headers={'X-API-Key': 'k'},
        )
        self.assertEqual(response.status_code, 200)
        statement, params = self.cursor.execute.call_args.args
        self.assertIn('DELETE', statement)
        self.assertEqual(params, ('user', 'artist', 'radium'))

    def test_a_user_key_cannot_write_someone_else_s_exclusion(self):
        self._auth({'type': 'user', 'user': {'username': 'user'}})
        client.put(
            '/api/feeds/profile/exclusions?username=someone-else',
            json={'entity_type': 'genre', 'entity_name': 'uptempo', 'excluded': True},
            headers={'X-API-Key': 'k'},
        )
        _, params = self.cursor.execute.call_args.args
        self.assertEqual(params, ('user', 'genre', 'uptempo'))


if __name__ == '__main__':
    unittest.main()
