"""The settle rule: no import step acts on a release folder that is still being copied in.

A release copied into `__TODO` over SMB arrives one file at a time. The extractor has
always waited for an archive a browser was still writing; the flattener, renamer and
mover had nothing of the kind, and could rename a folder under the copy filling it or
move it to its label with half its tracks.
"""

import os
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()
from services.importer import flattener, mover, renamer, settle  # noqa: E402
from services.importer.flattener import Flattener  # noqa: E402
from services.importer.mover import Mover  # noqa: E402
from services.importer.renamer import Renamer  # noqa: E402
from services.importer.settle import STAGING_PREFIX, is_settled, newest_mtime, settle_seconds  # noqa: E402

AN_HOUR_AGO = time.time() - 3600


def write(path, content='x', mtime=AN_HOUR_AGO):
    """Create a file (and its folders), dated `mtime`."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(content)
    os.utime(path, (mtime, mtime))
    return path


def age(path, mtime=AN_HOUR_AGO):
    """Date every file and folder under `path`, and `path` itself, to `mtime`."""
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            os.utime(os.path.join(root, name), (mtime, mtime))
    os.utime(path, (mtime, mtime))


class IsSettledTest(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(TemporaryDirectory())
        self.release = os.path.join(self.root, 'Release')
        write(os.path.join(self.release, 'CD1', '01.mp3'))
        write(os.path.join(self.release, '00.nfo'))
        age(self.release)

    def test_a_folder_nothing_touched_for_longer_than_the_window_is_settled(self):
        self.assertTrue(is_settled(self.release, 300))

    def test_a_file_still_being_written_holds_the_whole_release_back(self):
        write(os.path.join(self.release, 'CD1', '02.mp3'), mtime=time.time())
        os.utime(os.path.join(self.release, 'CD1'), (AN_HOUR_AGO, AN_HOUR_AGO))
        self.assertFalse(is_settled(self.release, 300))

    def test_a_folder_that_just_gained_an_entry_counts_even_when_its_files_look_old(self):
        """Windows Explorer restores each copied file's own date as it closes it."""
        os.utime(os.path.join(self.release, 'CD1'), None)
        self.assertFalse(is_settled(self.release, 300))

    def test_synology_thumbnails_do_not_count(self):
        write(os.path.join(self.release, '@eaDir', 'thumb.jpg'), mtime=time.time())
        os.utime(self.release, (AN_HOUR_AGO, AN_HOUR_AGO))
        self.assertTrue(is_settled(self.release, 300))

    def test_a_folder_that_cannot_be_read_is_not_settled(self):
        self.assertFalse(is_settled(os.path.join(self.root, 'gone'), 300))

    def test_a_window_of_zero_switches_the_guard_off(self):
        self.assertTrue(is_settled(os.path.join(self.root, 'gone'), 0))

    def test_newest_mtime_is_the_newest_anywhere_inside(self):
        recent = AN_HOUR_AGO + 60
        write(os.path.join(self.release, 'CD1', '03.mp3'), mtime=recent)
        os.utime(os.path.join(self.release, 'CD1'), (AN_HOUR_AGO, AN_HOUR_AGO))
        self.assertAlmostEqual(newest_mtime(self.release), recent, places=0)

    def test_skipping_is_logged_at_debug_only(self):
        write(os.path.join(self.release, 'new.mp3'), mtime=time.time())
        with self.assertLogs(level='DEBUG') as logs:
            is_settled(self.release, 300)
        self.assertTrue(all(line.startswith('DEBUG') for line in logs.output))


class SettleSecondsTest(unittest.TestCase):
    def configured(self, value):
        with patch.object(settle, 'Settings', return_value=MagicMock(import_settle_minutes=value)):
            return settle_seconds()

    def test_minutes_become_seconds(self):
        self.assertEqual(self.configured(10), 600)

    def test_zero_is_allowed(self):
        self.assertEqual(self.configured(0), 0)

    def test_anything_else_falls_back_to_five_minutes(self):
        self.assertEqual(self.configured(-1), 300)
        self.assertEqual(self.configured('soon'), 300)
        self.assertEqual(self.configured(None), 300)


class StepsWaitForASettledFolderTest(unittest.TestCase):
    """The three steps that act on folders each leave an unsettled one alone, and act on it once settled."""

    def setUp(self):
        reset_database_helpers()
        self.root = self.enterContext(TemporaryDirectory())
        self.imports = os.path.join(self.root, 'import')
        self.eps = os.path.join(self.root, 'EPs')
        os.makedirs(os.path.join(self.eps, 'Scantraxx'))
        settings = MagicMock(import_folder_path=self.imports, eps_folder_path=self.eps, delimiter='/')
        for module in (flattener, renamer, mover):
            self.enterContext(patch.object(module, 'Settings', return_value=settings))
        self.enterContext(patch.object(settle, 'settle_seconds', return_value=300))

    def entries(self):
        return sorted(os.listdir(self.imports))

    def test_the_flattener_does_not_lift_releases_out_of_a_pack_still_arriving(self):
        write(os.path.join(self.imports, 'Pack', 'One (A1)', '01.mp3'), mtime=time.time())
        write(os.path.join(self.imports, 'Pack', 'Two (A2)', '01.mp3'), mtime=time.time())
        Flattener().run()
        self.assertEqual(self.entries(), ['Pack'])

        age(os.path.join(self.imports, 'Pack'))
        Flattener().run()
        self.assertEqual(self.entries(), ['One (A1)', 'Two (A2)'])

    def test_the_renamer_does_not_rename_a_folder_still_arriving(self):
        write(os.path.join(self.imports, 'Release (SCAN123)', '01.mp3'), mtime=time.time())
        Renamer().run()
        self.assertEqual(self.entries(), ['Release (SCAN123)'])

        age(os.path.join(self.imports, 'Release (SCAN123)'))
        Renamer().run()
        self.assertEqual(self.entries(), ['SCAN123 - Release (SCAN123)'])

    def test_the_mover_does_not_move_a_folder_still_arriving(self):
        folder = 'SCAN123 - Release'
        write(os.path.join(self.imports, folder, '01.mp3'), mtime=time.time())
        step = Mover()
        step.get_label = MagicMock(return_value='Scantraxx')
        with patch.object(mover, 'post_processing_songs', return_value=1), patch.object(mover, 'notification_service'):
            step.run()
            self.assertEqual(self.entries(), [folder])
            step.get_label.assert_not_called()

            age(os.path.join(self.imports, folder))
            step.run()
        self.assertEqual(self.entries(), [])
        self.assertTrue(os.path.isdir(os.path.join(self.eps, 'Scantraxx', folder)))

    def test_no_step_touches_an_extraction_in_progress(self):
        staging = os.path.join(self.imports, STAGING_PREFIX + 'abc')
        write(os.path.join(staging, 'Pack', 'One (A1)', '01.mp3'))
        age(staging)
        step = Mover()
        step.get_label = MagicMock(return_value='Scantraxx')
        step._propose = MagicMock()

        Flattener().run()
        Renamer().run()
        step.run()

        self.assertEqual(self.entries(), [STAGING_PREFIX + 'abc'])
        step.get_label.assert_not_called()
        step._propose.assert_not_called()


if __name__ == '__main__':
    unittest.main()
