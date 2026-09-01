"""The authentication endpoints stop answering once a caller hammers them."""

import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda: None

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
    def make_request(self, headers=None, host='10.0.0.1'):
        request = MagicMock()
        request.headers = headers or {}
        request.client = MagicMock(host=host) if host else None
        return request

    def test_the_peer_address_is_used_without_a_proxy_header(self):
        self.assertEqual(rate_limit.client_key(self.make_request()), '10.0.0.1')

    def test_the_left_most_forwarded_address_wins(self):
        request = self.make_request(headers={'x-forwarded-for': '203.0.113.9, 10.0.0.1'})
        self.assertEqual(rate_limit.client_key(request), '203.0.113.9')

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


class AuthEndpointRateLimitTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        rate_limit.auth_limiter.reset()
        self.addCleanup(rate_limit.auth_limiter.reset)
        # No such user and no such refresh token: every call below is a genuine
        # rejection, which is what the limiter counts.
        self.answer_queries_with(None)

    def answer_queries_with(self, row):
        patcher = patch.object(users_router, 'get_db_connection', return_value=_connection_returning(row))
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self, username='root', password='wrong'):
        return self.client.post('/api/auth/login', json={'username': username, 'password': password})

    def test_a_burst_of_failed_logins_for_one_account_is_eventually_refused(self):
        for _ in range(rate_limit.auth_limiter.attempts):
            self.assertNotEqual(self.login().status_code, 429)
        refused = self.login()
        self.assertEqual(refused.status_code, 429)
        self.assertIn('Retry-After', refused.headers)

    def test_one_account_being_guessed_does_not_lock_out_another(self):
        """The LMS -> music-manager hop carries no client address, so every user
        would otherwise share a single bucket (see rate_limit's module doc)."""
        for _ in range(rate_limit.auth_limiter.attempts + 5):
            self.login(username='alice')
        self.assertNotEqual(self.login(username='bob').status_code, 429)

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
        rate_limit.auth_limiter.reset()
        self.addCleanup(rate_limit.auth_limiter.reset)
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
