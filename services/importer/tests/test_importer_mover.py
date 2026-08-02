import shutil
import unittest
from unittest.mock import MagicMock, patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()
from services.common.Helpers.NotificationService import notification_service
from services.importer.mover import Mover, post_processing_songs


class TestMover(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        self.path_exists_patcher = patch('os.path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

    def tearDown(self):
        patch.stopall()

    @patch('os.walk')
    @patch('os.path.isfile')
    def test_post_processing_notifications(self, mock_isfile, mock_walk):
        """Verify that post_processing_songs sends a notification."""
        mock_walk.return_value = [('/tmp/eps/Scantraxx/SCAN123', [], ['song1.mp3'])]
        mock_isfile.return_value = True
        with patch('services.importer.mover.LabelSong') as MockLabelSong:
            mock_song = MockLabelSong.return_value
            mock_song.__str__.return_value = 'Title=Test Song\nArtists=Test Artist'
            post_processing_songs('/tmp/eps/Scantraxx/SCAN123')
            notification_service.notify.assert_called()
            self.assertEqual(notification_service.notify.call_args[1]['title'], 'Import Complete')


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
        mock_move.side_effect = shutil.Error("Destination path '/mnt/music/EPs/Scantraxx/SCAN123/SCAN123' already exists")
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