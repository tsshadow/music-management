"""Tests for the daily production check of the music mirror."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, call, patch

from tools import music_mirror_check

NOW = datetime(2026, 11, 13, 9, 42, tzinfo=UTC)


def write_status(directory, hours_ago=8, **overrides):
    """A status file in ``directory``; a good run by default."""
    payload = {
        'run_id': 'r',
        'result': 'ok',
        'finished_at': (NOW - timedelta(hours=hours_ago)).isoformat(),
        'files_total': 412000,
        'files_transferred': 37,
        'bytes_transferred': 1_200_000_000,
        'snapshot': 'mirror-20261113T014412Z',
        'sample': {'checked': 200, 'differing': []},
        'orphans': {'files': 12, 'bytes': 300_000_000},
        'pool_used_percent': 61,
    }
    payload.update(overrides)
    Path(directory, 'latest.json').write_text(json.dumps(payload), encoding='utf-8')


class RunTest(unittest.TestCase):
    def setUp(self):
        self._dir = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self._dir.cleanup)
        self.dir = self._dir.name
        sink = patch.object(music_mirror_check, 'NtfySink')
        self.sink = sink.start().return_value
        self.addCleanup(sink.stop)
        service = patch.object(music_mirror_check, 'event_service')
        self.events = service.start()
        self.addCleanup(service.stop)

    def recorded(self):
        return [c.args[0] for c in self.events.record_now.call_args_list]

    def test_a_recent_good_run_is_one_info_row_without_a_push(self):
        write_status(self.dir)
        self.assertEqual(music_mirror_check.run(self.dir, now=NOW), 0)
        (event,) = self.recorded()
        self.assertEqual((event.level, event.source, event.push), ('INFO', 'music-mirror', False))
        self.assertIn('412000 files', event.message)
        self.assertIn('1.2 GB', event.message)
        self.sink.handle.assert_not_called()

    def test_a_good_run_older_than_a_day_is_not_reported_twice(self):
        write_status(self.dir, hours_ago=30)
        self.assertEqual(music_mirror_check.run(self.dir, now=NOW), 0)
        self.assertEqual(self.recorded(), [])

    def test_a_failed_run_pushes_first_then_records(self):
        order = MagicMock()
        self.sink.handle.side_effect = lambda e: order('push', e.level)
        self.events.record_now.side_effect = lambda e: order('row', e.level)
        write_status(self.dir, result='failed', reason='rsync exit 12')
        self.assertEqual(music_mirror_check.run(self.dir, now=NOW), 1)
        self.assertEqual(order.call_args_list, [call('push', 'ERROR'), call('row', 'ERROR')])
        event = self.recorded()[0]
        self.assertEqual(event.title, 'Music mirror failed')
        self.assertEqual(event.message, 'rsync exit 12')
        self.assertTrue(event.push)

    def test_a_stale_status_alerts(self):
        write_status(self.dir, hours_ago=40)
        self.assertEqual(music_mirror_check.run(self.dir, now=NOW), 1)
        self.assertEqual(self.recorded()[0].title, 'Music mirror stale')

    def test_no_status_path_alerts(self):
        self.assertEqual(music_mirror_check.run(None, now=NOW), 1)
        self.assertEqual(self.recorded()[0].title, 'Music mirror unconfigured')

    def test_a_failing_push_still_records_the_row(self):
        self.sink.handle.side_effect = OSError('ntfy down')
        write_status(self.dir, result='refused', reason='too much would change')
        self.assertEqual(music_mirror_check.run(self.dir, now=NOW), 1)
        self.assertEqual(len(self.recorded()), 1)

    def test_main_reads_the_environment(self):
        write_status(self.dir)
        with patch.dict('os.environ', {'MIRROR_STATUS_PATH': self.dir}), patch.object(music_mirror_check, 'run') as run:
            music_mirror_check.main()
        run.assert_called_once_with(self.dir)


class SummaryTest(unittest.TestCase):
    def test_missing_numbers_show_a_dash(self):
        self.assertIn('copied (-)', music_mirror_check.summary({}))


if __name__ == '__main__':
    unittest.main()
