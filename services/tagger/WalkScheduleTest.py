"""Coverage for services/tagger/walk_schedule.py: the daily walk survives restarts."""

import tempfile
import unittest
from pathlib import Path

from services.tagger.walk_schedule import WalkSchedule

HOUR = 3600.0


class WalkScheduleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'nested' / 'tagger_last_walk'

    def schedule(self, hours=24):
        return WalkSchedule(hours, path=self.path)

    def test_an_interval_of_zero_walks_every_round(self):
        self.assertTrue(self.schedule(0).due(now=1000.0))
        self.assertTrue(self.schedule(0).due(now=1000.0))

    def test_a_first_start_serves_the_queue_and_starts_the_clock(self):
        # Five deploys in a night used to be five walks from EPs; the queue is the work.
        schedule = self.schedule()
        self.assertFalse(schedule.due(now=1000.0))
        self.assertEqual(schedule.last_walk_at(), 1000.0)

    def test_the_walk_is_due_once_the_interval_has_passed(self):
        schedule = self.schedule(24)
        schedule.record(now=1000.0)
        self.assertFalse(schedule.due(now=1000.0 + 23 * HOUR))
        self.assertTrue(schedule.due(now=1000.0 + 24 * HOUR))

    def test_the_record_outlives_the_process(self):
        self.schedule().record(now=5000.0)
        self.assertEqual(self.schedule().last_walk_at(), 5000.0)
        self.assertFalse(self.schedule().due(now=5000.0 + HOUR))

    def test_a_corrupt_record_counts_as_no_record(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('yesterday')
        self.assertIsNone(self.schedule().last_walk_at())

    def test_an_unwritable_record_is_logged_not_raised(self):
        schedule = WalkSchedule(24, path=Path('/proc/nope/tagger_last_walk'))
        with self.assertLogs('music-manager.tagger', level='WARNING'):
            schedule.record(now=1.0)
