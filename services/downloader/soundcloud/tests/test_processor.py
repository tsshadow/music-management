import sys
import types
import unittest
from services.tests.mock_base import setup_mocks, reset_database_helpers

# Ensure mocks are setup before importing anything from services
setup_mocks()

from services.downloader.soundcloud.SoundcloudSongProcessor import SoundcloudSongProcessor

class SoundcloudProcessorTest(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()

    def test_extract_account_name_from_url(self):
        url = 'https://soundcloud.com/testuser/track-name'
        self.assertEqual(SoundcloudSongProcessor._extract_account_name_from_url(url), 'testuser')

    def test_extract_account_name_from_url_invalid(self):
        self.assertEqual(SoundcloudSongProcessor._extract_account_name_from_url('not a url'), 'not a url')
if __name__ == '__main__':
    unittest.main()