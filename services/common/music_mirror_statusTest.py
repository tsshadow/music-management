"""Tests for the music mirror's status verdict, shared by /health/music-mirror and the daily check."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from services.common import music_mirror_status as mms

NOW = datetime(2026, 11, 13, 9, 42, tzinfo=UTC)


def good_payload(**overrides):
    """A status file of a good run that finished eight hours before NOW."""
    payload = {
        'run_id': '20261113T013000Z',
        'result': 'ok',
        'reason': None,
        'finished_at': (NOW - timedelta(hours=8)).isoformat(),
        'files_total': 412000,
        'files_transferred': 37,
        'bytes_transferred': 1_200_000_000,
        'snapshot': 'mirror-20261113T014412Z',
        'sample': {'checked': 200, 'differing': []},
        'orphans': {'files': 12, 'bytes': 300_000_000},
        'full_checksum': {'at': None, 'differing': None, 'differing_count': None},
        'pool_used_percent': 61,
    }
    payload.update(overrides)
    return payload


class EvaluateTest(unittest.TestCase):
    """One test per status, in the order evaluate() checks them."""

    def setUp(self):
        self._dir = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self._dir.cleanup)
        self.dir = self._dir.name

    def write(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        Path(self.dir, 'latest.json').write_text(text, encoding='utf-8')

    def verdict(self, **kwargs):
        return mms.evaluate(self.dir, now=NOW, **kwargs)

    def test_ok_for_a_recent_good_run(self):
        self.write(good_payload())
        verdict = self.verdict()
        self.assertTrue(verdict.healthy)
        self.assertEqual(verdict.status, 'ok')
        self.assertEqual(verdict.details['age_hours'], 8.0)
        self.assertEqual(verdict.details['snapshot'], 'mirror-20261113T014412Z')
        self.assertEqual(verdict.as_dict()['status'], 'ok')

    def test_unconfigured_without_a_directory(self):
        self.assertEqual(mms.evaluate(None, now=NOW).status, 'unconfigured')
        self.assertEqual(mms.evaluate('', now=NOW).status, 'unconfigured')

    def test_missing_without_a_status_file(self):
        verdict = self.verdict()
        self.assertEqual(verdict.status, 'missing')
        self.assertFalse(verdict.healthy)

    def test_unreadable_for_broken_json(self):
        self.write('{"result": "ok", ')
        self.assertEqual(self.verdict().status, 'unreadable')

    def test_unreadable_for_a_list(self):
        self.write('[]')
        self.assertEqual(self.verdict().status, 'unreadable')

    def test_unreadable_without_a_time_zone(self):
        self.write(good_payload(finished_at='2026-11-13T01:30:00'))
        self.assertIn('time zone', self.verdict().reason)

    def test_unreadable_without_finished_at(self):
        payload = good_payload()
        del payload['finished_at']
        self.write(payload)
        self.assertEqual(self.verdict().status, 'unreadable')

    def test_failed_names_the_reason_even_when_recent(self):
        self.write(good_payload(result='failed', reason='rsync exit 12'))
        verdict = self.verdict()
        self.assertEqual(verdict.status, 'failed')
        self.assertEqual(verdict.reason, 'rsync exit 12')

    def test_refused_names_the_reason(self):
        self.write(good_payload(result='refused', reason='the library lists 100 files'))
        self.assertEqual(self.verdict().status, 'refused')

    def test_unknown_result_is_unreadable(self):
        self.write(good_payload(result='maybe'))
        self.assertEqual(self.verdict().status, 'unreadable')

    def test_differing_sample(self):
        self.write(good_payload(sample={'checked': 200, 'differing': ['Labels/A/1.flac', 'Labels/B/2.flac']}))
        verdict = self.verdict()
        self.assertEqual(verdict.status, 'differing')
        self.assertEqual(verdict.files, ('Labels/A/1.flac', 'Labels/B/2.flac'))
        self.assertNotIn('Labels/A/1.flac', json.dumps(verdict.as_dict()))
        self.assertEqual(verdict.details['sample_differing'], 2)

    def test_differing_full_checksum(self):
        full = {'at': NOW.isoformat(), 'differing': ['Sets/x.mp3'], 'differing_count': 1}
        self.write(good_payload(full_checksum=full))
        verdict = self.verdict()
        self.assertEqual(verdict.status, 'differing')
        self.assertEqual(verdict.files, ('Sets/x.mp3',))
        self.assertNotIn('Sets/x.mp3', json.dumps(verdict.as_dict()))

    def test_stale_past_the_limit(self):
        self.write(good_payload(finished_at=(NOW - timedelta(hours=37)).isoformat()))
        self.assertEqual(self.verdict().status, 'stale')

    def test_limit_can_be_given(self):
        self.write(good_payload())
        self.assertEqual(self.verdict(limit_hours=4).status, 'stale')

    def test_limit_from_the_environment(self):
        self.write(good_payload())
        with patch.dict('os.environ', {'MIRROR_STALE_AFTER_HOURS': '6'}):
            self.assertEqual(self.verdict().status, 'stale')
        with patch.dict('os.environ', {'MIRROR_STALE_AFTER_HOURS': 'soon'}):
            self.assertEqual(mms.stale_after_hours(), 36)


if __name__ == '__main__':
    unittest.main()
