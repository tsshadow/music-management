import unittest
from unittest.mock import patch
from services.tests.mock_base import setup_mocks, reset_database_helpers

setup_mocks()

# --- IMPORT TARGETS ---
# pylint: disable=wrong-import-position
from services.downloader.youtube.youtube import YoutubeDownloader
from services.tagger.Song.YoutubeSong import YoutubeSong
from services.tagger.constants import TITLE, ARTIST
from services.common.Helpers.NotificationService import notification_service

class YoutubeDownloaderTest(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        self.processor = None
        # Use a list to store patchers for easy cleanup
        self.patchers = []

        archive_patcher = patch('services.downloader.youtube.YoutubeSongProcessor.YoutubeArchive')
        self.mock_archive = archive_patcher.start()
        self.patchers.append(archive_patcher)
        self.mock_archive.exists.return_value = False

        db_patcher = patch('services.downloader.youtube.youtube.YoutubeDownloader.get_accounts_from_db')
        self.mock_get_accounts = db_patcher.start()
        self.patchers.append(db_patcher)
        self.mock_get_accounts.return_value = ['Noisia']

        # Mock Path.exists and os.path.exists
        path_exists_patcher = patch('pathlib.Path.exists')
        self.mock_path_exists = path_exists_patcher.start()
        self.patchers.append(path_exists_patcher)
        self.mock_path_exists.return_value = True

        path_is_file_patcher = patch('pathlib.Path.is_file')
        path_is_file_patcher.start().return_value = True
        self.patchers.append(path_is_file_patcher)

        os_path_exists_patcher = patch('os.path.exists')
        os_path_exists_patcher.start().return_value = True
        self.patchers.append(os_path_exists_patcher)

        makedirs_patcher = patch('os.makedirs')
        makedirs_patcher.start()
        self.patchers.append(makedirs_patcher)

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        patch.stopall()

    @patch('services.downloader.youtube.youtube.YoutubeDL')
    def test_youtube_downloader_run(self, mock_ytdlp):
        """
        Test the YouTube downloader pipeline:
        Mock(yt-dlp returns) -> do run -> assert(tags)
        """
        # 1. MOCK (Setup input data)
        dl_info = {
            'id': 'collider_id',
            'title': 'Noisia - Collider',
            'uploader': 'Noisia',
            'uploader_id': 'noisia_id',
            'webpage_url': 'https://www.youtube.com/watch?v=collider_id',
            'ext': 'mp3',
            'filepath': '/tmp/youtube/Noisia/Noisia - Collider.mp3'
        }

        mock_instance = mock_ytdlp.return_value.__enter__.return_value

        self.processor = None
        def mock_add_pp(pp):
            if "YoutubeSongProcessor" in str(type(pp)):
                self.processor = pp

        mock_ytdlp.return_value.add_post_processor.side_effect = mock_add_pp

        def mock_download(_links):
            if self.processor:
                self.processor.run(dl_info)
            return 0

        mock_instance.download.side_effect = mock_download

        # 2. DO RUN
        downloader = YoutubeDownloader(break_on_existing=False)
        with patch('time.sleep'):
            downloader.run(account='Noisia')

        # 3. ASSERT
        song = YoutubeSong(dl_info['filepath'], dl_info)
        # Load the mock tags into the tag collection so parse() correctly processes them
        # Note: YoutubeSong.update_song requires artist == folder name to split the title
        song.tag_collection.set_item(ARTIST, 'Noisia')
        song.tag_collection.set_item(TITLE, 'Noisia - Collider')
        song.parse()

        # YoutubeSong splits "Artist - Title" if they match the folder name
        self.assertEqual(song.artist(), 'Noisia')
        self.assertEqual(song.title(), 'Collider')
        self.assertEqual(song.album(), 'Youtube (Noisia)')
        self.assertEqual(song.publisher(), 'Youtube')

        # Verify notification was sent
        notification_service.notify.assert_called()
        call_args = notification_service.notify.call_args[0]
        self.assertIn("Title=Collider", call_args[0])
        self.assertIn("Artists=Noisia", call_args[0])
        self.assertEqual(notification_service.notify.call_args[1]['title'], "YouTube Download Complete")

if __name__ == '__main__':
    unittest.main()
