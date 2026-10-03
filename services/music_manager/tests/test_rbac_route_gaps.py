"""Authorization on the routes that used to accept any enabled account.

See docs/bug-reports/037-management-routes-open-to-every-user.md. Every tightened
route is exercised three ways: a plain `user` role is refused, the role that should
pass does, and the system key keeps working for LMS, CI and scripts/.
"""

import threading
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import bcrypt
import urllib3

import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient

from services.music_manager import rbac
from services.music_manager.artist_image_fetcher import safe_fetch
from services.music_manager.main import app
from services.music_manager.routers import artist_images as artist_images_router
from services.music_manager.routers import channel_links as channel_links_router
from services.music_manager.routers import events as events_router
from services.music_manager.routers import management as management_router
from services.music_manager.routers import rating as rating_router
from services.tests.stop_after import StopAfter

SYSTEM_KEY = resolve_system_api_key()


def auth_for(user_id, username, role_name, permissions):
    """A verify_token result for an account with the given role and permissions."""
    return {
        'status': 'ok',
        'type': 'user',
        'user': {'id': user_id, 'username': username, 'role_name': role_name, 'permissions': sorted(permissions)},
    }


LISTENER = auth_for(5, 'listener', 'user', rbac.USER_ROLE_PERMISSIONS)
CURATOR = auth_for(6, 'curator', 'curator', rbac.USER_ROLE_PERMISSIONS | {'rules.manage'})
USER_ADMIN = auth_for(7, 'helper', 'helpdesk', rbac.USER_ROLE_PERMISSIONS | {'users.update'})
ADMIN = auth_for(1, 'root', 'admin', {name for name, _ in rbac.PERMISSIONS})

RULES_ROUTES = [
    ('post', '/api/label-proposals/1/confirm', {'label': 'Scantraxx'}),
    ('post', '/api/label-proposals/1/reject', None),
    ('post', '/api/channel-links/proposals/refresh', None),
    ('post', '/api/channel-links/proposals/1/confirm', None),
    ('post', '/api/channel-links/proposals/1/reject', None),
    ('delete', '/api/channel-links/channels/1/label', None),
    ('put', '/api/channel-links/channels/1/label', {'target_id': 1}),
    ('post', '/api/rules/genres/1/decide', {'state': 'white'}),
    ('post', '/api/rules/podcasts/1/decide', {'state': 'white'}),
    ('post', '/api/rules/podcasts/1/rename', {'name': 'Show'}),
    ('post', '/api/rules/podcasts/1/aliases', {'alias': 'Alias'}),
    ('delete', '/api/rules/podcasts/1/aliases?alias=Alias', None),
    ('post', '/api/rules/artist-genres', {'artist_name': 'A', 'genre_id': 1}),
    ('delete', '/api/rules/artist-genres/1', None),
    ('post', '/api/rules/label-genres', {'label_name': 'L', 'genre_id': 1}),
    ('delete', '/api/rules/label-genres/1', None),
    ('post', '/api/rules/artist-redirects', {'name': 'A', 'corrected_name': 'B'}),
    ('delete', '/api/rules/artist-redirects/1', None),
    ('post', '/api/tagger/rescan', None),
    ('post', '/api/tagger/rescan/file', {'filepath': '/music/a.mp3'}),
]

ADMIN_ROUTES = [
    ('get', '/api/system/containers', None),
    ('get', '/api/system/logs/muma-manager', None),
    ('post', '/api/soundcloud', {'name': 'x', 'soundcloud_id': 1}),
    ('delete', '/api/soundcloud/x', None),
    ('post', '/api/youtube', {'name': 'x'}),
    ('delete', '/api/youtube/x', None),
]

READ_ROUTES = [
    '/api/rules',
    '/api/artists',
    '/api/labels',
    '/api/label-proposals',
    '/api/channel-links/proposals',
    '/api/channel-links/channels?q=x',
    '/api/channel-links/targets?kind=label&q=x',
    '/api/channel-links/by-label?name=x',
    '/api/config',
]

ARTIST_IMAGE_ROUTES = [
    ('post', '/api/artists/1/image/url', {'url': 'https://img.example/a.jpg'}),
    ('post', '/api/artists/1/image/upload', {'data': 'aGVsbG8='}),
    ('post', '/api/artists/1/image/select/2', None),
    ('post', '/api/artists/1/image/clear', None),
    ('post', '/api/artists/fetch-missing', None),
    ('post', '/api/artists/1/fetch-image', None),
]


class RouteAuthTestCase(unittest.TestCase):
    """Shared plumbing: a client that reports server errors as 500s, and mocked I/O."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        self.conn = MagicMock()
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.conn.cursor.return_value.__exit__.return_value = False
        for module in (
            management_router,
            events_router,
            rating_router,
            artist_images_router,
            users_router,
            channel_links_router,
        ):
            patcher = patch.object(module, 'get_db_connection', return_value=self.conn)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target in ('docker', 'ProcessedFilesHelper', 'move_release_folder', 'lms_scan_trigger'):
            patcher = patch.object(management_router, target)
            patcher.start()
            self.addCleanup(patcher.stop)
        # A link change queues a retag through the real database helpers; not what is tested here.
        patcher = patch.object(channel_links_router, 'queue_retag', return_value=0)
        patcher.start()
        self.addCleanup(patcher.stop)
        for target in ('download_public_image', '_store_manual_image', 'run_fetch_missing', 'trigger_fetch_by_id'):
            patcher = patch.object(artist_images_router, target, return_value={'status': 'ok'})
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, method, path, body, auth):
        """Call a route as `auth` (a verify_token result) or, for 'system', with the system key."""
        if auth == 'system':
            return self.client.request(method, path, json=body, headers={'x-api-key': SYSTEM_KEY})
        with patch.object(users_router, 'verify_token', return_value=auth):
            return self.client.request(method, path, json=body, headers={'x-api-key': 'user-key'})

    def assertRefused(self, response, route):
        self.assertEqual(response.status_code, 403, f'{route}: {response.status_code} {response.text}')

    def assertAdmitted(self, response, route):
        self.assertNotIn(response.status_code, (401, 403), f'{route}: {response.status_code} {response.text}')


class ManagementRulesRoutesTest(RouteAuthTestCase):
    def test_a_plain_user_cannot_change_rules(self):
        for method, path, body in RULES_ROUTES:
            self.assertRefused(self.call(method, path, body, LISTENER), path)

    def test_rules_manage_is_enough(self):
        for method, path, body in RULES_ROUTES:
            self.assertAdmitted(self.call(method, path, body, CURATOR), path)

    def test_the_system_key_still_passes(self):
        for method, path, body in RULES_ROUTES:
            self.assertAdmitted(self.call(method, path, body, 'system'), path)


class ManagementAdminRoutesTest(RouteAuthTestCase):
    def test_a_plain_user_is_refused(self):
        for method, path, body in ADMIN_ROUTES:
            self.assertRefused(self.call(method, path, body, LISTENER), path)

    def test_rules_manage_is_not_enough(self):
        for method, path, body in ADMIN_ROUTES:
            self.assertRefused(self.call(method, path, body, CURATOR), path)

    def test_an_admin_and_the_system_key_pass(self):
        management_router.docker.from_env.return_value.containers.get.return_value.name = 'muma-manager'
        management_router.docker.from_env.return_value.containers.get.return_value.logs.return_value = b''
        for method, path, body in ADMIN_ROUTES:
            self.assertAdmitted(self.call(method, path, body, ADMIN), path)
            self.assertAdmitted(self.call(method, path, body, 'system'), path)


class ManagementReadRoutesTest(RouteAuthTestCase):
    def test_a_plain_user_can_still_read(self):
        self.cursor.fetchall.return_value = []
        for path in READ_ROUTES:
            self.assertAdmitted(self.call('get', path, None, LISTENER), path)

    def test_the_local_verify_copy_is_gone(self):
        # The router re-exports the canonical dependency; news, radio and events import it.
        self.assertIs(management_router.verify_api_key, users_router.verify_api_key)


class EventsTest(RouteAuthTestCase):
    def test_a_plain_user_can_list_events(self):
        self.cursor.fetchall.return_value = []
        self.cursor.fetchone.return_value = {'total': 0}
        self.assertEqual(self.call('get', '/api/events', None, LISTENER).status_code, 200)

    def test_a_plain_user_cannot_delete_events(self):
        self.assertRefused(self.call('delete', '/api/events/1', None, LISTENER), 'delete one')
        self.assertRefused(self.call('delete', '/api/events', None, LISTENER), 'clear')
        self.cursor.execute.assert_not_called()

    def test_an_admin_and_the_system_key_can_delete_events(self):
        self.assertEqual(self.call('delete', '/api/events/1', None, ADMIN).status_code, 200)
        self.assertEqual(self.call('delete', '/api/events', None, 'system').status_code, 200)


class RatingWebhookTest(RouteAuthTestCase):
    PAYLOAD = {'event': 'rating_changed', 'object_type': 'artist', 'object_id': 'A', 'username': 'root', 'rating': 5}

    def test_a_user_key_cannot_write_ratings_under_any_name(self):
        for path in ('/api/rating/lms-event',):
            self.assertRefused(self.call('post', path, self.PAYLOAD, LISTENER), path)
            self.assertRefused(self.call('post', path, self.PAYLOAD, ADMIN), path)
        self.cursor.execute.assert_not_called()

    def test_the_system_key_lms_uses_still_writes(self):
        response = self.call('post', '/api/rating/lms-event', self.PAYLOAD, 'system')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.cursor.execute.call_args.args[1][2], 'root')

    def test_a_user_reads_their_own_ratings(self):
        self.cursor.fetchall.return_value = []
        self.assertEqual(self.call('get', '/api/rating/ratings/listener', None, LISTENER).status_code, 200)

    def test_a_user_cannot_read_someone_elses_ratings(self):
        self.assertRefused(self.call('get', '/api/rating/ratings/root', None, LISTENER), 'other')

    def test_an_admin_and_the_system_key_read_anyones_ratings(self):
        self.cursor.fetchall.return_value = []
        self.assertEqual(self.call('get', '/api/rating/ratings/listener', None, ADMIN).status_code, 200)
        self.assertEqual(self.call('get', '/api/rating/ratings/listener', None, 'system').status_code, 200)


class ArtistImageRoutesTest(RouteAuthTestCase):
    def test_a_plain_user_cannot_change_artist_images(self):
        for method, path, body in ARTIST_IMAGE_ROUTES:
            self.assertRefused(self.call(method, path, body, LISTENER), path)

    def test_rules_manage_and_the_system_key_pass(self):
        self.cursor.fetchone.return_value = {'id': 2}
        for method, path, body in ARTIST_IMAGE_ROUTES:
            self.assertAdmitted(self.call(method, path, body, CURATOR), path)
            self.assertAdmitted(self.call(method, path, body, 'system'), path)

    def test_an_oversized_upload_is_refused_before_decoding(self):
        body = {'data': 'A' * (artist_images_router.MAX_IMAGE_BYTES * 2)}
        response = self.call('post', '/api/artists/1/image/upload', body, CURATOR)
        self.assertEqual(response.status_code, 413)
        artist_images_router._store_manual_image.assert_not_called()


def resolving_to(*addresses):
    """A getaddrinfo stand-in returning the given addresses for any host."""
    return MagicMock(return_value=[(2, 1, 6, '', (address, 0)) for address in addresses])


def ensure_public_url(url):
    """The address check the image URL route applies to every hop, without the fetch."""
    _scheme, host, port, _target = safe_fetch.split_url(url)
    safe_fetch.resolve_public(host, port)


class EnsurePublicUrlTest(unittest.TestCase):
    def test_non_http_schemes_are_refused(self):
        for url in ('file:///etc/passwd', 'ftp://example.com/a.jpg', 'gopher://example.com', 'http://'):
            with self.assertRaises(artist_images_router.UnsafeImageUrl, msg=url):
                ensure_public_url(url)

    def test_private_loopback_and_link_local_addresses_are_refused(self):
        for address in (
            '127.0.0.1',
            '10.0.0.5',
            '192.0.2.27',
            '172.16.0.1',
            '169.254.169.254',
            '100.64.0.1',
            '0.0.0.0',
            '::1',
            'fe80::1',
            'fc00::1',
            '::ffff:127.0.0.1',
            '224.0.0.1',
        ):
            with (
                patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to(address)),
                self.assertRaises(artist_images_router.UnsafeImageUrl, msg=address),
            ):
                ensure_public_url('http://images.example/a.jpg')

    def test_one_private_address_among_public_ones_is_enough_to_refuse(self):
        with (
            patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to('93.184.216.34', '10.0.0.1')),
            self.assertRaises(artist_images_router.UnsafeImageUrl),
        ):
            ensure_public_url('https://images.example/a.jpg')

    def test_an_unresolvable_host_is_refused(self):
        with (
            patch.object(safe_fetch.socket, 'getaddrinfo', side_effect=OSError('no such host')),
            self.assertRaises(artist_images_router.UnsafeImageUrl),
        ):
            ensure_public_url('https://nowhere.example/a.jpg')

    def test_a_public_address_passes(self):
        with patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to('93.184.216.34')):
            ensure_public_url('https://images.example/a.jpg')


def fake_response(status=200, headers=None, body=b'img'):
    """A streamed urllib3 response, as the pinned connection pool returns it."""
    return urllib3.HTTPResponse(body=BytesIO(body), headers=headers or {}, status=status, preload_content=False)


def pinned_pool(*responses):
    """A safe_fetch._pool stand-in whose pools answer with `responses` in turn."""
    replies = list(responses)
    pools = []

    def make(scheme, host, address, port, timeout):
        pool = MagicMock()
        pool.args = (scheme, host, address, port, timeout)
        pool.urlopen.return_value = replies.pop(0)
        pools.append(pool)
        return pool

    return MagicMock(side_effect=make), pools


class DownloadPublicImageTest(unittest.TestCase):
    """The route's download goes through safe_fetch; the deep cases live in test_safe_fetch."""

    def setUp(self):
        patcher = patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to('93.184.216.34'))
        self.getaddrinfo = patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_body_is_returned_through_the_checked_address(self):
        factory, pools = pinned_pool(fake_response())
        with patch.object(safe_fetch, '_pool', factory):
            self.assertEqual(artist_images_router.download_public_image('https://images.example/a.jpg'), b'img')
        self.assertEqual(pools[0].args[2], '93.184.216.34')
        self.assertFalse(pools[0].urlopen.call_args.kwargs['redirect'])

    def test_a_redirect_to_a_private_address_is_refused(self):
        def resolve(host, *_args, **_kwargs):
            address = '127.0.0.1' if host == 'internal.example' else '93.184.216.34'
            return [(2, 1, 6, '', (address, 0))]

        self.getaddrinfo.side_effect = resolve
        factory, pools = pinned_pool(fake_response(status=302, headers={'Location': 'http://internal.example/admin'}))
        with patch.object(safe_fetch, '_pool', factory), self.assertRaises(artist_images_router.UnsafeImageUrl):
            artist_images_router.download_public_image('https://images.example/a.jpg')
        self.assertEqual(len(pools), 1)

    def test_a_declared_oversized_body_is_refused(self):
        big = fake_response(headers={'Content-Length': str(artist_images_router.MAX_IMAGE_BYTES + 1)})
        factory, _pools = pinned_pool(big)
        with patch.object(safe_fetch, '_pool', factory), self.assertRaises(artist_images_router.ImageTooLarge):
            artist_images_router.download_public_image('https://images.example/a.jpg')

    def test_an_undeclared_oversized_body_is_cut_off(self):
        endless = fake_response(body=b'x' * (artist_images_router.MAX_IMAGE_BYTES + 1))
        factory, _pools = pinned_pool(endless)
        with patch.object(safe_fetch, '_pool', factory), self.assertRaises(artist_images_router.ImageTooLarge):
            artist_images_router.download_public_image('https://images.example/a.jpg')


class ImageUrlRouteTest(unittest.TestCase):
    def test_a_url_resolving_to_a_private_address_is_refused_without_a_request(self):
        client = TestClient(app)
        with (
            patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to('192.0.2.27')),
            patch.object(safe_fetch, '_pool') as pool,
        ):
            response = client.post(
                '/api/artists/1/image/url',
                json={'url': 'http://muma.internal/api/users'},
                headers={'x-api-key': SYSTEM_KEY},
            )
        self.assertEqual(response.status_code, 400)
        pool.assert_not_called()

    def test_a_rebinding_answer_never_reaches_the_connection(self):
        """Public for the one lookup, internal for a second: the second is never asked."""
        client = TestClient(app)
        factory, pools = pinned_pool(fake_response(body=b'binary'))
        with (
            patch.object(
                safe_fetch.socket,
                'getaddrinfo',
                side_effect=[[(2, 1, 6, '', ('93.184.216.34', 0))], [(2, 1, 6, '', ('127.0.0.1', 0))]],
            ) as getaddrinfo,
            patch.object(safe_fetch, '_pool', factory),
            patch.object(artist_images_router, '_store_manual_image', return_value={'status': 'ok'}),
        ):
            response = client.post(
                '/api/artists/1/image/url',
                json={'url': 'https://rebind.example/a.jpg'},
                headers={'x-api-key': SYSTEM_KEY},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(getaddrinfo.call_count, 1)
        self.assertEqual(pools[0].args[2], '93.184.216.34')


class UsersListTest(RouteAuthTestCase):
    def test_the_list_does_not_carry_api_keys(self):
        self.cursor.fetchall.return_value = []
        self.assertEqual(self.call('get', '/api/users', None, ADMIN).status_code, 200)
        statement = self.cursor.execute.call_args.args[0]
        self.assertNotIn('api_key', statement)

    def test_a_plain_user_cannot_list_users(self):
        self.assertRefused(self.call('get', '/api/users', None, LISTENER), 'list')


class PasswordChangeTest(RouteAuthTestCase):
    def target(self, role_name='user', password='old-secret'):
        """Make the target account row the password route reads."""
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(4)).decode() if password else None
        self.cursor.fetchone.return_value = {'id': 5, 'password_hash': password_hash, 'role_name': role_name}

    def updated(self):
        return any('UPDATE users SET password_hash' in call.args[0] for call in self.cursor.execute.call_args_list)

    def test_a_user_cannot_change_another_users_password(self):
        self.target()
        self.assertRefused(self.call('post', '/api/users/1/password', {'password': 'x'}, LISTENER), 'other')
        self.assertFalse(self.updated())

    def test_users_update_without_admin_is_not_enough_for_another_account(self):
        self.target()
        self.assertRefused(self.call('post', '/api/users/5/password', {'password': 'x'}, USER_ADMIN), 'other')

    def test_a_non_admin_cannot_change_an_admins_password_even_their_own_role_allows_users_update(self):
        self.target(role_name='admin')
        response = self.call(
            'post', '/api/users/7/password', {'password': 'x', 'current_password': 'old-secret'}, USER_ADMIN
        )
        self.assertRefused(response, 'admin target')
        self.assertFalse(self.updated())

    def test_an_own_change_needs_the_current_password(self):
        self.target()
        self.assertRefused(self.call('post', '/api/users/5/password', {'password': 'new'}, LISTENER), 'missing')
        self.assertRefused(
            self.call('post', '/api/users/5/password', {'password': 'new', 'current_password': 'wrong'}, LISTENER),
            'wrong',
        )
        self.assertFalse(self.updated())

    def test_an_own_change_with_the_current_password_succeeds(self):
        self.target()
        body = {'password': 'new', 'current_password': 'old-secret'}
        self.assertEqual(self.call('post', '/api/users/5/password', body, LISTENER).status_code, 200)
        self.assertTrue(self.updated())

    def test_an_account_without_a_password_may_set_its_first(self):
        self.target(password=None)
        self.assertEqual(self.call('post', '/api/users/5/password', {'password': 'new'}, LISTENER).status_code, 200)
        self.assertTrue(self.updated())

    def test_an_admin_sets_any_password_without_the_current_one(self):
        self.target(role_name='admin')
        self.assertEqual(self.call('put', '/api/users/5/password', {'password': 'new'}, ADMIN).status_code, 200)
        self.assertEqual(self.call('post', '/api/users/5/password', {'password': 'new'}, 'system').status_code, 200)

    def test_an_unknown_account_is_not_found(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(self.call('post', '/api/users/99/password', {'password': 'new'}, ADMIN).status_code, 404)


class ServerSyncTest(RouteAuthTestCase):
    PATHS = ('/api/users/sync/muma-server', '/api/users/sync/lms-db')

    def setUp(self):
        super().setUp()
        patcher = patch.object(users_router, 'run_lms_db_sync', return_value=3)
        self.sync = patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_plain_user_cannot_start_a_sync(self):
        for path in self.PATHS:
            self.assertRefused(self.call('post', path, None, LISTENER), path)
        self.sync.assert_not_called()

    def test_an_admin_runs_the_sync_and_the_lock_is_released(self):
        response = self.call('post', '/api/users/sync/muma-server', None, ADMIN)
        self.assertEqual(response.json()['synced'], 3)
        self.assertFalse(users_router.lms_db_sync_lock.locked())

    def test_a_second_sync_while_one_runs_is_a_conflict(self):
        with users_router.lms_db_sync_lock:
            response = self.call('post', '/api/users/sync/lms-db', None, 'system')
        self.assertEqual(response.status_code, 409)
        self.sync.assert_not_called()

    def test_a_failing_sync_still_releases_the_lock(self):
        self.sync.side_effect = RuntimeError('locked database')
        self.assertEqual(self.call('post', '/api/users/sync/muma-server', None, ADMIN).status_code, 500)
        self.assertFalse(users_router.lms_db_sync_lock.locked())

    def test_the_hourly_loop_holds_the_same_lock(self):
        seen = []

        def record():
            seen.append(users_router.lms_db_sync_lock.locked())

        with patch.object(users_router, 'run_lms_db_sync_with_retry', side_effect=record):
            users_router.run_lms_db_sync_loop(1, stop=StopAfter(1))
        self.assertEqual(seen, [True])
        self.assertIsInstance(users_router.lms_db_sync_lock, type(threading.Lock()))


class DeleteUserScopeTest(RouteAuthTestCase):
    """DELETE /api/users/{id} is for `users.update` only (issue #38): no self-delete."""

    def setUp(self):
        super().setUp()
        notify = patch.object(users_router, 'notify_server_sync_users')
        notify.start()
        self.addCleanup(notify.stop)

    def test_a_plain_account_cannot_delete_itself(self):
        response = self.call('delete', f"/api/users/{LISTENER['user']['id']}", None, LISTENER)
        self.assertRefused(response, 'self-delete')
        self.cursor.execute.assert_not_called()

    def test_a_plain_account_cannot_delete_another(self):
        self.assertRefused(self.call('delete', '/api/users/9', None, LISTENER), 'delete another')
        self.cursor.execute.assert_not_called()

    def test_users_update_and_the_system_key_may_delete(self):
        self.cursor.fetchone.return_value = {'id': 9, 'username': 'user', 'role_id': 2}
        with (
            patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}),
            patch.object(users_router.rbac, 'record_audit_event'),
        ):
            self.assertEqual(self.call('delete', '/api/users/9', None, USER_ADMIN).status_code, 200)
            self.assertEqual(self.call('delete', '/api/users/9', None, ADMIN).status_code, 200)
            self.assertEqual(self.call('delete', '/api/users/9', None, 'system').status_code, 200)

    def test_the_last_admin_still_cannot_delete_itself(self):
        # Bug report 052: `cnt` counts the other enabled admins.
        self.cursor.fetchone.side_effect = [{'id': 1, 'username': 'root', 'role_id': 1}, {'cnt': 0}]
        with patch.object(users_router.rbac, 'get_role_by_name', return_value={'id': 1}):
            response = self.call('delete', f"/api/users/{ADMIN['user']['id']}", None, ADMIN)
        self.assertEqual(response.status_code, 409, response.text)


class LatestImportsScopeTest(RouteAuthTestCase):
    """GET /api/scrobble/import/latest: every account's for an admin, its own otherwise (issue #38)."""

    def setUp(self):
        super().setUp()
        from services.music_manager.routers import scrobbler as scrobbler_router

        patcher = patch.object(scrobbler_router, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cursor.fetchall.return_value = []

    def last_query(self):
        """The statement and parameters of the last SELECT."""
        call = self.cursor.execute.call_args
        return call.args[0], (call.args[1] if len(call.args) > 1 else None)

    def test_a_plain_account_reads_only_its_own_imports(self):
        response = self.call('get', '/api/scrobble/import/latest', None, LISTENER)
        self.assertEqual(response.status_code, 200, response.text)
        sql, params = self.last_query()
        self.assertIn('WHERE username = %s', sql)
        self.assertEqual(params, ('listener',))

    def test_an_admin_and_the_system_key_read_every_account(self):
        for auth in (ADMIN, 'system'):
            self.assertEqual(self.call('get', '/api/scrobble/import/latest', None, auth).status_code, 200)
            sql, params = self.last_query()
            self.assertNotIn('WHERE', sql)
            self.assertIsNone(params)

    def test_users_update_alone_does_not_widen_the_list(self):
        self.call('get', '/api/scrobble/import/latest', None, USER_ADMIN)
        sql, params = self.last_query()
        self.assertIn('WHERE username = %s', sql)
        self.assertEqual(params, ('helper',))

    def test_the_management_copy_applies_the_same_scope(self):
        management_router.get_latest_scrobble_imports_proxy(LISTENER)
        sql, params = self.last_query()
        self.assertIn('WHERE username = %s', sql)
        self.assertEqual(params, ('listener',))


if __name__ == '__main__':
    unittest.main()
