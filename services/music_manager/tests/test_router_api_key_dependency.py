"""Every router checks X-API-Key through the one dependency in routers/users.py.

Eleven routers used to carry their own `verify_api_key`. Some swallowed every
exception from `verify_token` and answered 401 "Invalid API key", so a database outage
logged every client out with a message blaming their key; the others were thin
wrappers around the canonical check, each one a place the swallowing copy could come
back. All of them now import `users.verify_api_key` itself. See
docs/bug-reports/065-router-key-check-copies-and-repeated-provider-warnings.md.
"""

import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient

from services.music_manager import database
from services.music_manager.main import app
from services.music_manager.routers import (
    analytics,
    artist_images,
    bpm,
    downloaders,
    feeds,
    library,
    listening,
    management,
    news,
    radio,
    rating,
    scanner,
    scrobbler,
    songs,
    stats,
    tagger,
)

ROUTERS_DIR = Path(users_router.__file__).parent

#: One protected route per router, called with a key no account holds. Only the key
#: check runs: it refuses before any handler (or scan, or tagging round) starts.
PROTECTED_ROUTES = [
    ('get', '/api/stats/'),
    ('get', '/api/library/genres'),
    ('get', '/api/library/bpm/histogram'),
    ('get', '/api/analytics/summary'),
    ('post', '/api/scanner/scan/file'),
    ('get', '/api/artists/search'),
    ('get', '/api/feeds/'),
    ('get', '/api/listening/summary'),
    ('get', '/api/scrobble/import/latest'),
    ('get', '/api/rating/ratings/listener'),
    ('post', '/api/tagger/tag/stop'),
    ('get', '/api/config/'),
    ('get', '/api/songs/1'),
    ('get', '/api/downloaders/settings'),
    ('get', '/api/radio/channels'),
    ('get', '/api/news/sources'),
    ('get', '/api/rules'),
    ('get', '/api/diagnostics/crash-reports/1'),
    ('get', '/api/events'),
    ('get', '/api/users'),
]

UNKNOWN_KEY = {'x-api-key': 'a-key-no-account-holds'}


def cursor_connection(fetchone=None):
    """A connection whose cursor answers `fetchone` for the users lookup."""
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    conn.cursor.return_value.__exit__.return_value = False
    cursor.fetchone.return_value = fetchone
    return conn


class ProtectedRouteTest(unittest.TestCase):
    """Unknown key 401, database outage 503 -- on every router, from the same check."""

    def setUp(self):
        self.client = TestClient(app)

    def call(self, method, path):
        return getattr(self.client, method)(path, headers=UNKNOWN_KEY)

    def test_an_unknown_key_is_a_401_everywhere(self):
        with patch.object(users_router, 'get_db_connection', return_value=cursor_connection(None)):
            for method, path in PROTECTED_ROUTES:
                with self.subTest(path=path):
                    response = self.call(method, path)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json()['detail'], users_router.INVALID_API_KEY)

    def test_a_database_outage_is_a_503_everywhere(self):
        for label, patcher in (
            ('no pool', patch.object(users_router, 'get_db_connection', return_value=None)),
            ('connect error', patch.object(users_router, 'get_db_connection', side_effect=OSError('refused'))),
            (
                'pool exhausted',
                patch.object(users_router, 'get_db_connection', side_effect=database.DatabaseBusyError('busy')),
            ),
        ):
            with patcher:
                for method, path in PROTECTED_ROUTES:
                    with self.subTest(outage=label, path=path):
                        response = self.call(method, path)
                        self.assertEqual(response.status_code, 503)
                        self.assertEqual(response.headers.get('Retry-After'), '5')


class NoPrivateCopyTest(unittest.TestCase):
    """No router module defines its own key check; they all hold the canonical one."""

    OWN_CHECK_NAMES = {'verify_api_key', '_verify_api_key', 'require_api_key', '_verify'}

    def test_no_router_defines_a_key_check_of_its_own(self):
        offenders = []
        for path in sorted(ROUTERS_DIR.glob('*.py')):
            if path.name == 'users.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in self.OWN_CHECK_NAMES:
                    offenders.append(f'{path.name}:{node.lineno} {node.name}')
        self.assertEqual(offenders, [], 'import verify_api_key from routers/users.py instead')

    def test_every_router_name_is_the_canonical_dependency(self):
        # config.py is absent on purpose: every route there goes through
        # rbac.require_permission, which calls the canonical check itself.
        for module in (
            analytics,
            artist_images,
            bpm,
            downloaders,
            feeds,
            library,
            listening,
            management,
            news,
            radio,
            rating,
            scanner,
            scrobbler,
            songs,
            stats,
            tagger,
        ):
            with self.subTest(module=module.__name__):
                self.assertIs(module.verify_api_key, users_router.verify_api_key)


class RequireConnectionTest(unittest.TestCase):
    """The routers' own "no connection" checks answer 503 through database.require_connection."""

    def test_a_connection_is_passed_through(self):
        conn = object()
        self.assertIs(database.require_connection(conn), conn)

    def test_no_pool_raises_the_unavailable_error(self):
        with self.assertRaises(database.DatabaseUnavailableError):
            database.require_connection(None)

    def test_a_router_without_a_pool_answers_503_not_500(self):
        admin = {'status': 'ok', 'type': 'system'}
        with (
            patch.object(users_router, 'verify_token', return_value=admin),
            patch.object(songs, 'get_db_connection', return_value=None),
        ):
            response = TestClient(app).get('/api/songs/1', headers=UNKNOWN_KEY)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get('Retry-After'), '5')


if __name__ == '__main__':
    unittest.main()
