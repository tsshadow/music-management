import unittest
from unittest.mock import MagicMock, patch
import logging
import threading

# Mock the database before importing SoundcloudDownloader
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()

from services.downloader.soundcloud.soundcloud import SoundcloudDownloader, CONSECUTIVE_403_ERRORS, _403_lock, get_403_wait_time
import services.downloader.soundcloud.soundcloud as soundcloud_mod

class TestSoundcloud403Backoff(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        # Reset global counter before each test
        with _403_lock:
            soundcloud_mod.CONSECUTIVE_403_ERRORS = 0
        
        self.db_patcher = patch('services.downloader.soundcloud.soundcloud.get_accounts_from_db')
        self.mock_get_accounts = self.db_patcher.start()
        self.mock_get_accounts.return_value = ['test_account']
        
        self.makedirs_patcher = patch('os.makedirs')
        self.makedirs_patcher.start()

    def tearDown(self):
        patch.stopall()

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    @patch('time.sleep')
    def test_consecutive_403_backoff(self, mock_sleep, mock_ytdlp):
        mock_instance = mock_ytdlp.return_value.__enter__.return_value
        
        # Simulate 403 error via logger (as planned)
        def mock_download_with_403(urls):
            # The actual implementation uses the logger passed in opts
            # YoutubeDL(opts) -> opts is mock_ytdlp.call_args[0][0]
            opts = mock_ytdlp.call_args[0][0]
            if 'logger' in opts:
                opts['logger'].error("HTTP Error 403: Forbidden")
            return 1 # Non-zero for error
        
        mock_instance.download.side_effect = mock_download_with_403
        
        downloader = SoundcloudDownloader(break_on_existing=False)
        
        # Call download_url
        url = "http://soundcloud.com/test_account/tracks"
        
        # 1st attempt
        downloader.download_url(url)
        
        # It should have tried 3 times (internal retry loop in download_url)
        # wait_time for 1st consecutive: 240
        # wait_time for 2nd consecutive: 1800
        # wait_time for 3rd consecutive: 10800
        
        self.assertEqual(mock_sleep.call_count, 3)
        mock_sleep.assert_any_call(240)
        mock_sleep.assert_any_call(1800)
        mock_sleep.assert_any_call(10800)
        
        with _403_lock:
            self.assertEqual(soundcloud_mod.CONSECUTIVE_403_ERRORS, 3)

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    @patch('time.sleep')
    def test_403_reset_on_success(self, mock_sleep, mock_ytdlp):
        mock_instance = mock_ytdlp.return_value.__enter__.return_value
        
        # First fail with 403
        def mock_download_fail(urls):
            opts = mock_ytdlp.call_args[0][0]
            opts['logger'].error("HTTP Error 403: Forbidden")
            return 1
            
        mock_instance.download.side_effect = mock_download_fail
        downloader = SoundcloudDownloader()
        
        # Manually set counter to simulate previous failures
        with _403_lock:
            soundcloud_mod.CONSECUTIVE_403_ERRORS = 5
            
        # Now simulate a success
        mock_instance.download.side_effect = lambda urls: 0
        
        downloader.download_url("http://soundcloud.com/success")
        
        with _403_lock:
            self.assertEqual(soundcloud_mod.CONSECUTIVE_403_ERRORS, 0)

    def test_wait_times(self):
        self.assertEqual(get_403_wait_time(1), 240)
        self.assertEqual(get_403_wait_time(2), 1800)
        self.assertEqual(get_403_wait_time(3), 10800)
        self.assertEqual(get_403_wait_time(4), 21600)
        self.assertEqual(get_403_wait_time(5), 43200)
        self.assertEqual(get_403_wait_time(6), 86400)
        self.assertEqual(get_403_wait_time(10), 86400)

if __name__ == '__main__':
    unittest.main()
