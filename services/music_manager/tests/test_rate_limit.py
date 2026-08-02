"""The authentication endpoints stop answering once a caller hammers them."""
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.ntfy_listener
services.music_manager.ntfy_listener.start_ntfy_listener = lambda: None
import services.music_manager.routers.users as users_router
users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager import rate_limit
from services.music_manager.main import app


class SlidingWindowTest(unittest.TestCase):

    def setUp(self):
        self.limiter = rate_limit.SlidingWindowRateLimiter(attempts=3, window_seconds=60)

    def test_attempts_up_to_the_limit_are_allowed(self):
        for attempt in range(3):
            allowed, retry_after = self.limiter.check('caller', now=attempt)
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0)

    def test_the_attempt_past_the_limit_is_refused(self):
        for attempt in range(3):
            self.limiter.check('caller', now=attempt)
        allowed, retry_after = self.limiter.check('caller', now=3)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_the_window_slides_rather_than_resetting_in_blocks(self):
        """With fixed buckets a caller gets the whole allowance twice across a
        boundary; with a sliding window each attempt expires on its own."""
        for attempt in range(3):
            self.limiter.check('caller', now=attempt)
        self.assertFalse(self.limiter.check('caller', now=59)[0])
        # The first attempt (t=0) leaves the window at t=60, freeing one slot.
        self.assertTrue(self.limiter.check('caller', now=61)[0])
        self.assertFalse(self.limiter.check('caller', now=61)[1] == -1)

    def test_callers_are_counted_separately(self):
        for attempt in range(3):
            self.limiter.check('first', now=attempt)
        self.assertFalse(self.limiter.check('first', now=3)[0])
        self.assertTrue(self.limiter.check('second', now=3)[0])

    def test_the_retry_hint_shrinks_as_the_window_moves_on(self):
        for attempt in range(3):
            self.limiter.check('caller', now=attempt)
        early = self.limiter.check('caller', now=10)[1]
        later = self.limiter.check('caller', now=50)[1]
        self.assertGreater(early, later)

    def test_resetting_one_caller_leaves_the_others_alone(self):
        for attempt in range(3):
            self.limiter.check('first', now=attempt)
            self.limiter.check('second', now=attempt)
        self.limiter.reset('first')
        self.assertTrue(self.limiter.check('first', now=3)[0])
        self.assertFalse(self.limiter.check('second', now=3)[0])

    def test_resetting_everything_clears_every_caller(self):
        self.limiter.check('first', now=0)
        self.limiter.reset()
        self.assertTrue(self.limiter.check('first', now=0)[0])


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


class AuthEndpointRateLimitTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        rate_limit.auth_limiter.reset()
        self.addCleanup(rate_limit.auth_limiter.reset)
        patcher = patch.object(users_router, 'get_db_connection', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self):
        return self.client.post('/api/auth/login', json={'username': 'root', 'password': 'wrong'})

    def test_a_burst_of_logins_is_eventually_refused(self):
        limit = rate_limit.auth_limiter.attempts
        for _ in range(limit):
            self.assertNotEqual(self.login().status_code, 429)
        refused = self.login()
        self.assertEqual(refused.status_code, 429)
        self.assertIn('Retry-After', refused.headers)

    def test_the_refresh_endpoint_shares_the_same_budget(self):
        for _ in range(rate_limit.auth_limiter.attempts):
            self.login()
        refused = self.client.post('/api/auth/refresh', json={'refresh_token': 'x'})
        self.assertEqual(refused.status_code, 429)

    def test_the_setup_endpoint_is_limited_too(self):
        for _ in range(rate_limit.auth_limiter.attempts):
            self.login()
        refused = self.client.post('/api/auth/setup', json={'username': 'root', 'password': 'pw'})
        self.assertEqual(refused.status_code, 429)

    def test_a_different_caller_is_not_affected(self):
        for _ in range(rate_limit.auth_limiter.attempts):
            self.login()
        other = self.client.post('/api/auth/login', json={'username': 'root', 'password': 'wrong'},
                                 headers={'x-forwarded-for': '203.0.113.9'})
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


if __name__ == '__main__':
    unittest.main()
