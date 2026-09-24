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

    def test_enrichment_presents_the_session_the_download_used(self):
        # Production downloads with the logged-in Firefox profile; the enrichment asks
        # SoundCloud for the same track a second later. Without the cookies that second
        # request is anonymous, and SoundCloud answers 401 for every promo or
        # follower-only track -- four of them on 2026-09-23, each 0.8s after its own
        # "Postprocessing downloaded file" line.
        module = 'services.downloader.soundcloud.SoundcloudSongProcessor'
        ydl_opts = {
            'cookiesfrombrowser': ('firefox', '/firefox-config/profile'),
            'http_headers': {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:151.0) Firefox/151.0'},
        }
        with patch(f'{module}.subprocess.run') as run:
            run.return_value = MagicMock(stdout='{}')
            SoundcloudSongProcessor(ydl_opts)._fetch_enriched_info('https://soundcloud.com/merciless_music/promo')
        command = run.call_args.args[0]
        self.assertIn('--cookies-from-browser', command)
        self.assertEqual('firefox:/firefox-config/profile', command[command.index('--cookies-from-browser') + 1])
        self.assertIn('--user-agent', command)
        self.assertEqual(ydl_opts['http_headers']['User-Agent'], command[command.index('--user-agent') + 1])
        self.assertEqual('https://soundcloud.com/merciless_music/promo', command[-1])

    def test_enrichment_presents_a_cookie_file_when_that_is_what_was_configured(self):
        module = 'services.downloader.soundcloud.SoundcloudSongProcessor'
        for key in ('cookiefile', 'cookies'):
            with patch(f'{module}.subprocess.run') as run:
                run.return_value = MagicMock(stdout='{}')
                processor = SoundcloudSongProcessor({key: 'soundcloud.com_cookies.txt'})
                processor._fetch_enriched_info('https://soundcloud.com/motz/a')
            command = run.call_args.args[0]
            self.assertIn('--cookies', command)
            self.assertEqual('soundcloud.com_cookies.txt', command[command.index('--cookies') + 1])

    def test_enrichment_without_a_session_asks_for_nothing_extra(self):
        # A processor built without the download's options is still the old anonymous
        # call rather than a crash; nothing in the tree constructs one, but the
        # yt-dlp base class may.
        module = 'services.downloader.soundcloud.SoundcloudSongProcessor'
        with patch(f'{module}.subprocess.run') as run:
            run.return_value = MagicMock(stdout='{}')
            SoundcloudSongProcessor()._fetch_enriched_info('https://soundcloud.com/motz/a')
        self.assertEqual(
            ['yt-dlp', '--dump-single-json', '--no-playlist', 'https://soundcloud.com/motz/a'],
            run.call_args.args[0],
        )

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
