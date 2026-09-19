import unittest
from unittest.mock import MagicMock, patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

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

    def test_a_tagged_download_is_announced(self):
        # Both branches -- with and without the enriched dict -- end in the same announce,
        # after the tag pass, so the walk does not tag the file again.
        module = 'services.downloader.soundcloud.SoundcloudSongProcessor'
        info = {'filepath': '/mnt/music/Soundcloud/MOTZ/a.mp3', 'webpage_url': 'https://soundcloud.com/motz/a'}
        for enriched in (None, {'uploader_url': 'https://soundcloud.com/motz', 'id': '1', 'uploader_id': 'motz'}):
            with (
                patch(f'{module}.Tagger') as tagger,
                patch(f'{module}.announce') as announce,
                patch(f'{module}.SoundcloudArchive') as archive,
                patch.object(SoundcloudSongProcessor, '_fetch_enriched_info', return_value=enriched),
            ):
                archive.exists.return_value = True
                tagger.parse_song.return_value = MagicMock()
                SoundcloudSongProcessor().run(dict(info))
                announce.assert_called_once_with(info['filepath'])

    def test_a_download_the_tagger_could_not_read_is_not_announced(self):
        module = 'services.downloader.soundcloud.SoundcloudSongProcessor'
        info = {'filepath': '/mnt/music/Soundcloud/MOTZ/a.mp3', 'webpage_url': 'https://soundcloud.com/motz/a'}
        with (
            patch(f'{module}.Tagger') as tagger,
            patch(f'{module}.announce') as announce,
            patch.object(SoundcloudSongProcessor, '_fetch_enriched_info', return_value=None),
        ):
            tagger.parse_song.return_value = None
            SoundcloudSongProcessor().run(info)
        announce.assert_not_called()


if __name__ == '__main__':
    unittest.main()
