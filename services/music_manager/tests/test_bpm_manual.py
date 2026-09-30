"""The manual BPM override (bug report 140): PUT/DELETE /api/library/bpm/tracks/{id}/manual."""

import json
import unittest
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

import services.music_manager.routers.users as users_router  # noqa: E402
from services.music_manager.api_key import resolve_system_api_key  # noqa: E402

users_router.run_lms_db_sync = lambda only_sources=None: None

from fastapi.testclient import TestClient  # noqa: E402

from services.music_manager import rbac  # noqa: E402
from services.music_manager.bpm import effective  # noqa: E402
from services.music_manager.main import app  # noqa: E402
from services.music_manager.routers import bpm as bpm_router  # noqa: E402

API_KEY = resolve_system_api_key()
URL = '/api/library/bpm/tracks/{}/manual'


class FakeDb:
    """One track (id 5): measured at 256 (raw 64, the André Hazes case), optionally set by hand."""

    def __init__(self, manual=None, measured=256.0, exists=True):
        self.manual = manual
        self.measured = measured
        self.exists = exists
        self.audit = []
        self.commits = 0
        self._last = None

    # -- the connection
    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self):
        self.commits += 1

    def close(self):
        pass

    # -- the cursor
    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        if text.startswith('SELECT track_uid FROM library_tracks'):
            self._last = {'track_uid': 'uid-5'} if self.exists else None
        elif 'AS manual' in text:
            self._last = {
                'track_id': 5,
                'manual': self.manual,
                'bpm_tag': None,
                'tempo': None,
                'measured': self.measured,
                'measured_confidence': 0.5,
                'measured_folded': 1,
                'genres': '',
            }
        elif text.startswith('SELECT bpm, raw_bpm FROM library_track_bpm'):
            self._last = {'bpm': self.measured, 'raw_bpm': 64.0} if self.measured else None
        elif text.startswith('INSERT INTO library_track_bpm_manual'):
            self.manual = params[1]
        elif text.startswith('DELETE FROM library_track_bpm_manual'):
            self.manual = None
        elif text.startswith('INSERT INTO audit_events'):
            self.audit.append(params)
        else:  # pragma: no cover - a statement the test does not know
            raise AssertionError(f'unexpected SQL: {text}')

    def fetchone(self):
        return self._last


class ManualOverrideTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.db = FakeDb()
        for target, value in (
            ('get_db_connection', lambda: self.db),
            ('reliable_confidence', lambda: 0.75),
        ):
            patcher = patch.object(bpm_router, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        sync = patch.object(bpm_router.effective_table, 'sync')
        self.sync = sync.start()
        self.addCleanup(sync.stop)
        stale = patch.object(bpm_router.index_cache, 'mark_stale')
        self.stale = stale.start()
        self.addCleanup(stale.stop)

    def put(self, body, track_id=5):
        return self.client.put(URL.format(track_id), json=body, headers=self.headers)

    def test_halving_the_shown_tempo_stores_it_as_manual(self):
        response = self.put({'factor': 0.5})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body['bpm'], body['bpm_source'], body['bpm_confidence']), (128.0, 'manual', 'high'))
        self.assertEqual((body['measured_bpm'], body['raw_bpm']), (256.0, 64.0))
        self.assertEqual(self.db.manual, 128.0)

    def test_doubling_and_setting_a_value(self):
        self.db.measured = 115.0
        self.assertEqual(self.put({'factor': 2}).json()['bpm'], 230.0)
        self.assertEqual(self.put({'bpm': 115.4}).json()['bpm'], 115.4)

    def test_the_change_is_audited_and_the_derived_data_follows(self):
        self.put({'factor': 0.5})
        event_type, _actor, _target, details = self.db.audit[0]
        self.assertEqual(event_type, 'bpm.manual_set')
        self.assertEqual(json.loads(details), {
            'track_id': 5, 'bpm': 128.0, 'factor': 0.5, 'previous_bpm': 256.0, 'previous_source': 'measured',
        })  # fmt: skip
        self.assertEqual(self.sync.call_args.kwargs['track_ids'], [5])
        self.stale.assert_called_once()
        self.assertEqual(self.db.commits, 1)

    def test_clearing_returns_to_the_measurement_and_is_audited(self):
        self.db.manual = 128.0
        body = self.client.delete(URL.format(5), headers=self.headers).json()
        self.assertEqual((body['bpm'], body['bpm_source']), (256.0, 'measured'))
        self.assertIsNone(self.db.manual)
        self.assertEqual(self.db.audit[0][0], 'bpm.manual_cleared')

    def test_clearing_without_a_manual_tempo_audits_nothing(self):
        self.client.delete(URL.format(5), headers=self.headers)
        self.assertEqual(self.db.audit, [])

    def test_bad_requests(self):
        self.assertEqual(self.put({}).status_code, 400)
        self.assertEqual(self.put({'bpm': 120, 'factor': 2}).status_code, 400)
        self.assertEqual(self.put({'bpm': 20}).status_code, 400)
        self.assertEqual(self.put({'factor': 3}).status_code, 422)
        self.db.measured = 300.0
        self.assertEqual(self.put({'factor': 2}).status_code, 400)  # 600 is not a tempo
        self.assertIsNone(self.db.manual)

    def test_halving_nothing_is_a_conflict(self):
        self.db.measured = None
        self.assertEqual(self.put({'factor': 0.5}).status_code, 409)

    def test_an_unknown_track_is_404(self):
        self.db.exists = False
        self.assertEqual(self.put({'bpm': 120}).status_code, 404)

    def test_it_needs_the_override_permission(self):
        without = {'type': 'user', 'user': {'id': 9, 'permissions': ['music.read']}}
        with patch.object(users_router, 'verify_api_key', return_value=without):
            self.assertEqual(self.put({'bpm': 120}).status_code, 403)
            self.assertEqual(self.client.delete(URL.format(5), headers=self.headers).status_code, 403)
        granted = {'type': 'user', 'user': {'id': 9, 'permissions': ['bpm.override']}}
        with patch.object(users_router, 'verify_api_key', return_value=granted):
            self.assertEqual(self.put({'bpm': 120}).status_code, 200)
        self.assertEqual(self.db.audit[-1][1], 9)

    def test_the_permission_is_seeded(self):
        self.assertIn(bpm_router.OVERRIDE_PERMISSION, {name for name, _ in rbac.PERMISSIONS})
        self.assertNotIn(bpm_router.OVERRIDE_PERMISSION, rbac.USER_ROLE_PERMISSIONS)


class ManualPrecedenceTest(unittest.TestCase):
    def test_a_manual_tempo_beats_every_other_source(self):
        found = effective.resolve(manual=128.0, measured=256.0, measured_confidence=0.99, tag=150.0, tempo=151.0)
        self.assertEqual((found.bpm, found.source, found.confidence), (128.0, 'manual', 'high'))
        self.assertFalse(found.folded or found.approximate)

    def test_an_implausible_manual_value_is_ignored(self):
        found = effective.resolve(manual=0.0, measured=150.0, measured_confidence=0.9)
        self.assertEqual(found.source, 'measured')

    def test_resolve_row_reads_the_manual_column(self):
        found = effective.resolve_row({'manual': 99.0, 'measured': 198.0, 'measured_confidence': 0.9})
        self.assertEqual((found.bpm, found.source), (99.0, 'manual'))


if __name__ == '__main__':
    unittest.main()
