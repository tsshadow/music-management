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

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.feeds.build import Feed
from services.music_manager.main import app
from services.music_manager.routers import feeds as feeds_router

pytestmark = pytest.mark.mock_base('DatabaseConnector')

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


def _serve_live(conn, username, slug, now, params_key, build):
    """`serve_snapshot` with the table taken out: always builds, never reads or writes.

    The tests below are about the router's shape -- auth, status codes, the body --
    against connections that have no cursor at all. What the snapshot does with a
    cursor is test_feeds_snapshot.py's subject; FeedsSnapshotRouterTest covers the
    one seam between the two.
    """
    return build(), 'live'


class _LiveFeedsMixin:
    """Bypasses the snapshot table for the duration of each test."""

    def setUp(self):
        super().setUp()
        patcher = patch('services.music_manager.routers.feeds.serve_snapshot', side_effect=_serve_live)
        patcher.start()
        self.addCleanup(patcher.stop)
        # params_key reads exclusions and genre hardness through a cursor these
        # connections do not have; ParamsKeyTest covers what it reads.
        key_patcher = patch('services.music_manager.routers.feeds.params_key', return_value='k')
        key_patcher.start()
        self.addCleanup(key_patcher.stop)
        # The system key's username is resolved to the account's spelling through a cursor
        # these connections do not have; test_username_case.py covers that lookup.
        canonical_patcher = patch('services.music_manager.routers.feeds._canonical', side_effect=lambda name: name)
        canonical_patcher.start()
        self.addCleanup(canonical_patcher.stop)


class _FeedsAuthTestCase(_LiveFeedsMixin, unittest.TestCase):
    """Base class for anything that needs to stand in for verify_api_key."""

    def tearDown(self):
        app.dependency_overrides.pop(feeds_router.verify_api_key, None)
        super().tearDown()

    def _auth(self, auth: dict) -> None:
        app.dependency_overrides[feeds_router.verify_api_key] = lambda: auth


class FeedsRealAuthTest(_LiveFeedsMixin, unittest.TestCase):
    """Exercises the real `verify_api_key` body, not a dependency override.

    Every other test class here replaces the dependency wholesale, which never
    runs the canonical `users.verify_api_key` feeds.py delegates to: its
    system-key detection, its `verify_token` call, or the rejection verify_token
    raises -- a regression in any of those would leave the rest of this file
    green. A real system key, a patched `verify_token` for the user-key path,
    and verify_token's own `HTTPException` for the rejection path, all one level
    below `verify_api_key` itself.
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
        """A key no account holds is unauthenticated: the canonical users.verify_api_key
        answers 401, as tests/bdd/features/access_control.feature requires (bug report 052)."""
        rejection = HTTPException(status_code=403, detail='Invalid API Key')
        with patch.object(users_router, 'verify_token', side_effect=rejection):
            response = client.get('/api/feeds', headers={'X-API-Key': 'bad'})
        self.assertEqual(response.status_code, 401)

    def test_a_disabled_account_is_passed_through_as_403(self):
        rejection = HTTPException(status_code=403, detail='Account disabled')
        with patch.object(users_router, 'verify_token', side_effect=rejection):
            response = client.get('/api/feeds', headers={'X-API-Key': 'disabled'})
        self.assertEqual(response.status_code, 403)

    def test_a_missing_key_is_a_401(self):
        self.assertEqual(client.get('/api/feeds').status_code, 401)


class FeedsRouterTest(_FeedsAuthTestCase):
    def test_listing_the_feeds_needs_a_key(self):
        self.assertEqual(client.get('/api/feeds').status_code, 401)

    def test_listing_the_feeds_describes_every_policy(self):
        """'daily-mix' is listed too -- it is its own policy now (the classic,

        unrestricted mix), not a duplicate of daily-mix-mid, so there is
        nothing to hide it behind.
        """
        self._auth({'type': 'system'})
        response = client.get('/api/feeds', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        slugs = {feed['slug'] for feed in response.json()['feeds']}
        self.assertEqual(
            slugs,
            {
                'release-radar',
                'daily-mix',
                'daily-mix-soft',
                'daily-mix-mid',
                'daily-mix-hard',
                'daily-mix-artist',
                'daily-mix-label',
            },
        )

    def test_listing_the_feeds_without_a_username_still_answers(self):
        """A system key may list feeds with no listener in mind at all -- every

        entry falls back to a generic title rather than the endpoint failing or
        silently querying a database connection it has no username to ask about.
        """
        self._auth({'type': 'system'})
        response = client.get('/api/feeds', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        feeds = {feed['slug']: feed for feed in response.json()['feeds']}
        self.assertEqual(feeds['daily-mix-soft']['title'], 'Zachter')
        self.assertEqual(feeds['daily-mix']['title'], 'Klassiek')

    def test_listing_the_feeds_calls_describe_feed_per_policy_for_a_known_user(self):
        """`GET /api/feeds` and `GET /api/feeds/{slug}` must describe a feed the

        same way -- `describe_feed` is the one implementation both go through,
        the same reason `resolve_profile` exists for steps 1-3. But the profile is
        resolved once for the whole listing and handed to every describe: seven
        resolutions of the same 90-day history were most of what opening Home
        cost (docs/designs/feeds/home-load.md).
        """
        self._auth({'type': 'system'})
        conn = _ClosingConnection()
        resolution = object()
        with (
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=conn),
            patch('services.music_manager.routers.feeds.resolve_profile', return_value=resolution) as resolve,
            patch(
                'services.music_manager.routers.feeds.describe_feed',
                return_value={'title': 'Aangepast', 'subtitle': 'Testwaarde'},
            ) as describe,
        ):
            response = client.get('/api/feeds?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        feeds = response.json()['feeds']
        self.assertTrue(feeds)
        self.assertTrue(all(feed['title'] == 'Aangepast' for feed in feeds))
        self.assertEqual(describe.call_count, len(feeds))
        self.assertEqual(resolve.call_count, 1)
        self.assertTrue(all(call.kwargs['resolution'] is resolution for call in describe.call_args_list))
        self.assertTrue(conn.closed)

    def test_listing_the_feeds_for_a_user_key_uses_its_own_username(self):
        self._auth({'type': 'user', 'user': {'username': 'user'}})
        with patch('services.music_manager.routers.feeds.get_db_connection', return_value=None):
            response = client.get('/api/feeds', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['feeds'])

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

    def test_a_hardness_band_feed_carries_its_edges_title_and_relaxation(self):
        banded = Feed(
            slug='daily-mix-mid',
            state='ok',
            scope='user',
            tracks=[],
            funnel={'candidates': 3, 'emitted': 3},
            title='Middenin',
            subtitle='50–75 hardheid',
            hardness_band=(50.0, 75.0),
            hardness_edges_source='default',
            hardness_source_counts={'genre': 2, 'none': 1},
            hardness_percentiles={'p33': 40.0, 'p50': 55.0, 'p67': 70.0},
            relaxed_to='none',
        )
        self._auth({'type': 'system'})
        conn = _ClosingConnection()
        with (
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=conn),
            patch('services.music_manager.routers.feeds.build_feed', return_value=banded),
        ):
            response = client.get('/api/feeds/daily-mix-mid?username=user', headers={'X-API-Key': 'k'})
        body = response.json()
        self.assertEqual(body['title'], 'Middenin')
        self.assertEqual(body['subtitle'], '50–75 hardheid')
        self.assertEqual(body['hardness_band'], [50.0, 75.0])
        self.assertEqual(body['hardness_edges_source'], 'default')
        self.assertEqual(body['hardness_source_counts'], {'genre': 2, 'none': 1})
        self.assertEqual(body['hardness_percentiles'], {'p33': 40.0, 'p50': 55.0, 'p67': 70.0})
        self.assertEqual(body['relaxed_to'], 'none')

    def test_a_feed_with_no_band_reports_null_rather_than_an_empty_placeholder(self):
        plain = Feed(slug='release-radar', state='ok', scope='user', tracks=[], funnel={}, title='Release Radar')
        self._auth({'type': 'system'})
        conn = _ClosingConnection()
        with (
            patch('services.music_manager.routers.feeds.get_db_connection', return_value=conn),
            patch('services.music_manager.routers.feeds.build_feed', return_value=plain),
        ):
            response = client.get('/api/feeds/release-radar?username=user', headers={'X-API-Key': 'k'})
        body = response.json()
        self.assertEqual(body['title'], 'Release Radar')
        self.assertIsNone(body['subtitle'])
        self.assertIsNone(body['hardness_band'])
        self.assertIsNone(body['hardness_edges_source'])
        self.assertIsNone(body['hardness_percentiles'])
        self.assertIsNone(body['relaxed_to'])

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
                    'file_path': '/mnt/music/EPs/Label/01.mp3',
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
                'library_path',
                'bucket',
                'reason',
                'work_id',
            },
        )
        self.assertEqual(track['bucket'], 'uptempo')
        self.assertEqual(track['reason'], 'genre')
        # The path a client hands to LMS's getSongsByPath: library-relative, because muma's
        # own absolute spelling names a file LMS does not have.
        self.assertEqual(track['library_path'], 'EPs/Label/01.mp3')
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
        with patch(
            'services.music_manager.routers.feeds.resolve_profile', return_value=MagicMock(profile=canned)
        ) as resolve:
            response = client.get('/api/feeds/profile?username=someone-else', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(resolve.call_args.args[1], 'user')
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
        statement, params = self._exclusion_statement()
        self.assertIn('INSERT', statement)
        self.assertEqual(params, ('user', 'label', 'neophyte records'))
        self.assertTrue(self.conn.close.called, 'the connection update_exclusion opened was never closed')

    def test_changing_an_exclusion_drops_the_listener_s_snapshots(self):
        """The snapshots were built from a profile the exclusion has just changed;
        serving them on would keep the excluded entity's influence for the rest of
        the day."""
        self._auth({'type': 'system'})
        client.put(
            '/api/feeds/profile/exclusions?username=user',
            json={'entity_type': 'label', 'entity_name': 'x', 'excluded': True},
            headers={'X-API-Key': 'k'},
        )
        statements = [call.args for call in self.cursor.execute.call_args_list]
        self.assertIn(('DELETE FROM feeds_snapshot WHERE username = %s', ('user',)), statements)

    def _exclusion_statement(self):
        calls = [call.args for call in self.cursor.execute.call_args_list if 'feeds_profile_exclusions' in call.args[0]]
        self.assertTrue(calls, 'no statement touched feeds_profile_exclusions')
        return calls[-1]

    def test_un_excluding_deletes_the_row(self):
        self._auth({'type': 'system'})
        response = client.put(
            '/api/feeds/profile/exclusions?username=user',
            json={'entity_type': 'artist', 'entity_name': 'Radium', 'excluded': False},
            headers={'X-API-Key': 'k'},
        )
        self.assertEqual(response.status_code, 200)
        statement, params = self._exclusion_statement()
        self.assertIn('DELETE', statement)
        self.assertEqual(params, ('user', 'artist', 'radium'))

    def test_a_user_key_cannot_write_someone_else_s_exclusion(self):
        self._auth({'type': 'user', 'user': {'username': 'user'}})
        client.put(
            '/api/feeds/profile/exclusions?username=someone-else',
            json={'entity_type': 'genre', 'entity_name': 'uptempo', 'excluded': True},
            headers={'X-API-Key': 'k'},
        )
        _, params = self._exclusion_statement()
        self.assertEqual(params, ('user', 'genre', 'uptempo'))


class FeedsSnapshotRouterTest(unittest.TestCase):
    """The one seam between the router and the snapshot: what the router asks
    `serve_snapshot` for, and what it does with the answer. The snapshot's own
    freshness and locking live in test_feeds_snapshot.py."""

    def setUp(self):
        app.dependency_overrides[feeds_router.verify_api_key] = lambda: {'type': 'system'}
        self.conn = _ClosingConnection()
        patcher = patch('services.music_manager.routers.feeds.get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        key_patcher = patch('services.music_manager.routers.feeds.params_key', return_value='k')
        key_patcher.start()
        self.addCleanup(key_patcher.stop)
        # The system key's username is resolved to the account's spelling through a cursor
        # these connections do not have; test_username_case.py covers that lookup.
        canonical_patcher = patch('services.music_manager.routers.feeds._canonical', side_effect=lambda name: name)
        canonical_patcher.start()
        self.addCleanup(canonical_patcher.stop)

    def tearDown(self):
        app.dependency_overrides.pop(feeds_router.verify_api_key, None)

    def _stored(self, tracks):
        return {
            'slug': 'daily-mix-mid',
            'state': 'ok',
            'scope': 'user',
            'generated_at': '2026-09-18T00:05:00',
            'tracks': tracks,
            'funnel': {},
            'title': 'Middenin',
            'subtitle': None,
            'hardness_band': [50.0, 75.0],
            'hardness_edges_source': 'default',
            'hardness_source_counts': None,
            'hardness_percentiles': None,
            'relaxed_to': None,
            'filled_from_unknown': None,
        }

    def test_a_fresh_snapshot_answers_without_a_build(self):
        stored = self._stored([{'id': n} for n in range(30)])
        with (
            patch('services.music_manager.routers.feeds.serve_snapshot', return_value=(stored, 'snapshot')) as serve,
            patch('services.music_manager.routers.feeds.build_feed') as build,
        ):
            response = client.get('/api/feeds/daily-mix-mid?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-MuMa-Feed-Source'], 'snapshot')
        self.assertEqual(len(response.json()['tracks']), 30)
        build.assert_not_called()
        conn, username, slug = serve.call_args.args[:3]
        self.assertIs(conn, self.conn)
        self.assertEqual((username, slug), ('user', 'daily-mix-mid'))
        self.assertTrue(self.conn.closed)

    def test_a_smaller_limit_is_the_head_of_the_snapshot(self):
        """The Home row shows the top of the page it links to -- the same
        ranking cut shorter, not a second allocation over ten places."""
        stored = self._stored([{'id': n} for n in range(30)])
        with patch('services.music_manager.routers.feeds.serve_snapshot', return_value=(stored, 'snapshot')):
            response = client.get('/api/feeds/daily-mix-mid?username=user&limit=10', headers={'X-API-Key': 'k'})
        self.assertEqual([track['id'] for track in response.json()['tracks']], list(range(10)))

    def test_the_head_says_where_the_next_page_starts(self):
        stored = self._stored([{'id': n} for n in range(100)])
        with patch('services.music_manager.routers.feeds.serve_snapshot', return_value=(stored, 'snapshot')):
            whole = client.get('/api/feeds/daily-mix-mid?username=user', headers={'X-API-Key': 'k'}).json()
            head = client.get('/api/feeds/daily-mix-mid?username=user&limit=10', headers={'X-API-Key': 'k'}).json()
        self.assertEqual((len(whole['tracks']), whole['offset'], whole['next_offset']), (100, 0, 100))
        self.assertEqual(head['next_offset'], 10)

    def test_an_exhausted_feed_has_no_next_page_and_does_not_leak_the_flag(self):
        stored = {**self._stored([{'id': n} for n in range(40)]), 'exhausted': True}
        with (
            patch('services.music_manager.routers.feeds.serve_snapshot', return_value=(stored, 'snapshot')),
            patch('services.music_manager.routers.feeds.extend_snapshot') as extend,
        ):
            body = client.get('/api/feeds/daily-mix-mid?username=user&offset=40', headers={'X-API-Key': 'k'}).json()
        self.assertEqual((body['tracks'], body['next_offset']), ([], None))
        self.assertNotIn('exhausted', body)
        extend.assert_not_called()

    def _continue(self, stored, built_tracks, query):
        """One request past the stored list, with the continuation run for real
        against `stored` and a build that returns `built_tracks`."""
        grown = {}

        def extend(conn, username, slug, now, key, grow):
            grown['payload'] = grow(stored)
            return grown['payload']

        feed = Feed(slug='daily-mix-mid', state='ok', scope='user', tracks=built_tracks, funnel={}, title='Middenin')
        with (
            patch('services.music_manager.routers.feeds.serve_snapshot', return_value=(stored, 'snapshot')),
            patch('services.music_manager.routers.feeds.extend_snapshot', side_effect=extend),
            patch('services.music_manager.routers.feeds.build_feed', return_value=feed) as build,
        ):
            response = client.get(f'/api/feeds/daily-mix-mid?username=user&{query}', headers={'X-API-Key': 'k'})
        return response, build, grown.get('payload')

    def test_the_next_page_continues_the_feed_without_repeating_a_song(self):
        stored = self._stored([{'id': n, 'work_id': 1000 + n} for n in range(100)])
        # The bigger build re-ranks: the stored songs come back, one under another
        # version's id (work 1005), and 99 songs are new.
        built = (
            [{'id': 500, 'work_id': 1005}]
            + [{'id': n, 'work_id': 1000 + n} for n in range(100)]
            + [{'id': n, 'work_id': 1000 + n} for n in range(100, 199)]
        )
        response, build, grown = self._continue(stored, built, 'offset=100&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-MuMa-Feed-Source'], 'extended')
        body = response.json()
        self.assertEqual([track['id'] for track in body['tracks']], list(range(100, 199)))
        self.assertEqual((body['offset'], body['next_offset']), (100, 200))
        # The same ranker at more places: the stored 100 plus a page.
        self.assertEqual(build.call_args.args[2].size, 200)
        self.assertEqual([track['id'] for track in grown['tracks'][:100]], list(range(100)))
        self.assertFalse(grown['exhausted'])

    def test_a_continuation_that_finds_nothing_new_marks_the_feed_exhausted(self):
        stored = self._stored([{'id': n, 'work_id': None} for n in range(30)])
        response, _build, grown = self._continue(stored, [{'id': n} for n in range(30)], 'offset=30')
        body = response.json()
        self.assertEqual((body['tracks'], body['next_offset']), ([], None))
        self.assertTrue(grown['exhausted'])

    def test_a_short_continuation_is_the_last_one(self):
        """A build shorter than it was asked for has used every candidate."""
        stored = self._stored([{'id': n} for n in range(100)])
        built = [{'id': n} for n in range(120)]
        response, _build, grown = self._continue(stored, built, 'offset=100')
        body = response.json()
        self.assertEqual([track['id'] for track in body['tracks']], list(range(100, 120)))
        self.assertTrue(grown['exhausted'])
        self.assertIsNone(body['next_offset'])

    def _head_of_a_build(self, count, allocated):
        feed = Feed(
            slug='daily-mix',
            state='ok',
            scope='user',
            tracks=[{'id': n} for n in range(count)],
            funnel={'allocated': allocated},
            title='Klassiek',
        )
        with (
            patch('services.music_manager.routers.feeds.serve_snapshot', side_effect=_serve_live),
            patch('services.music_manager.routers.feeds.build_feed', return_value=feed),
        ):
            return client.get('/api/feeds/daily-mix?username=user', headers={'X-API-Key': 'k'}).json()

    def test_a_feed_that_ran_out_of_candidates_offers_no_next_page(self):
        """40 of 100 because only 40 qualified: a continuation build would only find the same 40."""
        body = self._head_of_a_build(40, allocated=40)
        self.assertEqual((len(body['tracks']), body['next_offset']), (40, None))

    def test_a_feed_short_only_because_of_the_artist_cap_stays_continuable(self):
        body = self._head_of_a_build(97, allocated=100)
        self.assertEqual(body['next_offset'], 97)

    def test_the_configured_length_is_what_a_miss_builds(self):
        feed = Feed(slug='daily-mix', state='ok', scope='user', tracks=[], funnel={}, title='Klassiek')

        def serve(conn, username, slug, now, key, build):
            return build(), 'live'

        with (
            patch.object(feeds_router.settings, 'get', side_effect=lambda key, *a: 40 if key == 'feeds_size' else None),
            patch('services.music_manager.routers.feeds.serve_snapshot', side_effect=serve),
            patch('services.music_manager.routers.feeds.build_feed', return_value=feed) as build,
        ):
            client.get('/api/feeds/daily-mix?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(build.call_args.args[2].size, 40)

    def test_a_page_larger_than_a_hundred_is_refused(self):
        response = client.get('/api/feeds/daily-mix?username=user&limit=101', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 422)
        response = client.get('/api/feeds/daily-mix?username=user&offset=-1', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 422)

    def test_the_listing_is_served_from_its_own_snapshot_row(self):
        stored = {
            'feeds': [
                {'slug': 'release-radar', 'size': 30, 'window_days': 7, 'title': 'Release Radar', 'subtitle': None}
            ]
        }
        with (
            patch('services.music_manager.routers.feeds.serve_snapshot', return_value=(stored, 'snapshot')) as serve,
            patch('services.music_manager.routers.feeds.resolve_profile') as resolve,
        ):
            response = client.get('/api/feeds?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), stored)
        self.assertEqual(serve.call_args.args[2], feeds_router.LIST_SLUG)
        resolve.assert_not_called()

    def test_a_miss_builds_through_the_callable_the_router_hands_over(self):
        """`serve_snapshot` is given a closure, not a body: a hit must cost no build."""
        plain = Feed(slug='release-radar', state='ok', scope='user', tracks=[], funnel={}, title='Release Radar')

        def serve(conn, username, slug, now, params_key, build):
            self.assertEqual(slug, 'release-radar')
            self.assertIsInstance(params_key, str)
            return build(), 'live'

        with (
            patch('services.music_manager.routers.feeds.serve_snapshot', side_effect=serve),
            patch('services.music_manager.routers.feeds.build_feed', return_value=plain) as build,
        ):
            response = client.get('/api/feeds/release-radar?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-MuMa-Feed-Source'], 'live')
        build.assert_called_once()

    def test_the_key_is_asked_for_this_listener_and_slug(self):
        with (
            patch('services.music_manager.routers.feeds.serve_snapshot', return_value=({'feeds': []}, 'snapshot')),
            patch('services.music_manager.routers.feeds.params_key', return_value='k') as key,
        ):
            client.get('/api/feeds/daily-mix-hard?username=user', headers={'X-API-Key': 'k'})
            client.get('/api/feeds?username=user', headers={'X-API-Key': 'k'})
        self.assertEqual(
            [call.args for call in key.call_args_list],
            [(self.conn, 'user', 'daily-mix-hard'), (self.conn, 'user', feeds_router.LIST_SLUG)],
        )


class _KeyDatabase:
    """A connection whose cursor answers the two queries `params_key` issues: the
    listener's exclusions and the genre-hardness digest."""

    def __init__(self, exclusions=(), hardness=(10, 12345)):
        self.exclusions = list(exclusions)
        self.hardness = hardness
        self.statements = []

    def cursor(self):
        database = self

        class Cursor:
            _sql = ''

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def execute(self, sql, params=None):
                self._sql = ' '.join(sql.split())
                database.statements.append(self._sql)

            def fetchall(self):
                if 'feeds_profile_exclusions' in self._sql:
                    return [{'entity_type': kind, 'entity_name': name} for kind, name in database.exclusions]
                return []

            def fetchone(self):
                genres, checksum = database.hardness
                return {'genres': genres, 'checksum': checksum}

        return Cursor()


class ParamsKeyTest(unittest.TestCase):
    """What ages a snapshot within its day: `params_key` must change with each input
    that shapes a build, and only for the slugs that input shapes."""

    def setUp(self):
        patcher = patch.object(feeds_router.settings, 'get', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_feed_length_change_changes_every_key(self):
        """An admin who changes `feeds_size` sees the new length on the next read."""
        database = _KeyDatabase()
        for slug in feeds_router.SNAPSHOT_SLUGS:
            with self.subTest(slug=slug):
                before = feeds_router.params_key(database, 'user', slug)
                with patch.object(
                    feeds_router.settings, 'get', side_effect=lambda key, *a: 150 if key == 'feeds_size' else None
                ):
                    after = feeds_router.params_key(database, 'user', slug)
                self.assertNotEqual(before, after)

    def test_a_hardness_edit_changes_the_key_of_the_spectrum_mixes_and_the_listing(self):
        before, after = _KeyDatabase(hardness=(10, 111)), _KeyDatabase(hardness=(10, 222))
        for slug in ('daily-mix-soft', 'daily-mix-mid', 'daily-mix-hard', feeds_router.LIST_SLUG):
            with self.subTest(slug=slug):
                self.assertNotEqual(
                    feeds_router.params_key(before, 'user', slug), feeds_router.params_key(after, 'user', slug)
                )

    def test_a_hardness_edit_leaves_the_other_feeds_fresh(self):
        before, after = _KeyDatabase(hardness=(10, 111)), _KeyDatabase(hardness=(10, 222))
        for slug in ('release-radar', 'daily-mix', 'daily-mix-artist', 'daily-mix-label'):
            with self.subTest(slug=slug):
                self.assertEqual(
                    feeds_router.params_key(before, 'user', slug), feeds_router.params_key(after, 'user', slug)
                )
        self.assertFalse(
            any('rules_genres' in sql for sql in before.statements), 'no digest query for a slug it cannot shape'
        )

    def test_an_exclusion_change_changes_every_key_of_that_listener(self):
        before = _KeyDatabase(exclusions=[('artist', 'angerfist')])
        after = _KeyDatabase(exclusions=[('artist', 'angerfist'), ('label', 'masters of hardcore')])
        for slug in feeds_router.SNAPSHOT_SLUGS:
            with self.subTest(slug=slug):
                self.assertNotEqual(
                    feeds_router.params_key(before, 'user', slug), feeds_router.params_key(after, 'user', slug)
                )

    def test_the_key_ignores_the_order_the_exclusions_come_back_in(self):
        one = _KeyDatabase(exclusions=[('artist', 'a'), ('genre', 'b')])
        other = _KeyDatabase(exclusions=[('genre', 'b'), ('artist', 'a')])
        self.assertEqual(
            feeds_router.params_key(one, 'user', 'daily-mix'), feeds_router.params_key(other, 'user', 'daily-mix')
        )

    def test_an_exclusion_that_lands_during_a_build_leaves_its_row_stale(self):
        """The race: the router computes the key, the build runs on the old exclusions,
        the exclusion lands and deletes the rows, the build then writes. The row it
        writes carries the old key, so the next read rebuilds it."""
        database = _KeyDatabase(exclusions=[])
        written = feeds_router.params_key(database, 'user', 'daily-mix')
        database.exclusions.append(('artist', 'angerfist'))
        self.assertNotEqual(feeds_router.params_key(database, 'user', 'daily-mix'), written)

    def test_a_recent_split_change_changes_every_key(self):
        """Bug report 131: moving the recent share, window or older minimum rating
        rebuilds today's mixes on their next read."""
        database = _KeyDatabase()
        before = feeds_router.params_key(database, 'user', 'daily-mix')
        for setting, value in (
            ('feeds_daily_recent_percent', 30),
            ('feeds_daily_recent_window_days', 90),
            ('feeds_daily_older_min_rating', 4),
        ):
            with self.subTest(setting=setting):
                with patch.object(
                    feeds_router.settings,
                    'get',
                    side_effect=lambda key, *a, s=setting, v=value: v if key == s else None,
                ):
                    after = feeds_router.params_key(database, 'user', 'daily-mix')
                self.assertNotEqual(before, after)

    def test_the_configured_split_reaches_the_build_policy(self):
        values = {'feeds_daily_recent_percent': 30, 'feeds_daily_recent_window_days': 90}
        with patch.object(feeds_router.settings, 'get', side_effect=lambda key, *a: values.get(key)):
            mix = feeds_router._sized(feeds_router.POLICIES['daily-mix-soft'])
            radar = feeds_router._sized(feeds_router.POLICIES['release-radar'])
        self.assertEqual((mix.recent_share, mix.recent_window_days, mix.older_min_rating), (0.3, 90, 3))
        self.assertIsNone(radar.recent_share)

    def test_a_settings_change_still_changes_the_key(self):
        database = _KeyDatabase()
        default = feeds_router.params_key(database, 'user', 'release-radar')
        with patch.object(feeds_router.settings, 'get', side_effect=lambda name: '40,80' if 'edges' in name else None):
            moved = feeds_router.params_key(database, 'user', 'release-radar')
        self.assertNotEqual(default, moved)


if __name__ == '__main__':
    unittest.main()
