"""The extraction budget: what it measures and when it stops the backend (issue #231)."""

import os
import subprocess
import threading
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from services.importer import extract_budget
from services.importer.extract_budget import ExtractionWatch, child_pids, staged_bytes


def write(path, size):
    """A file of `size` bytes."""
    with open(path, 'wb') as handle:
        handle.write(b'\0' * size)


class StagedBytesTest(unittest.TestCase):
    def test_counts_files_in_every_folder(self):
        with TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, 'Release', 'CD1'))
            write(os.path.join(root, 'Release', 'CD1', '01.flac'), 300)
            write(os.path.join(root, 'Release', 'cover.jpg'), 20)
            self.assertEqual(staged_bytes(root), 320)

    def test_a_link_counts_as_itself_not_as_its_target(self):
        with TemporaryDirectory() as root, TemporaryDirectory() as elsewhere:
            write(os.path.join(elsewhere, 'big.bin'), 10_000)
            os.symlink(os.path.join(elsewhere, 'big.bin'), os.path.join(root, 'link'))
            self.assertLess(staged_bytes(root), 10_000)


class OverBudgetTest(unittest.TestCase):
    def test_the_folder_size_limit(self):
        with TemporaryDirectory() as root:
            write(os.path.join(root, 'a'), 200)
            self.assertEqual(ExtractionWatch(root, max_bytes=200, min_free_bytes=0).over_budget(), '')
            self.assertIn('passed 199 bytes', ExtractionWatch(root, max_bytes=199, min_free_bytes=0).over_budget())

    def test_the_free_space_floor(self):
        with TemporaryDirectory() as root, patch.object(extract_budget, 'free_bytes', return_value=5):
            self.assertIn('below 6 bytes', ExtractionWatch(root, max_bytes=0, min_free_bytes=6).over_budget())
            self.assertEqual(ExtractionWatch(root, max_bytes=0, min_free_bytes=5).over_budget(), '')

    def test_zero_switches_both_checks_off(self):
        with TemporaryDirectory() as root, patch.object(extract_budget, 'free_bytes', return_value=0):
            write(os.path.join(root, 'a'), 10**6)
            self.assertEqual(ExtractionWatch(root, max_bytes=0, min_free_bytes=0).over_budget(), '')


class WatchTest(unittest.TestCase):
    def test_stops_the_backend_once_the_folder_passes_the_budget(self):
        stopped = threading.Event()
        with TemporaryDirectory() as root:
            with ExtractionWatch(
                root, max_bytes=100, min_free_bytes=0, interval=0.01, stop=lambda _: stopped.set()
            ) as watch:
                write(os.path.join(root, 'a'), 101)
                self.assertTrue(stopped.wait(5))
            self.assertIn('passed 100 bytes', watch.exceeded)

    def test_a_block_within_the_budget_stops_nothing(self):
        with TemporaryDirectory() as root:
            stop = Mock()
            with ExtractionWatch(root, max_bytes=100, min_free_bytes=0, interval=0.01, stop=stop) as watch:
                write(os.path.join(root, 'a'), 100)
            self.assertEqual(watch.exceeded, '')
            stop.assert_not_called()


class ChildPidsTest(unittest.TestCase):
    def test_finds_a_grandchild(self):
        # `sh` starts `sleep` as its own child, the way patool starts a backend.
        shell = subprocess.Popen(['sh', '-c', 'sleep 30 & wait'])  # pylint: disable=consider-using-with
        try:
            for _ in range(100):
                found = child_pids(os.getpid())
                if len(found) >= 2:
                    break
                threading.Event().wait(0.02)
            self.assertIn(shell.pid, found)
            self.assertGreaterEqual(len(found), 2)
        finally:
            for pid in child_pids(shell.pid):
                os.kill(pid, 9)
            shell.kill()
            shell.wait()


if __name__ == '__main__':
    unittest.main()
