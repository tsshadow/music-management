import unittest
from unittest.mock import patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()
from services.downloader.timing import load_timing
from services.downloader.youtube.DropCategoryGenre import DropCategoryGenrePP
from services.downloader.youtube.youtube import YoutubeDownloader
from services.tagger.constants import ARTIST, TITLE
from services.tagger.Song.YoutubeSong import YoutubeSong


class YoutubeDownloaderTest(unittest.TestCase):

    def setUp(self):
        self.patchers = []
        config_patcher = patch('services.downloader.youtube.youtube.ConfigStore')
        self.mock_config = config_patcher.start()
        self.patchers.append(config_patcher)
        self.mock_config.return_value.get_many.return_value = {'youtube_folder': '/tmp/youtube', 'youtube_archive': '/tmp/archive'}
        reset_database_helpers()
        self.processor = None
        archive_patcher = patch('services.downloader.youtube.YoutubeSongProcessor.YoutubeArchive')
        self.mock_archive = archive_patcher.start()
        self.patchers.append(archive_patcher)
        self.mock_archive.exists.return_value = False
        db_patcher = patch('services.downloader.youtube.youtube.YoutubeDownloader.get_accounts_from_db')
        self.mock_get_accounts = db_patcher.start()
        self.patchers.append(db_patcher)
        self.mock_get_accounts.return_value = ['Noisia']
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

    @patch('services.common.Helpers.NotificationService.notification_service.notify')
    @patch('services.downloader.youtube.youtube.YoutubeDL')
    def test_youtube_downloader_run(self, mock_ytdlp, mock_notify):
        """
        Test the YouTube downloader pipeline:
        Mock(yt-dlp returns) -> do run -> assert(tags)
        """
        dl_info = {'id': 'collider_id', 'title': 'Noisia - Collider', 'uploader': 'Noisia', 'uploader_id': 'noisia_id', 'webpage_url': 'https://www.youtube.com/watch?v=collider_id', 'ext': 'mp3', 'filepath': '/tmp/youtube/Noisia/Noisia - Collider.mp3'}
        mock_instance = mock_ytdlp.return_value.__enter__.return_value
        self.processor = None

        def mock_add_pp(pp, **_kwargs):
            if 'YoutubeSongProcessor' in str(type(pp)):
                self.processor = pp
        mock_ytdlp.return_value.add_post_processor.side_effect = mock_add_pp

        def mock_download(_links):
            if self.processor:
                self.processor.run(dl_info)
            return 0
        mock_instance.download.side_effect = mock_download
        # This test drives the ordinary run. Without turning the cadence off the
        # channel would be deep-due -- it has never been deep-swept -- and take
        # the full-listing path instead.
        downloader = YoutubeDownloader(
            break_on_existing=False,
            timing=load_timing('youtube', overrides={'deep_sweep_days': 0}))
        downloader.downloader_config['enabled'] = True
        with patch('time.sleep'):
            downloader.run(account='Noisia')
        song = YoutubeSong(dl_info['filepath'], dl_info)
        song.tag_collection.set_item(ARTIST, 'Noisia')
        song.tag_collection.set_item(TITLE, 'Noisia - Collider')
        song.parse()
        self.assertEqual(song.artist(), 'Noisia')
        self.assertEqual(song.title(), 'Collider')
        self.assertEqual(song.album(), 'Youtube (Noisia)')
        self.assertEqual(song.publisher(), 'Youtube')
        mock_notify.assert_called()
        call_args = mock_notify.call_args[0]
        self.assertIn('Title=Collider', call_args[0])
        self.assertIn('Artists=Noisia', call_args[0])
        self.assertEqual(mock_notify.call_args[1]['title'], 'YouTube Download Complete')

    def test_youtube_category_is_not_offered_as_a_genre(self):
        """yt-dlp resolves the genre tag as genre -> genres -> categories -> tags.

        The YouTube extractor sets neither of the first two and always sets
        `categories`, so ffmpeg wrote `genre=Music` on every music video and the
        keyword list on everything else. SoundCloud never hits this because its
        extractor supplies a real genre.
        """
        info = {'id': 'x', 'title': 'In The Pit', 'categories': ['Music'], 'tags': ['hardcore', 'gabber']}
        _, cleaned = DropCategoryGenrePP().run(info)
        self.assertIsNone(cleaned.get('categories'))
        self.assertIsNone(cleaned.get('tags'))
        self.assertEqual(cleaned['title'], 'In The Pit')

    def test_a_real_genre_from_the_extractor_survives(self):
        info = {'id': 'x', 'genre': 'Hardcore', 'categories': ['Music']}
        _, cleaned = DropCategoryGenrePP().run(info)
        self.assertEqual(cleaned['genre'], 'Hardcore')

    @patch('services.downloader.youtube.youtube.YoutubeDL')
    def test_downloader_strips_categories_before_the_metadata_is_written(self, mock_ytdlp):
        """The filter has to run before download, since FFmpegMetadata is added
        through the `postprocessors` option and therefore always runs first."""
        # This test drives the ordinary run. Without turning the cadence off the
        # channel would be deep-due -- it has never been deep-swept -- and take
        # the full-listing path instead.
        downloader = YoutubeDownloader(
            break_on_existing=False,
            timing=load_timing('youtube', overrides={'deep_sweep_days': 0}))
        downloader._create_ydl({})
        registered = [(type(call.args[0]).__name__, call.kwargs.get('when'))
                      for call in mock_ytdlp.return_value.add_post_processor.call_args_list]
        self.assertIn(('DropCategoryGenrePP', 'pre_process'), registered)


if __name__ == '__main__':
    unittest.main()
