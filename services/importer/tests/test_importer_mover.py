import unittest
from unittest.mock import patch, MagicMock
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.importer.mover import post_processing_songs
from services.common.Helpers.NotificationService import notification_service

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
if __name__ == '__main__':
    unittest.main()