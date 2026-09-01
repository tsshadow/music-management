import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yt_dlp.utils import sanitize_filename

from services.tagger.constants import SongTypeEnum


class DummyYoutubeArchive:
    inserted = []

    @staticmethod
    def exists(_account, _video_id, _download_type='audio'):
        return False

    @staticmethod
    def insert(account, video_id, path, url, title, download_type='audio'):
        DummyYoutubeArchive.inserted.append((account, video_id, path, url, title, download_type))


# Import via the fully-qualified "services." path (matching every other test in
# this suite, e.g. YoutubeDownloaderTest.py) rather than a bare top-level alias:
# since services/ and the repo root are both on sys.path, importing under two
# different dotted names would create two separate module objects for the same
# file, so a unittest.mock.patch() targeting the "services.downloader..." path
# (as used below) would silently miss the module actually executed by this test.
from services.downloader.youtube import YoutubeSongProcessor


class DummyDownloader:
    def __init__(self, base_dir, html):
        self.base_dir = base_dir
        self.html = html
        self.params = {}

    def prepare_filename(self, info):
        uploader = info.get('uploader') or info.get('channel') or 'NA'
        title = info.get('title') or info.get('id') or 'download'
        ext = info.get('ext', 'm4a')
        uploader_dir = sanitize_filename(uploader, restricted=True) or 'NA'
        title_part = sanitize_filename(title, restricted=True) or info.get('id', 'download')
        path = os.path.join(self.base_dir, uploader_dir, f'{title_part}.{ext}')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def urlopen(self, _url):
        return io.BytesIO(self.html.encode('utf-8'))

    def to_console_title(self, *_args, **_kwargs):
        return None

    def evaluate_outtmpl(self, _template, _info_dict=None, **_kwargs):
        return ''


class YoutubeSongProcessorTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        DummyYoutubeArchive.inserted.clear()
        # Patch YoutubeArchive/Tagger on the actual module used by
        # YoutubeSongProcessor.run() via unittest.mock.patch (reverted in
        # tearDown), rather than pre-seeding sys.modules at import time: the
        # latter only affects the *first* import of this module across the
        # whole pytest session, so it silently stops working whenever another
        # test file imports YoutubeSongProcessor first.
        self.archive_patcher = patch(
            'services.downloader.youtube.YoutubeSongProcessor.YoutubeArchive', DummyYoutubeArchive
        )
        self.archive_patcher.start()

    def tearDown(self):
        self.archive_patcher.stop()
        self.temp_dir.cleanup()

    def test_recovers_title_and_renames_file(self):
        html = '<html><head><meta property="og:title" content="Noiseflow | Defqon.1 2025"></head><body></body></html>'
        processor = YoutubeSongProcessor()
        processor._downloader = DummyDownloader(self.temp_dir.name, html)
        info = {
            'id': '5mKayZadF4g',
            'title': 'youtube video #5mKayZadF4g',
            'fulltitle': 'youtube video #5mKayZadF4g',
            'extractor': 'youtube',
            'uploader': 'Q-dance',
            'uploader_id': 'qdance',
            'ext': 'm4a',
            'webpage_url': 'https://www.youtube.com/watch?v=5mKayZadF4g',
        }
        original_path = processor._downloader.prepare_filename(info)
        with open(original_path, 'wb') as handle:
            handle.write(b'data')
        info['filepath'] = original_path
        info['_filename'] = original_path
        info['requested_downloads'] = [
            {'filepath': original_path, '_filename': original_path, 'filename': os.path.basename(original_path)}
        ]
        expected_info = dict(info)
        expected_info['title'] = 'Noiseflow | Defqon.1 2025'
        expected_path = processor._downloader.prepare_filename(expected_info)
        with patch('services.downloader.youtube.YoutubeSongProcessor.Tagger') as mock_tagger:
            processor.run(info)
            mock_tagger.parse_song.assert_called_with(Path(info['filepath']), SongTypeEnum.YOUTUBE, extra_info=info)
        self.assertEqual(info['title'], 'Noiseflow | Defqon.1 2025')
        self.assertEqual(info['fulltitle'], 'Noiseflow | Defqon.1 2025')
        self.assertEqual(os.path.normpath(info['filepath']), os.path.normpath(expected_path))
        self.assertFalse(os.path.exists(original_path))
        self.assertTrue(os.path.exists(expected_path))
        self.assertEqual(os.path.normpath(info['requested_downloads'][0]['filepath']), os.path.normpath(expected_path))
        self.assertEqual(os.path.normpath(info['requested_downloads'][0]['_filename']), os.path.normpath(expected_path))
        self.assertEqual(
            DummyYoutubeArchive.inserted[-1],
            ('qdance', '5mKayZadF4g', info['filepath'], info['webpage_url'], 'Noiseflow | Defqon.1 2025', 'audio'),
        )


if __name__ == '__main__':
    unittest.main()
