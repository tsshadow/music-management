import os
import shutil
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

from services.tests.mock_base import reset_database_helpers

pytestmark = pytest.mark.mock_base('Cache')

from services.importer.mover import Mover, make_library_writable, post_processing_songs


class TestMover(unittest.TestCase):
    def setUp(self):
        reset_database_helpers()
        self.path_exists_patcher = patch('os.path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

    def tearDown(self):
        patch.stopall()

    @patch('services.common.Helpers.NotificationService.notification_service.notify')
    @patch('os.walk')
    @patch('os.path.isfile')
    def test_post_processing_notifications(self, mock_isfile, mock_walk, mock_notify):
        """Every tagged file is an event, and none of them is a push: the release gets that."""
        mock_walk.return_value = [('/tmp/eps/Scantraxx/SCAN123', [], ['song1.mp3', 'song2.mp3'])]
        mock_isfile.return_value = True
        with patch('services.importer.mover.LabelSong') as MockLabelSong:
            mock_song = MockLabelSong.return_value
            mock_song.__str__.return_value = 'Title=Test Song\nArtists=Test Artist'
            tagged = post_processing_songs('/tmp/eps/Scantraxx/SCAN123')
        self.assertEqual(tagged, 2)
        self.assertEqual(mock_notify.call_count, 2)
        for call in mock_notify.call_args_list:
            self.assertEqual(call.kwargs['title'], 'Track Imported')
            self.assertIs(call.kwargs['push'], False)

    @patch('services.common.Helpers.NotificationService.notification_service.notify')
    @patch('services.importer.mover.announce')
    @patch('os.walk')
    @patch('os.path.isfile')
    def test_a_tagged_import_is_announced_per_file(self, mock_isfile, mock_walk, mock_announce, _notify):
        # After the tag pass, so the bookkeeping carries the mtime the pass produced and the
        # walk in music-manager does not tag the release a second time.
        mock_walk.return_value = [('/tmp/eps/Scantraxx/SCAN123', [], ['01.mp3', '02.mp3'])]
        mock_isfile.return_value = True
        with patch('services.importer.mover.LabelSong'):
            post_processing_songs('/tmp/eps/Scantraxx/SCAN123')
        self.assertEqual(
            [c.args[0] for c in mock_announce.call_args_list],
            ['/tmp/eps/Scantraxx/SCAN123/01.mp3', '/tmp/eps/Scantraxx/SCAN123/02.mp3'],
        )


class TestMoverConflictHandling(unittest.TestCase):
    """Regression test: shutil.move(src, dst) raises shutil.Error (not FileExistsError) when
    "dst" already exists as a directory AND already contains an identically-named entry for
    "src" (i.e. this exact release was already imported before). This used to be swallowed by
    the generic "except OSError" branch, logged as a bogus "check disk space/filesystem" error,
    and left the duplicate source folder in __TODO forever, retried (and re-logged as an error)
    on every single import cycle. Both FileExistsError and shutil.Error must be treated as the
    same "already imported" conflict and clean up the duplicate source folder.
    """

    def setUp(self):
        reset_database_helpers()

    def tearDown(self):
        patch.stopall()

    def _make_mover(self, label='Scantraxx'):
        mover = Mover()
        mover.get_label = MagicMock(return_value=label)
        mover.remove = MagicMock()
        return mover

    @patch('services.importer.mover.shutil.move')
    def test_shutil_error_is_treated_as_conflict_and_source_is_removed(self, mock_move):
        mock_move.side_effect = shutil.Error(
            "Destination path '/mnt/music/EPs/Scantraxx/SCAN123/SCAN123' already exists"
        )
        mover = self._make_mover()
        mover._move_folder('SCAN123', 'SCAN', dry_run=False)
        mover.remove.assert_called_once_with('SCAN123')

    @patch('services.importer.mover.shutil.move')
    def test_file_exists_error_is_treated_as_conflict_and_source_is_removed(self, mock_move):
        mock_move.side_effect = FileExistsError('already exists')
        mover = self._make_mover()
        mover._move_folder('SCAN123', 'SCAN', dry_run=False)
        mover.remove.assert_called_once_with('SCAN123')

    @patch('services.importer.mover.shutil.move')
    def test_generic_os_error_does_not_remove_source(self, mock_move):
        """A genuine disk/filesystem error must NOT be treated as a duplicate and must not
        remove the source folder - only the "already exists" conflict shapes should."""
        mock_move.side_effect = OSError('No space left on device')
        mover = self._make_mover()
        mover._move_folder('SCAN123', 'SCAN', dry_run=False)
        mover.remove.assert_not_called()


if __name__ == '__main__':
    unittest.main()


class TestMoverScanNotification(unittest.TestCase):
    """A move must tell LMS about both ends of it, and only when it actually happened."""

    def setUp(self):
        reset_database_helpers()
        self.mover = Mover()
        self.mover.settings = MagicMock(import_folder_path='/mnt/music/EPs/__TODO', eps_folder_path='/mnt/music/EPs')
        self.mover.get_label = MagicMock(return_value='Evolve AU')

    def tearDown(self):
        patch.stopall()

    def test_a_move_notifies_lms_of_both_the_old_and_the_new_folder(self):
        # The old path is not optional: it is how the rows under the folder that was moved
        # away get removed. Without it a moved release stays in the index twice.
        with (
            patch('services.importer.mover.lms_scan_trigger') as trigger,
            patch('services.importer.mover.shutil.move'),
            patch('services.importer.mover.post_processing_songs'),
            patch('os.path.exists', return_value=False),
        ):
            self.mover._move_folder('EVAU021E', 'EVAU', dry_run=False)

        notified = trigger.notify.call_args.args[0]
        self.assertIn('/mnt/music/EPs/__TODO/EVAU021E', notified)
        self.assertIn('/mnt/music/EPs/Evolve AU/EVAU021E', notified)

    def test_a_dry_run_notifies_nothing(self):
        with (
            patch('services.importer.mover.lms_scan_trigger') as trigger,
            patch('services.importer.mover.post_processing_songs'),
            patch('os.path.exists', return_value=False),
        ):
            self.mover._move_folder('EVAU021E', 'EVAU', dry_run=True)

        trigger.notify.assert_not_called()

    def test_a_failed_move_notifies_nothing(self):
        with (
            patch('services.importer.mover.lms_scan_trigger') as trigger,
            patch('services.importer.mover.shutil.move', side_effect=PermissionError),
            patch('os.path.exists', return_value=False),
        ):
            self.mover._move_folder('EVAU021E', 'EVAU', dry_run=False)

        trigger.notify.assert_not_called()


class TestImportedReleaseIsWritable(unittest.TestCase):
    """What the importer drops into the library has to be writable by everyone else.

    It runs as root with the default umask, so an unpacked release lands 0755/0644 and
    root -- which may write anything -- never notices. Over SMB every later write fails.
    Measured 2026-09-08: 19 of the EPs directories created since the last manual repair
    sat at 0755, and the release-date backfill skipped 9 of their files.
    """

    def setUp(self):
        reset_database_helpers()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.release = os.path.join(self.tmp.name, 'SCAN123 - Release')
        os.makedirs(os.path.join(self.release, 'CD1'), mode=0o755)
        self.track = os.path.join(self.release, 'CD1', '01-song.mp3')
        with open(self.track, 'w', encoding='utf-8') as handle:
            handle.write('audio')
        os.chmod(self.track, 0o644)
        os.chmod(self.release, 0o755)

    def test_every_file_and_folder_gains_the_librarys_permissions(self):
        failures = make_library_writable(self.release)
        self.assertEqual(failures, 0)
        self.assertEqual(stat.S_IMODE(os.stat(self.release).st_mode), 0o777)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.release, 'CD1')).st_mode), 0o777)
        self.assertEqual(stat.S_IMODE(os.stat(self.track).st_mode), 0o666)

    def test_a_mode_that_will_not_stick_is_counted_and_logged_not_raised(self):
        # Some shares refuse a chmod outright. The release is already in place by then;
        # failing the import afterwards would be the worse outcome.
        with patch('os.chmod', side_effect=OSError('read-only')):
            failures = make_library_writable(self.release)
        self.assertEqual(failures, 3)

    def test_a_move_makes_the_destination_writable_before_it_is_tagged(self):
        mover = Mover()
        mover.settings = MagicMock(import_folder_path='/tmp/import', eps_folder_path='/tmp/eps')
        mover.get_label = MagicMock(return_value='Scantraxx')
        order = []
        with (
            patch('os.path.exists', return_value=False),
            patch('shutil.move'),
            patch('services.importer.mover.make_library_writable', side_effect=lambda path: order.append('chmod')),
            patch('services.importer.mover.post_processing_songs', side_effect=lambda path, **_: order.append('tag')),
            patch('services.common.Helpers.LmsScanTrigger.lms_scan_trigger.notify'),
        ):
            mover._move_folder('SCAN123 - Release', 'SCAN123', dry_run=False)
        self.assertEqual(order, ['chmod', 'tag'])

    def test_a_dry_run_changes_no_permissions(self):
        mover = Mover()
        mover.settings = MagicMock(import_folder_path='/tmp/import', eps_folder_path='/tmp/eps')
        mover.get_label = MagicMock(return_value='Scantraxx')
        with (
            patch('os.path.exists', return_value=False),
            patch('shutil.move'),
            patch('services.importer.mover.make_library_writable') as writable,
            patch('services.importer.mover.post_processing_songs'),
        ):
            mover._move_folder('SCAN123 - Release', 'SCAN123', dry_run=True)
        writable.assert_not_called()
