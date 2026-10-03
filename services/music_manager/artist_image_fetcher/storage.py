import contextlib
import hashlib
import logging
import os
import shutil
import time
from io import BytesIO

from PIL import Image

from . import safe_fetch

#: The sizes `_generate_thumbnails` writes, per image and as the stable `thumb_<size>.jpg`.
THUMBNAIL_SIZES = (64, 160, 300, 640)
#: The file the web player falls back to (`/media/artist-images/<id>/primary.jpg`).
PRIMARY_FILENAME = 'primary.jpg'


class ImageStorage:
    """Saves fetched artist images to disk and builds their public URLs.

    Each image is kept under its own name (`<source>-<hash>.jpg` plus thumbnails), so an
    earlier portrait can be selected again. Next to those sit the *published* copies,
    `primary.jpg` and `thumb_<size>.jpg`, which are what a fixed URL serves: they must
    follow whatever the artist's primary image is, and disappear when it is cleared.
    """

    def __init__(self, storage_path, public_base_url):
        self.storage_path = storage_path
        self.public_base_url = public_base_url
        self.logger = logging.getLogger(__name__)

    def save_image(self, artist_id, source, image_data, filename_prefix=None):
        """Save image data, generate thumbnails and return the metadata.

        Errors are raised, not logged: the fetcher decides whether a failure is one
        artist's (INFO, counted into the run summary) or the whole run's (an image
        directory that cannot be written, one ERROR per run).
        """
        artist_dir = os.path.join(self.storage_path, str(artist_id))
        os.makedirs(artist_dir, exist_ok=True)
        img: Image.Image = Image.open(BytesIO(image_data))
        file_hash = hashlib.md5(image_data).hexdigest()
        ext = 'jpg'
        base_filename = f'{source}-{file_hash}'
        if filename_prefix:
            base_filename = f'{filename_prefix}-{base_filename}'
        full_filename = f'{base_filename}.{ext}'
        cached_path = os.path.join(artist_dir, full_filename)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img = self._square_crop(img)
        img.save(cached_path, 'JPEG', quality=90)
        self._generate_thumbnails(img, artist_dir, base_filename)
        primary_path = os.path.join(artist_dir, 'primary.jpg')
        img.save(primary_path, 'JPEG', quality=90)
        return {
            'cached_path': cached_path,
            'public_path': f'{self.public_base_url}/{artist_id}/{full_filename}',
            'width': img.size[0],
            'height': img.size[1],
            'mime_type': 'image/jpeg',
            'file_size': os.path.getsize(cached_path),
        }

    def _square_crop(self, img):
        width, height = img.size
        if width == height:
            return img
        new_size = min(width, height)
        left = (width - new_size) / 2
        top = (height - new_size) / 2
        right = (width + new_size) / 2
        bottom = (height + new_size) / 2
        return img.crop((left, top, right, bottom))

    def _generate_thumbnails(self, img, artist_dir, base_filename):
        paths = {}
        for size in THUMBNAIL_SIZES:
            thumb = img.copy()
            thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
            thumb_filename = f'{base_filename}_{size}.jpg'
            thumb_path = os.path.join(artist_dir, thumb_filename)
            thumb.save(thumb_path, 'JPEG', quality=85)
            stable_thumb_path = os.path.join(artist_dir, f'thumb_{size}.jpg')
            thumb.save(stable_thumb_path, 'JPEG', quality=85)
            paths[size] = thumb_path
        return paths

    def unpublish_primary(self, artist_id):
        """Remove the published `primary.jpg` and `thumb_<size>.jpg`; keep every stored image.

        Clearing a portrait used to leave these behind, so the fixed URL kept serving
        the picture that had just been removed. Returns how many files were removed.
        """
        artist_dir = os.path.join(self.storage_path, str(artist_id))
        removed = 0
        for filename in [PRIMARY_FILENAME] + [f'thumb_{size}.jpg' for size in THUMBNAIL_SIZES]:
            with contextlib.suppress(FileNotFoundError):
                os.remove(os.path.join(artist_dir, filename))
                removed += 1
        return removed

    def publish_primary(self, artist_id, cached_path):
        """Make the stored image at `cached_path` the published one for `artist_id`.

        Copies it to `primary.jpg` and its thumbnails to `thumb_<size>.jpg`. A thumbnail
        that is not there (an image stored before thumbnails existed) removes the stale
        published one rather than leaving the previous portrait's thumbnail in place.
        False when the image itself is gone from disk; nothing is changed then.
        """
        if not cached_path or not os.path.exists(cached_path):
            return False
        artist_dir = os.path.join(self.storage_path, str(artist_id))
        os.makedirs(artist_dir, exist_ok=True)
        shutil.copyfile(cached_path, os.path.join(artist_dir, PRIMARY_FILENAME))
        base = os.path.splitext(cached_path)[0]
        for size in THUMBNAIL_SIZES:
            stable = os.path.join(artist_dir, f'thumb_{size}.jpg')
            source = f'{base}_{size}.jpg'
            if os.path.exists(source):
                shutil.copyfile(source, stable)
            else:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(stable)
        return True


class ImageDownloader:
    """Downloads image bytes, retrying a failed attempt after a short, growing pause.

    The URL comes from a provider's API answer, so it is fetched through safe_fetch: an
    address that is not public is refused (and not retried), and a response is capped at
    ten megabytes, the same limits as the manual "image from URL" route.
    """

    def __init__(self, timeout=10, retries=3, backoff=1.0, max_bytes=safe_fetch.DEFAULT_MAX_BYTES):
        self.timeout = timeout
        self.retries = retries
        # Seconds before the second attempt; doubled for each one after. Three attempts
        # back to back all land inside the same CDN hiccup.
        self.backoff = backoff
        self.max_bytes = max_bytes
        self.logger = logging.getLogger(__name__)

    def download(self, url):
        """Return the body at `url`; raise the last error once every attempt failed."""
        for i in range(self.retries):
            try:
                return safe_fetch.fetch(url, timeout=self.timeout, max_bytes=self.max_bytes)
            except (safe_fetch.UnsafeUrl, safe_fetch.ResponseTooLarge):
                # Asking again gets the same answer.
                raise
            except Exception as e:
                # INFO: one attempt for one artist. The final failure is raised to the
                # fetcher, which counts it into the run summary.
                self.logger.info(f'Attempt {i + 1} failed to download {url}: {e}')
                if i == self.retries - 1:
                    raise
                time.sleep(self.backoff * (2**i))
        return None
