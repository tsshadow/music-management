"""Every route that changes something names who may call it (issue #216).

A write route (POST, PUT, PATCH, DELETE) passes when one of its dependencies is a permission
gate: `rbac.require_permission`, `rbac.require_admin`, or a `require_*` check a router builds
on them. A route that takes any login and checks the caller in its own body -- "only your own
account, unless admin" -- is listed in LOGIN_ONLY with the reason. A new write route that is
neither fails here, so "any enabled account may do this" is a choice someone wrote down and not
the default: bug reports 037 and 052 and issue #216 each found routes where it was the default.

Routes are read from each router module rather than from `app.routes`: FastAPI changed how
an app keeps included routers, and the router's own list is the same in every version.
"""

import importlib
import pkgutil
import unittest

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi import APIRouter

import services.music_manager.main  # noqa: F401 -- imports every router, as the app does
import services.music_manager.routers as routers_package

WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

#: (router module, method, path inside the router) -> why any login is enough here.
LOGIN_ONLY = {
    ('diagnostics', 'POST', '/crash-reports'): 'every app install uploads its own crash reports',
    ('diagnostics', 'PATCH', '/crash-reports/{report_id}/status'): 'body: _require_system',
    ('feeds', 'PUT', '/profile/exclusions'): "the caller's own feed profile",
    ('management', 'POST', '/scrobble/import/listenbrainz'): 'delegates to scrobbler: own account unless admin',
    ('scrobbler', 'POST', '/event'): 'body: _may_write_history_for, own history unless admin',
    ('scrobbler', 'POST', '/import/listenbrainz'): 'body: _may_write_history_for, own history unless admin',
    ('users', 'POST', ''): 'body: users.create',
    ('users', 'POST', '/'): 'body: users.create',
    ('users', 'POST', '/{user_id}/password'): 'body: own account, or admin',
    ('users', 'PUT', '/{user_id}/password'): 'body: own account, or admin',
    ('users', 'POST', '/{user_id}/sessions/revoke'): 'body: own sessions, or users.revoke-sessions',
    ('users', 'POST', '/{user_id}/settings/{app_id}'): 'body: own settings, or users.update',
    ('users', 'PATCH', '/{user_id}/settings/{app_id}'): 'body: own settings, or users.update',
    ('users', 'POST', '/{user_id}/listenbrainz'): 'body: own account, or users.update',
    ('users', 'PUT', '/{user_id}/listenbrainz'): 'body: own account, or users.update',
    ('users', 'POST', '/{user_id}/dynamic-playlists'): 'body: own playlists, or users.update',
    ('users', 'PUT', '/{user_id}/dynamic-playlists/{playlist_id}'): 'body: own playlists, or users.update',
    ('users', 'DELETE', '/{user_id}/dynamic-playlists/{playlist_id}'): 'body: own playlists, or users.update',
    ('users', 'POST', '/{user_id}/dynamic-playlists/seed-defaults'): 'body: own playlists, or users.update',
}

#: Write routes without any key: signing in and asking for an account.
PUBLIC = {
    ('users', 'POST', '/auth/login'),
    ('users', 'POST', '/auth/refresh'),
    ('users', 'POST', '/auth/setup'),
    ('user_requests', 'POST', '/auth/google'),
    ('user_requests', 'POST', '/auth/access-request'),
}


def dependency_calls(dependant):
    """Every callable a route depends on, nested ones included."""
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from dependency_calls(dependency)


def is_gate(call) -> bool:
    """A permission check: rbac's factories, or a router's own `require_*` built on them."""
    name = getattr(call, '__qualname__', '')
    return name.startswith('require_')


def write_routes():
    """(module name, method, path, dependency calls) for every write route of every router."""
    for info in pkgutil.iter_modules(routers_package.__path__):
        module = importlib.import_module(f'{routers_package.__name__}.{info.name}')
        routers = {id(value): value for value in vars(module).values() if isinstance(value, APIRouter)}
        for router in routers.values():
            for route in router.routes:
                if not hasattr(route, 'dependant'):
                    continue
                calls = list(dependency_calls(route.dependant))
                for method in sorted(set(route.methods or ()) & WRITE_METHODS):
                    yield info.name, method, route.path, calls


class RoutePermissionMatrixTest(unittest.TestCase):
    def test_every_write_route_has_a_gate_or_a_written_reason(self):
        ungated = []
        for module, method, path, calls in write_routes():
            key = (module, method, path)
            if key in LOGIN_ONLY or key in PUBLIC:
                continue
            if not any(is_gate(call) for call in calls):
                ungated.append(f'{module}: {method} {path}')
        self.assertEqual(
            ungated,
            [],
            'Give these routes a permission (rbac.require_permission) or add them to LOGIN_ONLY with the reason',
        )

    def test_the_lists_name_only_routes_that_exist_and_need_them(self):
        found = {(module, method, path): calls for module, method, path, calls in write_routes()}
        for key in sorted(set(LOGIN_ONLY) | PUBLIC):
            with self.subTest(route=key):
                self.assertIn(key, found, 'listed route no longer exists: remove it from the list')
                self.assertFalse(
                    any(is_gate(call) for call in found[key]), 'route has a gate now: remove it from the list'
                )

    def test_a_route_this_test_found_before_issue_216_is_gated(self):
        # Guards the walk itself: if it ever stops seeing the routers, the first test passes
        # on an empty list.
        found = {(module, method, path): calls for module, method, path, calls in write_routes()}
        self.assertGreater(len(found), 100)
        self.assertTrue(any(is_gate(call) for call in found[('tagger', 'POST', '/tag/all')]))
