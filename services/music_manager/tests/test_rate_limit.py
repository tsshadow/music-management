"""The authentication endpoints stop answering once a caller hammers them."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient

from services.music_manager import rate_limit
from services.music_manager.main import app


class SlidingWindowTest(unittest.TestCase):
    def setUp(self):
        self.limiter = rate_limit.SlidingWindowRateLimiter(attempts=3, window_seconds=60)

    def test_a_caller_with_no_failures_is_not_blocked(self):
        blocked, retry_after = self.limiter.blocked('caller', now=0)
        self.assertFalse(blocked)
        self.assertEqual(retry_after, 0)

    def test_failures_up_to_the_limit_leave_the_caller_in(self):
        for attempt in range(3):
            self.assertFalse(self.limiter.blocked('caller', now=attempt)[0])
            self.limiter.register_attempt('caller', now=attempt)

    def test_the_caller_is_blocked_once_the_window_is_full(self):
        for attempt in range(3):
            self.limiter.register_attempt('caller', now=attempt)
        blocked, retry_after = self.limiter.blocked('caller', now=4)
        self.assertTrue(blocked)
        self.assertGreater(retry_after, 0)

    def test_asking_whether_a_caller_is_blocked_costs_them_nothing(self):
        """`blocked` is a read: two failures plus a hundred questions is still
        two failures. Otherwise a check on a busy endpoint would be the thing
        that fills the window."""
        for attempt in range(2):
            self.limiter.register_attempt('caller', now=attempt)
        for _ in range(100):
            self.limiter.blocked('caller', now=2)
        self.limiter.register_attempt('caller', now=2)
        self.assertTrue(self.limiter.blocked('caller', now=2)[0])

    def test_the_window_slides_rather_than_resetting_in_blocks(self):
        """With fixed buckets a caller gets the whole allowance twice across a
        boundary; with a sliding window each attempt expires on its own."""
        for attempt in range(3):
            self.limiter.register_attempt('caller', now=attempt)
        self.assertTrue(self.limiter.blocked('caller', now=59)[0])
        # The first failure (t=0) leaves the window at t=60, freeing one slot.
        self.assertFalse(self.limiter.blocked('caller', now=61)[0])

    def test_callers_are_counted_separately(self):
        for attempt in range(3):
            self.limiter.register_attempt('first', now=attempt)
        self.assertTrue(self.limiter.blocked('first', now=3)[0])
        self.assertFalse(self.limiter.blocked('second', now=3)[0])

    def test_the_retry_hint_shrinks_as_the_window_moves_on(self):
        for attempt in range(3):
            self.limiter.register_attempt('caller', now=attempt)
        early = self.limiter.blocked('caller', now=10)[1]
        later = self.limiter.blocked('caller', now=50)[1]
        self.assertGreater(early, later)

    def test_resetting_one_caller_leaves_the_others_alone(self):
        for attempt in range(3):
            self.limiter.register_attempt('first', now=attempt)
            self.limiter.register_attempt('second', now=attempt)
        self.limiter.reset('first')
        self.assertFalse(self.limiter.blocked('first', now=3)[0])
        self.assertTrue(self.limiter.blocked('second', now=3)[0])

    def test_resetting_everything_clears_every_caller(self):
        for attempt in range(3):
            self.limiter.register_attempt('first', now=attempt)
        self.limiter.reset()
        self.assertFalse(self.limiter.blocked('first', now=3)[0])


class ClientKeyTest(unittest.TestCase):
    """Who the caller is: X-Forwarded-For only counts when whoever wrote it can be believed.

    docs/bug-reports/079-google-login-unverified-email-and-lms-login-limit.md: LMS now sends
    the client address it resolved, so music-manager has to tell that header apart from one
    a client typed itself.
    """

    def make_request(self, headers=None, host='172.18.0.5'):
        request = MagicMock()
        request.headers = headers or {}
        request.client = MagicMock(host=host) if host else None
        return request

    def test_the_peer_address_is_used_without_a_proxy_header(self):
        self.assertEqual(rate_limit.client_key(self.make_request()), '172.18.0.5')

    def test_a_trusted_proxy_is_believed(self):
        """LMS (or the nginx in front of the web-player host) on the Docker network reports the client."""
        request = self.make_request(headers={'x-forwarded-for': '203.0.113.9'})
        self.assertEqual(rate_limit.client_key(request), '203.0.113.9')

    def test_a_forged_header_from_an_untrusted_caller_is_ignored(self):
        """An internet caller reaching music-manager directly cannot name itself someone else."""
        request = self.make_request(headers={'x-forwarded-for': '198.51.100.1'}, host='203.0.113.50')
        self.assertEqual(rate_limit.client_key(request), '203.0.113.50')

    def test_a_forged_header_from_an_untrusted_caller_cannot_start_fresh_buckets(self):
        keys = {
            rate_limit.client_key(
                self.make_request(headers={'x-forwarded-for': f'198.51.100.{n}'}, host='203.0.113.50')
            )
            for n in range(20)
        }
        self.assertEqual(keys, {'203.0.113.50'})

    def test_the_system_key_makes_the_header_believable_from_anywhere(self):
        """LMS's password checks carry the system key; a deployment where it reaches
        music-manager over a public address still passes the client on."""
        with patch.dict('os.environ', {'API_KEY': 'the-system-key'}):
            request = self.make_request(
                headers={'x-forwarded-for': '198.51.100.1', 'x-api-key': 'the-system-key'}, host='203.0.113.50'
            )
            self.assertEqual(rate_limit.client_key(request), '198.51.100.1')

    def test_a_wrong_key_does_not_make_the_header_believable(self):
        with patch.dict('os.environ', {'API_KEY': 'the-system-key'}):
            request = self.make_request(
                headers={'x-forwarded-for': '198.51.100.1', 'x-api-key': 'a-guess'}, host='203.0.113.50'
            )
            self.assertEqual(rate_limit.client_key(request), '203.0.113.50')

    def test_the_client_written_left_end_of_the_chain_is_not_believed(self):
        """A trusted proxy appends the real client; anything left of it is the client's own claim.
        Taking the left-most entry used to let every guess arrive under a fresh address."""
        request = self.make_request(headers={'x-forwarded-for': '1.2.3.4, 203.0.113.9, 172.16.0.10'})
        self.assertEqual(rate_limit.client_key(request), '203.0.113.9')

    def test_a_chain_of_trusted_hops_falls_back_to_the_left_most(self):
        """LMS not looking behind the proxy in front of it reports that proxy: the best there is."""
        request = self.make_request(headers={'x-forwarded-for': '172.16.0.10, 10.0.0.2'})
        self.assertEqual(rate_limit.client_key(request), '172.16.0.10')

    def test_an_ipv4_mapped_peer_is_recognised_as_trusted(self):
        request = self.make_request(headers={'x-forwarded-for': '203.0.113.9'}, host='::ffff:172.18.0.5')
        self.assertEqual(rate_limit.client_key(request), '203.0.113.9')

    def test_a_non_address_peer_is_not_trusted(self):
        request = self.make_request(headers={'x-forwarded-for': '203.0.113.9'}, host='testclient')
        self.assertEqual(rate_limit.client_key(request), 'testclient')

    def test_the_trusted_networks_are_configurable(self):
        with patch.dict('os.environ', {'AUTH_TRUSTED_PROXIES': '203.0.113.0/24, not-a-network'}):
            trusted = self.make_request(headers={'x-forwarded-for': '198.51.100.1'}, host='203.0.113.50')
            self.assertEqual(rate_limit.client_key(trusted), '198.51.100.1')
            # The private default is replaced, not extended.
            private = self.make_request(headers={'x-forwarded-for': '198.51.100.1'}, host='172.18.0.5')
            self.assertEqual(rate_limit.client_key(private), '172.18.0.5')

    def test_a_request_without_a_client_is_still_keyed(self):
        self.assertEqual(rate_limit.client_key(self.make_request(host=None)), 'unknown')


class ConfigurationTest(unittest.TestCase):
    def test_an_unparseable_limit_falls_back_to_the_default(self):
        with patch.dict('os.environ', {'AUTH_RATE_LIMIT_ATTEMPTS': 'many'}):
            self.assertEqual(rate_limit._int_env('AUTH_RATE_LIMIT_ATTEMPTS', 10), 10)

    def test_a_non_positive_limit_falls_back_to_the_default(self):
        with patch.dict('os.environ', {'AUTH_RATE_LIMIT_ATTEMPTS': '0'}):
            self.assertEqual(rate_limit._int_env('AUTH_RATE_LIMIT_ATTEMPTS', 10), 10)

    def test_the_limiter_can_be_switched_off(self):
        for value in ('0', 'false', 'NO'):
            with patch.dict('os.environ', {'AUTH_RATE_LIMIT_ENABLED': value}):
                self.assertFalse(rate_limit._enabled())

    def test_it_is_on_by_default(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertTrue(rate_limit._enabled())


class _FakeCursor:
    """Just enough cursor for the login endpoint's happy path."""

    def __init__(self, user):
        self._user = user
        self.lastrowid = 1

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return self._user


def _connection_returning(user):
    conn = MagicMock()
    conn.cursor.return_value = _FakeCursor(user)
    return conn


def _widen_windows(test):
    """Give every module-level limiter an hour-long window for the duration of `test`.

    The endpoint tests make ten-plus real logins, each a bcrypt check. On a loaded CI runner
    those took longer than the 60 s window, so the first attempts expired before the last one
    and the "refused" call came back 401 instead of 429 (backend:unit, 2026-09-27). The window
    arithmetic itself is covered by SlidingWindowTest with an injected clock.
    """
    for limiter in [
        value for value in vars(rate_limit).values() if isinstance(value, rate_limit.SlidingWindowRateLimiter)
    ]:
        patcher = patch.object(limiter, 'window_seconds', 3600)
        patcher.start()
        test.addCleanup(patcher.stop)


class AuthEndpointRateLimitTest(unittest.TestCase):
    def setUp(self):
        # A peer on the Docker network, like LMS or the nginx in front of the web-player host:
        # its X-Forwarded-For is believed, so a test can present a different client.
        self.client = TestClient(app, client=('172.18.0.5', 50000))
        rate_limit.reset_limiters()
        self.addCleanup(rate_limit.reset_limiters)
        _widen_windows(self)
        # No such user and no such refresh token: every call below is a genuine
        # rejection, which is what the limiter counts.
        self.answer_queries_with(None)

    def answer_queries_with(self, row):
        patcher = patch.object(users_router, 'get_db_connection', return_value=_connection_returning(row))
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self, username='root', password='wrong', client=None):
        headers = {'x-forwarded-for': client} if client else None
        return self.client.post('/api/auth/login', json={'username': username, 'password': password}, headers=headers)

    def test_a_burst_of_failed_logins_for_one_account_is_eventually_refused(self):
        for _ in range(rate_limit.auth_limiter.attempts):
            self.assertNotEqual(self.login().status_code, 429)
        refused = self.login()
        self.assertEqual(refused.status_code, 429)
        self.assertIn('Retry-After', refused.headers)

    def test_one_account_being_guessed_does_not_lock_out_another(self):
        """A login is bucketed per account, so a caller hammering one account
        leaves the others alone (see rate_limit's module doc)."""
        for _ in range(rate_limit.auth_limiter.attempts + 5):
            self.login(username='alice')
        self.assertNotEqual(self.login(username='bob').status_code, 429)

    def test_one_client_on_a_stale_password_does_not_lock_the_account_for_the_others(self):
        """LMS now passes the client address on, so a phone stuck on an old password
        uses up its own budget, not the account's (bug report 079)."""
        for _ in range(rate_limit.auth_limiter.attempts + 5):
            self.login(client='203.0.113.9')
        self.assertEqual(self.login(client='203.0.113.9').status_code, 429)
        self.assertNotEqual(self.login(client='198.51.100.7').status_code, 429)

    def test_guessing_spread_over_many_addresses_still_meets_an_account_ceiling(self):
        for n in range(rate_limit.account_limiter.attempts):
            self.assertNotEqual(self.login(client=f'198.51.100.{n % 250 + 1}').status_code, 429)
        refused = self.login(client='203.0.113.200')
        self.assertEqual(refused.status_code, 429)
        self.assertIn('Retry-After', refused.headers)
        # Another account is untouched by that ceiling.
        self.assertNotEqual(self.login(username='bob', client='203.0.113.200').status_code, 429)

    def test_a_forged_address_from_an_untrusted_caller_does_not_reset_its_budget(self):
        outsider = TestClient(app, client=('203.0.113.50', 50000))
        for n in range(rate_limit.auth_limiter.attempts):
            outsider.post(
                '/api/auth/login',
                json={'username': 'root', 'password': 'wrong'},
                headers={'x-forwarded-for': f'198.51.100.{n + 1}'},
            )
        refused = outsider.post(
            '/api/auth/login',
            json={'username': 'root', 'password': 'wrong'},
            headers={'x-forwarded-for': '198.51.100.99'},
        )
        self.assertEqual(refused.status_code, 429)

    def test_the_refresh_endpoint_has_its_own_budget(self):
        for _ in range(rate_limit.auth_limiter.attempts + 5):
            self.login()
        refresh = self.client.post('/api/auth/refresh', json={'refresh_token': 'x'})
        self.assertNotEqual(refresh.status_code, 429)

    def test_the_refresh_endpoint_is_limited_too(self):
        for _ in range(rate_limit.auth_limiter.attempts):
            self.client.post('/api/auth/refresh', json={'refresh_token': 'x'})
        refused = self.client.post('/api/auth/refresh', json={'refresh_token': 'x'})
        self.assertEqual(refused.status_code, 429)

    def test_the_setup_endpoint_is_limited_too(self):
        self.answer_queries_with({'count': 1})  # setup already completed
        for _ in range(rate_limit.auth_limiter.attempts):
            self.client.post('/api/auth/setup', json={'username': 'root', 'password': 'pw'})
        refused = self.client.post('/api/auth/setup', json={'username': 'root', 'password': 'pw'})
        self.assertEqual(refused.status_code, 429)

    def test_a_different_caller_is_not_affected(self):
        for _ in range(rate_limit.auth_limiter.attempts):
            self.client.post('/api/auth/refresh', json={'refresh_token': 'x'})
        other = self.client.post(
            '/api/auth/refresh', json={'refresh_token': 'x'}, headers={'x-forwarded-for': '203.0.113.9'}
        )
        self.assertNotEqual(other.status_code, 429)

    def test_an_authenticated_endpoint_is_not_rate_limited(self):
        for _ in range(rate_limit.auth_limiter.attempts + 5):
            self.login()
        verify = self.client.get('/api/auth/verify', headers={'x-api-key': users_router.API_KEY})
        self.assertEqual(verify.status_code, 200)

    def test_switching_the_limiter_off_lets_everything_through(self):
        with patch.dict('os.environ', {'AUTH_RATE_LIMIT_ENABLED': '0'}):
            for _ in range(rate_limit.auth_limiter.attempts + 5):
                self.assertNotEqual(self.login().status_code, 429)


class SuccessfulLoginsAreNotAttemptsTest(unittest.TestCase):
    """LMS re-checks the password against `/api/auth/login` on *every* Subsonic
    request (SubsonicResource.cpp -> MusicManagementPasswordService.cpp), so a
    single user browsing their library spends far more than ten successful
    logins a minute. Counting those as attempts logs the whole installation out.
    """

    def setUp(self):
        self.client = TestClient(app)
        rate_limit.reset_limiters()
        self.addCleanup(rate_limit.reset_limiters)
        _widen_windows(self)
        user = {'id': 1, 'username': 'root', 'enabled': True, 'password_hash': None, 'api_key': 'sekrit'}
        patcher = patch.object(users_router, 'get_db_connection', return_value=_connection_returning(user))
        patcher.start()
        self.addCleanup(patcher.stop)
        auth_user = patch.object(
            users_router, 'build_auth_user', return_value={'id': 1, 'username': 'root', 'permissions': []}
        )
        auth_user.start()
        self.addCleanup(auth_user.stop)

    def test_a_long_run_of_successful_logins_keeps_working(self):
        for _ in range(rate_limit.auth_limiter.attempts * 3):
            response = self.client.post('/api/auth/login', json={'username': 'root', 'password': 'sekrit'})
            self.assertEqual(response.status_code, 200)

    def test_a_correct_password_still_works_after_a_few_wrong_ones(self):
        for _ in range(rate_limit.auth_limiter.attempts - 1):
            self.client.post('/api/auth/login', json={'username': 'root', 'password': 'nope'})
        response = self.client.post('/api/auth/login', json={'username': 'root', 'password': 'sekrit'})
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
