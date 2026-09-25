"""Standing folder conflicts are warned about once, counted every cycle, and forgotten when resolved.

Bug report 091: 49 pairs the renamer could not resolve produced ~490 WARNING events an
hour on production, the same pairs every five minutes.
"""

import logging
import os
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from services.common.Helpers import Quarantine as quarantine_module
from services.importer import conflict_store, renamer, settle
from services.importer.conflict_store import MOVER, RENAMER, ConflictStore, ConflictTracker, pair_key
from services.importer.renamer import Renamer

AN_HOUR_AGO = time.time() - 3600

UNPARSED = 'Some Release (SCAN123)'
RENAMED = 'SCAN123 - Some Release (SCAN123)'


class FakeConflictStore:
    """`importer_conflicts` as far as the tracker sees it; outlives a Renamer like the database does."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.unreachable = False

    def snapshot(self, step):
        if self.unreachable:
            return None
        return {key: row['fingerprint'] for key, row in self.rows.items() if row['step'] == step}

    def record(self, key, step, source, target, fingerprint):
        self.rows[key] = {'step': step, 'source': source, 'target': target, 'fingerprint': fingerprint}

    def touch(self, key):
        pass

    def forget(self, key):
        self.rows.pop(key, None)


def messages(logs, level):
    """The messages of one level in an assertLogs capture."""
    return [record.getMessage() for record in logs.records if record.levelno == level]


class RenamerConflictMemoryTest(unittest.TestCase):
    """The renamer over a real import folder, with the conflict table replaced by a fake."""

    def setUp(self):
        self.enterContext(patch.object(settle, 'settle_seconds', return_value=0))
        self.tmp = self.enterContext(TemporaryDirectory())
        self.quarantine = self.enterContext(TemporaryDirectory())
        settings = MagicMock(
            import_folder_path=self.tmp,
            delimiter='/',
            quarantine_folder_path=self.quarantine,
            quarantine_retention_days=30,
        )
        for module in (renamer, quarantine_module):
            self.enterContext(patch.object(module, 'Settings', return_value=settings))
        self.store = FakeConflictStore()
        self.compare = self.enterContext(patch.object(renamer, 'is_same_release', wraps=renamer.is_same_release))

    def new_renamer(self):
        """A renamer as a fresh importer process would build it, sharing the one database."""
        instance = Renamer()
        instance.conflicts = ConflictTracker(RENAMER, self.store)
        return instance

    def make_release(self, folder, content):
        path = os.path.join(self.tmp, folder)
        os.makedirs(path, exist_ok=True)
        track = os.path.join(path, '01-track.mp3')
        with open(track, 'w', encoding='utf-8') as handle:
            handle.write(content)
        os.utime(track, (AN_HOUR_AGO, AN_HOUR_AGO))
        os.utime(path, (AN_HOUR_AGO, AN_HOUR_AGO))
        return path

    def conflicting_pair(self):
        self.make_release(UNPARSED, 'a longer rip')
        return self.make_release(RENAMED, 'aaa')

    def run_cycle(self, instance):
        with self.assertLogs(level='DEBUG') as logs:
            instance.run()
        return logs

    def test_a_standing_conflict_is_warned_about_only_the_first_time(self):
        self.conflicting_pair()
        instance = self.new_renamer()

        first = self.run_cycle(instance)
        second = self.run_cycle(instance)
        third = self.run_cycle(instance)

        self.assertEqual(len([m for m in messages(first, logging.WARNING) if 'differ' in m]), 1)
        self.assertEqual(messages(second, logging.WARNING), [])
        self.assertEqual(messages(third, logging.WARNING), [])
        self.assertTrue(any('still stands' in m for m in messages(second, logging.DEBUG)))

    def test_an_unchanged_pair_is_not_compared_again(self):
        self.conflicting_pair()
        instance = self.new_renamer()

        for _ in range(3):
            self.run_cycle(instance)

        self.assertEqual(self.compare.call_count, 1)

    def test_a_restart_does_not_warn_about_what_already_stands(self):
        self.conflicting_pair()
        self.run_cycle(self.new_renamer())

        after_restart = self.run_cycle(self.new_renamer())

        self.assertEqual(messages(after_restart, logging.WARNING), [])

    def test_every_cycle_ends_with_one_line_counting_the_standing_conflicts(self):
        self.conflicting_pair()
        instance = self.new_renamer()

        first = self.run_cycle(instance)
        second = self.run_cycle(instance)

        first_summary = [m for m in messages(first, logging.INFO) if m.startswith('Standing folder conflicts')]
        second_summary = [m for m in messages(second, logging.INFO) if m.startswith('Standing folder conflicts')]
        self.assertEqual(
            first_summary, ['Standing folder conflicts (renamer): 1, 1 new this cycle, 0 resolved since the last one']
        )
        self.assertEqual(
            second_summary, ['Standing folder conflicts (renamer): 1, 0 new this cycle, 0 resolved since the last one']
        )

    def test_a_resolved_pair_is_forgotten_and_stops_being_reported(self):
        self.conflicting_pair()
        instance = self.new_renamer()
        self.run_cycle(instance)
        self.assertEqual(len(self.store.rows), 1)

        # Someone looked at the two folders and removed the target: the rename now succeeds.
        target = os.path.join(self.tmp, RENAMED)
        os.remove(os.path.join(target, '01-track.mp3'))
        os.rmdir(target)
        resolved = self.run_cycle(instance)
        after = self.run_cycle(instance)

        self.assertEqual(self.store.rows, {})
        self.assertTrue(
            any('1 resolved since the last one' in m for m in messages(resolved, logging.INFO)),
        )
        self.assertFalse(any(m.startswith('Standing folder conflicts') for m in messages(after, logging.INFO)))
        self.assertEqual(messages(after, logging.WARNING), [])

    def test_a_changed_folder_is_compared_again_without_a_second_warning(self):
        target = self.conflicting_pair()
        instance = self.new_renamer()
        self.run_cycle(instance)

        with open(os.path.join(target, '02-bonus.mp3'), 'w', encoding='utf-8') as handle:
            handle.write('bonus')
        changed = self.run_cycle(instance)

        self.assertEqual(self.compare.call_count, 2)
        self.assertEqual(messages(changed, logging.WARNING), [])
        self.assertTrue(any('still differs' in m for m in messages(changed, logging.INFO)))

    def test_a_pair_that_becomes_equal_is_parked_and_forgotten(self):
        target = self.conflicting_pair()
        instance = self.new_renamer()
        self.run_cycle(instance)

        with open(os.path.join(target, '01-track.mp3'), 'w', encoding='utf-8') as handle:
            handle.write('a longer rip')
        self.run_cycle(instance)

        self.assertFalse(os.path.isdir(os.path.join(self.tmp, UNPARSED)))
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(self.store.rows, {})

    def test_without_the_database_the_process_still_warns_only_once(self):
        self.store.unreachable = True
        self.conflicting_pair()
        instance = self.new_renamer()

        first = self.run_cycle(instance)
        second = self.run_cycle(instance)

        self.assertEqual(len([m for m in messages(first, logging.WARNING) if 'differ' in m]), 1)
        self.assertEqual(messages(second, logging.WARNING), [])

    def test_nothing_is_logged_as_a_summary_when_nothing_stands(self):
        with self.assertLogs(level='INFO') as logs:
            self.new_renamer().run()

        self.assertFalse(any(m.startswith('Standing folder conflicts') for m in messages(logs, logging.INFO)))


class TrackerTest(unittest.TestCase):
    """The tracker's bookkeeping, without a renamer around it."""

    def setUp(self):
        self.store = FakeConflictStore()
        self.enterContext(patch.object(conflict_store, 'pair_fingerprint', return_value='fp'))

    def test_each_step_prunes_only_its_own_pairs(self):
        renamer_tracker = ConflictTracker(RENAMER, self.store)
        mover_tracker = ConflictTracker(MOVER, self.store)
        mover_tracker.begin()
        mover_tracker.unchanged('/a', '/b')
        mover_tracker.differs('/a', '/b')
        mover_tracker.end()

        renamer_tracker.begin()
        renamer_tracker.end()

        self.assertIn(pair_key(MOVER, '/a', '/b'), self.store.rows)

    def test_a_dry_run_neither_records_nor_forgets(self):
        tracker = ConflictTracker(RENAMER, self.store)
        tracker.begin()
        tracker.unchanged('/a', '/b')
        tracker.differs('/a', '/b', dry_run=True)
        tracker.end(dry_run=True)

        self.assertEqual(self.store.rows, {})

    def test_the_end_of_a_cycle_returns_how_many_stand(self):
        tracker = ConflictTracker(RENAMER, self.store)
        tracker.begin()
        tracker.unchanged('/a', '/b')
        tracker.differs('/a', '/b')
        tracker.unchanged('/c', '/d')
        tracker.differs('/c', '/d')

        self.assertEqual(tracker.end(), 2)


class ConflictStoreTest(unittest.TestCase):
    """The store never fails an import cycle over the database."""

    def test_an_unreachable_database_reads_as_no_snapshot(self):
        store = ConflictStore()
        store.db_connector = MagicMock()
        store.db_connector.connection.side_effect = RuntimeError('down')

        self.assertIsNone(store.snapshot(RENAMER))

    def test_a_failed_write_is_swallowed(self):
        store = ConflictStore()
        store.db_connector = MagicMock()
        store.db_connector.connection.side_effect = RuntimeError('down')

        store.record('k', RENAMER, '/a', '/b', 'fp')
        store.forget('k')
        store.touch('k')

    def test_the_snapshot_maps_each_pair_to_its_fingerprint(self):
        store = ConflictStore()
        cursor = MagicMock()
        cursor.fetchall.return_value = [('k1', 'fp1'), ('k2', None)]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        store.db_connector = MagicMock()
        store.db_connector.connection.return_value = connection

        self.assertEqual(store.snapshot(RENAMER), {'k1': 'fp1', 'k2': None})
        cursor.execute.assert_called_once_with(conflict_store.SNAPSHOT_QUERY, (RENAMER,))


if __name__ == '__main__':
    unittest.main()
