"""Where the users router's routes are published.

`users.router` used to be mounted at `/api/users` and again at `/api` (for `/api/auth/*`), so
every user route also existed as `/api/{user_id}/...` -- `DELETE /api/{user_id}` included. The
session endpoints now live on `users.auth_router`, mounted at `/api` on its own.
"""

import unittest

import pytest

from services.music_manager.main import app

pytestmark = pytest.mark.mock_base('DatabaseConnector')


def _routes() -> set[tuple[str, str]]:
    """Every `(method, path)` the app publishes, read from its OpenAPI schema.

    `app.routes` holds included routers as opaque entries in this FastAPI version, so
    the schema -- built from the same route table -- is the flat list to read.
    """
    return {(method.upper(), path) for path, operations in app.openapi()['paths'].items() for method in operations}


class RouteMountTest(unittest.TestCase):
    def test_no_user_route_is_published_under_the_bare_api_prefix(self):
        leaked = sorted(path for _method, path in _routes() if path.startswith('/api/{user_id}'))
        self.assertEqual(leaked, [])

    def test_the_session_endpoints_stay_where_every_client_calls_them(self):
        routes = _routes()
        for method, path in (
            ('GET', '/api/auth/verify'),
            ('POST', '/api/auth/login'),
            ('POST', '/api/auth/refresh'),
            ('GET', '/api/auth/setup-status'),
            ('POST', '/api/auth/setup'),
            ('POST', '/api/auth/google'),
            ('POST', '/api/auth/access-request'),
        ):
            with self.subTest(path=path):
                self.assertIn((method, path), routes)

    def test_the_session_endpoints_are_not_repeated_under_users(self):
        self.assertFalse([path for _method, path in _routes() if path.startswith('/api/users/auth/')])

    def test_roles_answer_at_both_paths_the_clients_use(self):
        """Management.svelte, and the copy bundled in installed apps, fetch /api/roles."""
        routes = _routes()
        self.assertIn(('GET', '/api/roles'), routes)
        self.assertIn(('GET', '/api/users/roles'), routes)
        self.assertIn(('GET', '/api/users/permissions'), routes)

    def test_the_user_routes_are_still_under_users(self):
        routes = _routes()
        for method, path in (
            ('GET', '/api/users'),
            ('DELETE', '/api/users/{user_id}'),
            ('GET', '/api/users/{user_id}/settings/{app_id}'),
            ('POST', '/api/users/{user_id}/settings/{app_id}'),
            ('PATCH', '/api/users/{user_id}/settings/{app_id}'),
            ('GET', '/api/users/{user_id}/dynamic-playlists'),
            ('POST', '/api/users/sync/muma-server'),
        ):
            with self.subTest(path=path):
                self.assertIn((method, path), routes)


if __name__ == '__main__':
    unittest.main()
