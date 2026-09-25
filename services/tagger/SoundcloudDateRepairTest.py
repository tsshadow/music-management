"""The SoundCloud date repair picks exactly the files bug report 088 damaged."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.tagger import soundcloud_date_repair as repair


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(self.dir, ignore_errors=True))

    def file(self, name):
        path = os.path.join(self.dir, name)
        open(path, 'wb').close()
        return path

    def test_each_file_lands_under_the_verdict_its_date_earns(self):
        dates = {
            'cut.mp3': '2026',
            'repaired.mp3': '2026-08-31',
            'old-style.mp3': '20260831',
            'other-year.mp3': '2019',
            'no-date.mp3': '',
            'unreadable.mp3': None,
        }
        rows = [(self.file(name), '20260831') for name in dates]
        rows.append((os.path.join(self.dir, 'gone.mp3'), '20260831'))

        plan = repair.classify(rows, read=lambda path: dates[os.path.basename(path)])

        names = lambda paths: sorted(os.path.basename(p) for p in paths)  # noqa: E731
        self.assertEqual(names(plan.repair), ['cut.mp3'])
        self.assertEqual(names(plan.full), ['old-style.mp3', 'repaired.mp3'])
        self.assertEqual(names(plan.other), ['no-date.mp3', 'other-year.mp3'])
        self.assertEqual(names(plan.missing), ['gone.mp3', 'unreadable.mp3'])


class RunTest(unittest.TestCase):
    def connection(self, rows):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = rows
        return connection, cursor

    def test_a_dry_run_reads_and_writes_nothing(self):
        connection, cursor = self.connection([('/m/a.mp3', '20260831')])
        with patch.object(repair.os.path, 'exists', return_value=True):
            report = repair.run(connection, '2026-09-22 09:00:00', apply=False, read=lambda _p: '2026')

        cursor.execute.assert_called_once_with(repair.CANDIDATES_SQL, ('2026-09-22 09:00:00',))
        cursor.executemany.assert_not_called()
        connection.commit.assert_not_called()
        self.assertEqual(report['counts']['repair'], 1)
        self.assertEqual(report['queued'], 0)

    def test_apply_queues_only_the_damaged_files_with_the_dedicated_reason(self):
        connection, cursor = self.connection([('/m/a.mp3', '20260831'), ('/m/b.mp3', '20260831')])
        dates = {'/m/a.mp3': '2026', '/m/b.mp3': '2026-08-31'}
        with patch.object(repair.os.path, 'exists', return_value=True):
            report = repair.run(connection, 'x', apply=True, read=dates.get)

        cursor.executemany.assert_called_once_with(repair.QUEUE_SQL, [('/m/a.mp3', 'soundcloud_full_date')])
        connection.commit.assert_called_once()
        self.assertEqual(report['queued'], 1)

    def test_apply_with_nothing_to_repair_writes_nothing(self):
        connection, cursor = self.connection([])
        report = repair.run(connection, 'x', apply=True)

        cursor.executemany.assert_not_called()
        self.assertEqual(report['queued'], 0)


class QueueTest(unittest.TestCase):
    def test_paths_are_queued_in_batches(self):
        cursor = MagicMock()
        paths = [f'/m/{i}.mp3' for i in range(repair.BATCH_SIZE + 3)]

        self.assertEqual(repair.queue(cursor, paths), len(paths))
        self.assertEqual(cursor.executemany.call_count, 2)
        self.assertEqual(len(cursor.executemany.call_args_list[1].args[1]), 3)


class ReadDateTest(unittest.TestCase):
    def test_a_file_mutagen_cannot_parse_is_reported_as_unreadable(self):
        with patch('mutagen.File', side_effect=Exception('boom')):
            self.assertIsNone(repair.read_date('/m/a.mp3'))

    def test_a_file_without_tags_has_no_date(self):
        with patch('mutagen.File', return_value=None):
            self.assertEqual(repair.read_date('/m/a.mp3'), '')

    def test_the_first_date_value_is_returned(self):
        audio = MagicMock()
        audio.tags = {'date': ['2026']}
        with patch('mutagen.File', return_value=audio):
            self.assertEqual(repair.read_date('/m/a.mp3'), '2026')


if __name__ == '__main__':
    unittest.main()
