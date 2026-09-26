import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

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


class PublishedPortraitTest(unittest.TestCase):
    """Bug 080: the fixed-URL copies outlived a cleared portrait and a changed selection."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage = storage.ImageStorage(self.tmp.name, '/media/artist-images')
        self.artist_dir = os.path.join(self.tmp.name, '7')

    def published(self):
        return sorted(
            name for name in os.listdir(self.artist_dir) if name == 'primary.jpg' or name.startswith('thumb_')
        )

    def test_clearing_removes_the_published_copies_and_keeps_the_stored_image(self):
        meta = self.storage.save_image(7, 'spotify', png_bytes())
        self.assertEqual(self.storage.unpublish_primary(7), 5)
        self.assertEqual(self.published(), [])
        self.assertTrue(os.path.exists(meta['cached_path']))

    def test_clearing_twice_or_without_a_directory_is_harmless(self):
        self.assertEqual(self.storage.unpublish_primary(8), 0)
        self.storage.save_image(7, 'spotify', png_bytes())
        self.storage.unpublish_primary(7)
        self.assertEqual(self.storage.unpublish_primary(7), 0)

    def test_selecting_a_stored_image_publishes_it(self):
        first = self.storage.save_image(7, 'spotify', png_bytes(color=(200, 0, 0)))
        self.storage.save_image(7, 'lastfm', png_bytes(color=(0, 0, 200)))
        self.assertTrue(self.storage.publish_primary(7, first['cached_path']))
        with (
            open(first['cached_path'], 'rb') as source,
            open(os.path.join(self.artist_dir, 'primary.jpg'), 'rb') as primary,
        ):
            self.assertEqual(source.read(), primary.read())
        self.assertEqual(len(self.published()), 5)

    def test_publishing_after_a_clear_restores_the_copies(self):
        meta = self.storage.save_image(7, 'spotify', png_bytes())
        self.storage.unpublish_primary(7)
        self.storage.publish_primary(7, meta['cached_path'])
        self.assertEqual(len(self.published()), 5)

    def test_an_image_gone_from_disk_publishes_nothing(self):
        self.assertFalse(self.storage.publish_primary(7, os.path.join(self.tmp.name, 'missing.jpg')))
        self.assertFalse(self.storage.publish_primary(7, None))

    def test_a_missing_thumbnail_removes_the_stale_one(self):
        meta = self.storage.save_image(7, 'spotify', png_bytes())
        os.remove(os.path.splitext(meta['cached_path'])[0] + '_300.jpg')
        self.storage.publish_primary(7, meta['cached_path'])
        self.assertFalse(os.path.exists(os.path.join(self.artist_dir, 'thumb_300.jpg')))
        self.assertTrue(os.path.exists(os.path.join(self.artist_dir, 'thumb_64.jpg')))


class ImageDownloaderTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(storage.time, 'sleep')
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)
        fetch_patcher = patch.object(storage.safe_fetch, 'fetch')
        self.fetch = fetch_patcher.start()
        self.addCleanup(fetch_patcher.stop)

    # Three attempts back to back all land inside the same CDN hiccup.
    def test_the_attempts_are_spaced_out_with_a_growing_pause(self):
        downloader = storage.ImageDownloader(retries=3, backoff=0.5)
        self.fetch.side_effect = RuntimeError('boom')
        with self.assertRaises(RuntimeError):
            downloader.download('https://img.test/a.jpg')
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [0.5, 1.0])

    def test_a_first_attempt_that_succeeds_does_not_wait(self):
        self.fetch.return_value = b'binary'
        storage.ImageDownloader().download('https://img.test/a.jpg')
        self.sleep.assert_not_called()

    def test_the_body_of_a_successful_response_is_returned(self):
        self.fetch.return_value = b'binary'
        self.assertEqual(storage.ImageDownloader().download('https://img.test/a.jpg'), b'binary')
        self.assertEqual(self.fetch.call_count, 1)

    def test_a_failing_download_is_retried_up_to_the_configured_limit(self):
        self.fetch.side_effect = RuntimeError('boom')
        with self.assertRaises(RuntimeError):
            storage.ImageDownloader(retries=3).download('https://img.test/a.jpg')
        self.assertEqual(self.fetch.call_count, 3)

    def test_a_retry_that_finally_succeeds_returns_the_body(self):
        self.fetch.side_effect = [RuntimeError('boom'), b'ok']
        self.assertEqual(storage.ImageDownloader(retries=3).download('https://img.test/a.jpg'), b'ok')
        self.assertEqual(self.fetch.call_count, 2)

    def test_an_error_status_counts_as_a_failure(self):
        self.fetch.side_effect = storage.safe_fetch.FetchFailed(404, 'https://img.test/a.jpg')
        with self.assertRaises(storage.safe_fetch.FetchFailed):
            storage.ImageDownloader(retries=1).download('https://img.test/a.jpg')

    # A provider answer naming an internal address is refused once, not three times.
    def test_a_non_public_url_is_refused_without_a_retry(self):
        self.fetch.side_effect = storage.safe_fetch.UnsafeUrl('URL points at a non-public address')
        with self.assertRaises(storage.safe_fetch.UnsafeUrl):
            storage.ImageDownloader(retries=3).download('http://internal.example/a.jpg')
        self.assertEqual(self.fetch.call_count, 1)
        self.sleep.assert_not_called()

    def test_an_oversized_image_is_refused_without_a_retry(self):
        self.fetch.side_effect = storage.safe_fetch.ResponseTooLarge('too big')
        with self.assertRaises(storage.safe_fetch.ResponseTooLarge):
            storage.ImageDownloader(retries=3).download('https://img.test/a.jpg')
        self.assertEqual(self.fetch.call_count, 1)

    # Each attempt is one artist's; a WARNING per retry was a push on the phone.
    def test_a_failed_attempt_is_logged_at_info_only(self):
        self.fetch.side_effect = RuntimeError('boom')
        with self.assertLogs(storage.__name__, level='INFO') as logs:
            with self.assertRaises(RuntimeError):
                storage.ImageDownloader(retries=2).download('https://img.test/a.jpg')
        self.assertEqual([r.levelname for r in logs.records], ['INFO', 'INFO'])

    def test_the_configured_timeout_and_size_cap_are_passed_on(self):
        self.fetch.return_value = b'x'
        storage.ImageDownloader(timeout=42).download('https://img.test/a.jpg')
        self.assertEqual(self.fetch.call_args.kwargs['timeout'], 42)
        self.assertEqual(self.fetch.call_args.kwargs['max_bytes'], 10 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
