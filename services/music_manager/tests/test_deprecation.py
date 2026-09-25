"""Deprecated routes announce themselves, and removed aliases stay removed.

See docs/bug-reports/084-unused-endpoints-and-duplicate-normalizers.md for the table of
which audited endpoint was kept, deprecated or removed, and why.
"""

import unittest
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.music_manager import deprecation
from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.main import app
from services.music_manager.routers import management as management_router

pytestmark = pytest.mark.mock_base('DatabaseConnector')

API_KEY = resolve_system_api_key()

#: No consumer in the repository: flagged, logged, removal date 2026-11-01.
DEPRECATED = {
    ('GET', '/api/about'),
    ('GET', '/api/rules/artist-redirects'),
    ('POST', '/api/rules/artist-redirects'),
    ('DELETE', '/api/rules/artist-redirects/{rule_id}'),
    ('POST', '/api/tagger/rescan/file'),
    ('POST', '/api/songs/tracks/{track_id}/split'),
    ('GET', '/api/downloaders/schedule/{source}'),
    ('GET', '/api/users/permissions'),
    ('POST', '/api/users/sync/lms-db'),
}

#: Aliases whose target every caller already uses.
REMOVED = {
    ('GET', '/api/users/{user_id}/lb-account'),
    ('PUT', '/api/users/{user_id}/lb-account'),
    ('POST', '/api/users/sync/lms'),
    ('POST', '/api/rating/server-event'),
}

#: Audited, but a consumer was found -- these must not be flagged.
KEPT = {
    ('GET', '/api/listening/clock'),
    ('GET', '/api/listening/sources'),
    ('POST', '/api/curation/retag'),
    ('GET', '/api/rating/ratings/{username}'),
    ('GET', '/api/users/{user_id}/listenbrainz'),
    ('PUT', '/api/users/{user_id}/listenbrainz'),
    ('POST', '/api/users/sync/muma-server'),
    ('POST', '/api/rating/lms-event'),
}


def _operations() -> dict[tuple[str, str], dict]:
    """Every published `(method, path)` with its OpenAPI operation."""
    return {
        (method.upper(), path): operation
        for path, operations in app.openapi()['paths'].items()
        for method, operation in operations.items()
    }


class DeprecationMarkTest(unittest.TestCase):
    def test_every_route_without_a_consumer_is_flagged_deprecated(self):
        operations = _operations()
        for key in sorted(DEPRECATED):
            with self.subTest(route=key):
                self.assertIn(key, operations)
                self.assertTrue(operations[key].get('deprecated'))

    def test_removed_aliases_are_gone(self):
        operations = _operations()
        for key in sorted(REMOVED):
            with self.subTest(route=key):
                self.assertNotIn(key, operations)

    def test_routes_with_a_consumer_are_published_and_not_flagged(self):
        operations = _operations()
        for key in sorted(KEPT):
            with self.subTest(route=key):
                self.assertIn(key, operations)
                self.assertFalse(operations[key].get('deprecated', False))


class DeprecationLogTest(unittest.TestCase):
    def setUp(self):
        deprecation.reset_seen()
        self.addCleanup(deprecation.reset_seen)
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}

    def _call_about(self):
        with (
            patch.object(management_router.os.path, 'exists', return_value=False),
            patch.object(management_router, 'markdown') as md,
        ):
            md.markdown.return_value = '<h1>Music Manager</h1>'
            return self.client.get('/api/about', headers=self.headers)

    def test_the_first_call_logs_the_route_the_caller_and_the_removal_date(self):
        with self.assertLogs('music-manager.deprecation', level='INFO') as logs:
            response = self._call_about()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(logs.records), 1)
        message = logs.records[0].getMessage()
        self.assertIn('GET /api/about', message)
        self.assertIn('testclient', message)
        self.assertIn(deprecation.REMOVAL_DATE, message)

    def test_later_calls_in_the_same_process_stay_quiet(self):
        with self.assertLogs('music-manager.deprecation', level='INFO') as logs:
            self._call_about()
            self._call_about()
            self._call_about()
        self.assertEqual(len(logs.records), 1)

    def test_a_route_counts_once_whatever_its_path_parameters(self):
        with (
            patch('services.music_manager.routers.downloaders.DatabaseCheckStore') as store,
            self.assertLogs('music-manager.deprecation', level='INFO') as logs,
        ):
            store.return_value.load.return_value = {}
            self.client.get('/api/downloaders/schedule/soundcloud', headers=self.headers)
            self.client.get('/api/downloaders/schedule/youtube', headers=self.headers)
        self.assertEqual(len(logs.records), 1)
        message = logs.records[0].getMessage()
        self.assertIn('GET /api/downloaders/schedule/soundcloud', message)
        self.assertIn('downloaders.get_schedule', message)

    def test_two_deprecated_routes_each_log_once(self):
        with self.assertLogs('music-manager.deprecation', level='INFO') as logs:
            self._call_about()
            with patch.object(management_router, 'ProcessedFilesHelper'):
                self.client.post('/api/tagger/rescan/file', headers=self.headers, json={'filepath': '/music/a.mp3'})
        self.assertEqual(len(logs.records), 2)

    def test_the_logger_is_one_the_event_stream_captures(self):
        from services.common.Helpers.logging_setup import ALLOWED_PREFIXES

        self.assertTrue(any(deprecation.logger.name.startswith(prefix) for prefix in ALLOWED_PREFIXES))


if __name__ == '__main__':
    unittest.main()
