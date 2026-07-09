import unittest
from unittest.mock import MagicMock, patch
from services.tests.mock_base import setup_mocks, reset_database_helpers

setup_mocks()

from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.tagger.constants import TITLE

class TestSoundcloudBasicRun(unittest.TestCase):

    def setUp(self):
        reset_database_helpers()
        self.processor = None
        self.archive_patcher = patch('services.downloader.soundcloud.SoundcloudSongProcessor.SoundcloudArchive')
        self.mock_archive = self.archive_patcher.start()
        self.mock_archive.exists.return_value = False
        
        self.db_patcher = patch('services.downloader.soundcloud.soundcloud.get_accounts_from_db')
        self.mock_get_accounts = self.db_patcher.start()
        self.mock_get_accounts.return_value = ['albino_music']

        self.path_exists_patcher = patch('pathlib.Path.exists')
        self.mock_path_exists = self.path_exists_patcher.start()
        self.mock_path_exists.return_value = True

        self.makedirs_patcher = patch('os.makedirs')
        self.makedirs_patcher.start()

    def tearDown(self):
        patch.stopall()

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    @patch('services.downloader.soundcloud.SoundcloudSongProcessor.subprocess.run')
    def test_run_basic(self, mock_subprocess, mock_ytdlp):
        dl_info = {
            'id': 'rije-moat-1',
            'title': 'RIJE MOAT',
            'uploader': 'Albino',
            'webpage_url': 'https://soundcloud.com/albino_music/rije-moat-1',
            'ext': 'mp3',
            'filepath': '/tmp/soundcloud/Albino/RIJE MOAT.mp3'
        }
        
        enriched_info = {
            'id': 'rije-moat-1',
            'title': 'RIJE MOAT',
            'uploader': 'Albino',
            'uploader_url': 'https://soundcloud.com/albino_music',
            'original_url': 'https://soundcloud.com/albino_music/rije-moat-1',
            'genre': 'Hardstyle',
            'channel_id': 'albino_id'
        }
        
        mock_instance = mock_ytdlp.return_value.__enter__.return_value
        
        def mock_add_pp(pp):
            if "SoundcloudSongProcessor" in str(type(pp)):
                self.processor = pp
        mock_instance.add_post_processor.side_effect = mock_add_pp

        def mock_download(links):
            if self.processor:
                self.processor.run(dl_info)
            return 0
        mock_instance.download.side_effect = mock_download
        
        import json
        mock_subprocess.return_value = MagicMock(stdout=json.dumps(enriched_info), check_returncode=lambda: None)

        downloader = SoundcloudDownloader(break_on_existing=False)
        with patch('time.sleep'):
            downloader.run(account='albino_music')

        from services.tagger.Song.SoundcloudSong import SoundcloudSong
        song = SoundcloudSong(dl_info['filepath'], enriched_info)
        song.tag_collection.set_item(TITLE, 'RIJE MOAT')
        song.parse()
        
        self.assertEqual(song.title(), 'RIJE MOAT')
        self.assertEqual(song.album(), 'Soundcloud (Albino)')
        self.assertEqual(song.publisher(), 'Soundcloud')

if __name__ == '__main__':
    unittest.main()
