"""Coverage for the /api/feeds HTTP surface: auth, the 404/400/422 edges the
design pins explicitly, and that a non-ok state never carries tracks.

build_feed is patched where this router looks it up (services.music_manager.
routers.feeds.build_feed), not where it is defined -- see test_library_router.py.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from services.music_manager.feeds.build import Feed
from services.music_manager.main import app

client = TestClient(app)


class FeedsRouterTest(unittest.TestCase):
    def test_listing_the_feeds_needs_a_key(self):
        self.assertEqual(client.get('/api/feeds').status_code, 401)

    def test_listing_the_feeds_describes_every_policy(self):
        with patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}):
            response = client.get('/api/feeds', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        slugs = {feed['slug'] for feed in response.json()['feeds']}
        self.assertEqual(slugs, {'release-radar', 'daily-mix'})

    def test_an_unknown_slug_is_a_404(self):
        with patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}):
            response = client.get('/api/feeds/no-such-feed?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 404)

    def test_the_system_key_must_say_who_it_is_asking_for(self):
        with patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}):
            response = client.get('/api/feeds/release-radar', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 400)

    def test_an_empty_feed_is_a_state_and_never_an_empty_ok(self):
        empty = Feed(slug='release-radar', state='no_matches', scope='user', tracks=[], funnel={'candidates': 0})
        with (
            patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}),
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=object()),
            patch('services.music_manager.routers.feeds.build_feed', return_value=empty),
        ):
            response = client.get('/api/feeds/release-radar?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['state'], 'no_matches')
        self.assertEqual(body['tracks'], [])

    def test_an_unknown_exclusion_type_is_refused(self):
        with patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}):
            response = client.put(
                '/api/feeds/profile/exclusions?username=user',
                json={'entity_type': 'bpm', 'entity_name': 'x', 'excluded': True},
                headers={'X-API-Key': 'k'},
            )
        self.assertEqual(response.status_code, 422)

    def test_a_user_key_cannot_read_someone_else_s_feed(self):
        auth = {'type': 'user', 'user': {'username': 'user'}}
        seen = {}

        def fake_build(conn, username, policy, now):
            seen['username'] = username
            return Feed(slug=policy.slug, state='ok', scope='user', tracks=[], funnel={})

        with (
            patch('services.music_manager.routers.feeds.verify_api_key', return_value=auth),
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=object()),
            patch('services.music_manager.routers.feeds.build_feed', side_effect=fake_build),
        ):
            client.get('/api/feeds/release-radar?username=someone-else', headers={'X-API-Key': 'k'})
        self.assertEqual(seen['username'], 'user')

    def test_a_missing_database_is_a_500(self):
        with (
            patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}),
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=None),
        ):
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
        with (
            patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}),
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=object()),
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


class FeedsProfileRouterTest(unittest.TestCase):
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
        with patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}):
            response = client.get('/api/feeds/profile', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 400)

    def test_a_user_key_reads_its_own_profile(self):
        auth = {'type': 'user', 'user': {'username': 'user'}}
        canned = MagicMock(scope='user', distinct_tracks=3, artists={'x': 1.0}, labels={}, genres={'uptempo': 1.0})
        self.cursor.fetchall.return_value = []
        with (
            patch('services.music_manager.routers.feeds.verify_api_key', return_value=auth),
            patch('services.music_manager.routers.feeds._taste_profile', return_value=canned) as taste,
        ):
            response = client.get('/api/feeds/profile?username=someone-else', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(taste.call_args.args[1], 'user')
        body = response.json()
        self.assertEqual(body['scope'], 'user')
        self.assertEqual(body['artists'], [{'name': 'x', 'affinity': 1.0}])
        self.assertEqual(body['excluded'], [])

    def test_a_missing_database_is_a_500(self):
        with patch('services.music_manager.routers.feeds.get_db_connection', return_value=None):
            with patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}):
                response = client.get('/api/feeds/profile?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 500)


class FeedsExclusionsRouterTest(unittest.TestCase):
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
        with patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}):
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

    def test_un_excluding_deletes_the_row(self):
        with patch('services.music_manager.routers.feeds.verify_api_key', return_value={'type': 'system'}):
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
        auth = {'type': 'user', 'user': {'username': 'user'}}
        with patch('services.music_manager.routers.feeds.verify_api_key', return_value=auth):
            client.put(
                '/api/feeds/profile/exclusions?username=someone-else',
                json={'entity_type': 'genre', 'entity_name': 'uptempo', 'excluded': True},
                headers={'X-API-Key': 'k'},
            )
        statement, params = self.cursor.execute.call_args.args
        self.assertEqual(params, ('user', 'genre', 'uptempo'))


if __name__ == '__main__':
    unittest.main()
