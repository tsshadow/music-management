import unittest
from services.tests.mock_base import setup_mocks, reset_database_helpers
setup_mocks()
from services.downloader.soundcloud.SoundcloudArchive import SoundcloudArchive

class SoundcloudArchiveTest(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()

    def test_get_uploader_id(self):
        info = {'channel_id': '123', 'uploader_id': 'abc'}
        self.assertEqual(SoundcloudArchive._get_uploader_id(info), '123')
        self.assertEqual(SoundcloudArchive._get_uploader_id({'uploader_id': 'abc'}), 'abc')
        self.assertIsNone(SoundcloudArchive._get_uploader_id({}))
if __name__ == '__main__':
    unittest.main()