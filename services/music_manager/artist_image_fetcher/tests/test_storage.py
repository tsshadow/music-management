import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

Image = pytest.importorskip('PIL.Image', reason='Pillow is only installed with the artist-image-fetcher extras')
from PIL import UnidentifiedImageError

from services.music_manager.artist_image_fetcher import storage


def png_bytes(size=(200, 100), mode='RGB', color=(10, 20, 30)):
    buffer = BytesIO()
    Image.new(mode, size, color if mode != 'P' else 0).save(buffer, 'PNG')
    return buffer.getvalue()


class ImageStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage = storage.ImageStorage(self.tmp.name, '/media/artist-images')

    def test_a_saved_image_is_cropped_square_and_reported_back(self):
        meta = self.storage.save_image(7, 'spotify', png_bytes(size=(200, 100)))
        self.assertEqual(meta['width'], meta['height'])
        self.assertEqual(meta['width'], 100)
        self.assertEqual(meta['mime_type'], 'image/jpeg')
        self.assertTrue(os.path.exists(meta['cached_path']))
        self.assertGreater(meta['file_size'], 0)
        self.assertTrue(meta['public_path'].startswith('/media/artist-images/7/'))

    def test_an_already_square_image_is_left_alone(self):
        meta = self.storage.save_image(7, 'spotify', png_bytes(size=(120, 120)))
        self.assertEqual((meta['width'], meta['height']), (120, 120))

    def test_the_primary_and_the_stable_thumbnails_are_written(self):
        self.storage.save_image(7, 'spotify', png_bytes())
        artist_dir = os.path.join(self.tmp.name, '7')
        self.assertTrue(os.path.exists(os.path.join(artist_dir, 'primary.jpg')))
        for size in (64, 160, 300, 640):
            self.assertTrue(os.path.exists(os.path.join(artist_dir, f'thumb_{size}.jpg')))

    def test_the_filename_carries_the_source_and_an_optional_prefix(self):
        meta = self.storage.save_image(7, 'lastfm', png_bytes(), filename_prefix='v2')
        self.assertTrue(os.path.basename(meta['cached_path']).startswith('v2-lastfm-'))

    def test_the_same_bytes_always_land_on_the_same_filename(self):
        data = png_bytes()
        first = self.storage.save_image(7, 'spotify', data)
        second = self.storage.save_image(7, 'spotify', data)
        self.assertEqual(first['cached_path'], second['cached_path'])

    def test_an_image_with_transparency_is_flattened_to_jpeg(self):
        meta = self.storage.save_image(7, 'spotify', png_bytes(mode='RGBA', color=(1, 2, 3, 4)))
        self.assertEqual(meta['mime_type'], 'image/jpeg')

    def test_bytes_that_are_not_an_image_are_reported_as_an_error(self):
        with self.assertRaises(UnidentifiedImageError):
            self.storage.save_image(7, 'spotify', b'this is not an image')

    # The fetcher decides how loud a failure is; storage only raises.
    def test_a_failure_is_raised_without_logging_anything(self):
        with self.assertNoLogs(storage.__name__, level='INFO'):
            with self.assertRaises(UnidentifiedImageError):
                self.storage.save_image(7, 'spotify', b'this is not an image')


class ImageDownloaderTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(storage.time, 'sleep')
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    # Three attempts back to back all land inside the same CDN hiccup.
    def test_the_attempts_are_spaced_out_with_a_growing_pause(self):
        downloader = storage.ImageDownloader(retries=3, backoff=0.5)
        with patch.object(storage, 'requests') as http:
            http.get.side_effect = RuntimeError('boom')
            with self.assertRaises(RuntimeError):
                downloader.download('https://img.test/a.jpg')
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [0.5, 1.0])

    def test_a_first_attempt_that_succeeds_does_not_wait(self):
        with patch.object(storage, 'requests') as http:
            http.get.return_value = MagicMock(content=b'binary')
            storage.ImageDownloader().download('https://img.test/a.jpg')
        self.sleep.assert_not_called()

    def test_the_body_of_a_successful_response_is_returned(self):
        downloader = storage.ImageDownloader()
        with patch.object(storage, 'requests') as http:
            http.get.return_value = MagicMock(content=b'binary')
            self.assertEqual(downloader.download('https://img.test/a.jpg'), b'binary')
        self.assertEqual(http.get.call_count, 1)

    def test_a_failing_download_is_retried_up_to_the_configured_limit(self):
        downloader = storage.ImageDownloader(retries=3)
        with patch.object(storage, 'requests') as http:
            http.get.side_effect = RuntimeError('boom')
            with self.assertRaises(RuntimeError):
                downloader.download('https://img.test/a.jpg')
        self.assertEqual(http.get.call_count, 3)

    def test_a_retry_that_finally_succeeds_returns_the_body(self):
        downloader = storage.ImageDownloader(retries=3)
        with patch.object(storage, 'requests') as http:
            http.get.side_effect = [RuntimeError('boom'), MagicMock(content=b'ok')]
            self.assertEqual(downloader.download('https://img.test/a.jpg'), b'ok')
        self.assertEqual(http.get.call_count, 2)

    def test_an_error_status_counts_as_a_failure(self):
        downloader = storage.ImageDownloader(retries=1)
        response = MagicMock()
        response.raise_for_status.side_effect = RuntimeError('404')
        with patch.object(storage, 'requests') as http:
            http.get.return_value = response
            with self.assertRaises(RuntimeError):
                downloader.download('https://img.test/a.jpg')

    # Each attempt is one artist's; a WARNING per retry was a push on the phone.
    def test_a_failed_attempt_is_logged_at_info_only(self):
        downloader = storage.ImageDownloader(retries=2)
        with patch.object(storage, 'requests') as http:
            http.get.side_effect = RuntimeError('boom')
            with self.assertLogs(storage.__name__, level='INFO') as logs:
                with self.assertRaises(RuntimeError):
                    downloader.download('https://img.test/a.jpg')
        self.assertEqual([r.levelname for r in logs.records], ['INFO', 'INFO'])

    def test_the_configured_timeout_is_passed_on(self):
        downloader = storage.ImageDownloader(timeout=42)
        with patch.object(storage, 'requests') as http:
            http.get.return_value = MagicMock(content=b'x')
            downloader.download('https://img.test/a.jpg')
        self.assertEqual(http.get.call_args.kwargs['timeout'], 42)


if __name__ == '__main__':
    unittest.main()
