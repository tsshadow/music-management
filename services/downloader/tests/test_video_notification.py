"""The push body for a video download, which has no Song to read the date off."""

import unittest

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.youtube.YoutubeSongProcessor import _video_message


class VideoMessageTestCase(unittest.TestCase):
    def test_the_upload_date_is_stated(self):
        message = _video_message({'upload_date': '20260903'}, 'Defqon.1 2026 Endshow')

        self.assertEqual(message, 'Defqon.1 2026 Endshow\nReleased=03-09-2026')

    def test_a_stated_release_date_beats_the_upload_date(self):
        message = _video_message({'release_date': '20260901', 'upload_date': '20260903'}, 'Some Premiere')

        self.assertEqual(message, 'Some Premiere\nReleased=01-09-2026')

    def test_without_a_date_the_message_is_the_bare_title(self):
        self.assertEqual(_video_message({}, 'Some Set'), 'Some Set')


if __name__ == '__main__':
    unittest.main()
