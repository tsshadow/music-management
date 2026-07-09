import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from services.tests.mock_base import setup_mocks, reset_database_helpers

setup_mocks()

# --- IMPORT TARGETS ---
from services.tagger.Song.LabelSong import LabelSong
from services.tagger.constants import TITLE, ARTIST
from services.common.Helpers.NotificationService import notification_service

class ImporterTest(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        from services.common.Helpers.Cache import databaseHelpers
        databaseHelpers['artistGenreHelper'].get.return_value = ['Hardstyle']
        # Mock Path.exists and os.path.exists
        self.path_exists_patcher = patch('os.path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

    def tearDown(self):
        patch.stopall()

    def test_importer_labelsong_tagging(self):
        """
        Test the Importer's tagging logic (via LabelSong):
        Mock(Imported file path) -> do run (parse) -> assert(tags)
        """
        # 1. MOCK (Setup input data - path structure is critical for LabelSong)
        file_path = '/tmp/eps/Scantraxx/SCAN123 - D-Block & S-te-Fan/01 - Takin\' Off.mp3'
        
        # 2. DO RUN
        song = LabelSong(file_path)
        # Load mock tags into the tag collection so parse() correctly processes them
        song.tag_collection.set_item(TITLE, "Takin' Off")
        song.tag_collection.set_item(ARTIST, 'D-Block & S-te-Fan')
        
        song.parse()

        # 3. ASSERT
        self.assertEqual(song.title(), "Takin' Off")
        # Note: The system splits '&' and 'feat' into multiple artists, joined by ';'
        self.assertIn('D-Block', song.artist())
        self.assertIn('S-te-Fan', song.artist())
        
        self.assertEqual(song.publisher(), 'Scantraxx')
        self.assertEqual(song.catalog_number(), 'SCAN123')
        # Genre should be Hardstyle based on our artistGenreHelper mock
        self.assertEqual(song.genre(), 'Hardstyle')

    @patch('os.walk')
    @patch('os.path.isfile')
    def test_post_processing_notifications(self, mock_isfile, mock_walk):
        """Verify that post_processing_songs sends a notification."""
        from services.importer.mover import post_processing_songs
        
        mock_walk.return_value = [
            ('/tmp/eps/Scantraxx/SCAN123', [], ['song1.mp3'])
        ]
        mock_isfile.return_value = True
        
        with patch('services.importer.mover.LabelSong') as MockLabelSong:
            mock_song = MockLabelSong.return_value
            mock_song.__str__.return_value = "Title=Test Song\nArtists=Test Artist"
            
            post_processing_songs('/tmp/eps/Scantraxx/SCAN123')
            
            notification_service.notify.assert_called()
            self.assertEqual(notification_service.notify.call_args[1]['title'], "Import Complete")

if __name__ == '__main__':
    unittest.main()
