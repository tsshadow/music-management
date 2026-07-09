import os
import requests
import hashlib
import logging
from PIL import Image
from io import BytesIO

class ImageStorage:
    def __init__(self, storage_path, public_base_url):
        self.storage_path = storage_path
        self.public_base_url = public_base_url
        self.logger = logging.getLogger(__name__)

    def save_image(self, artist_id, source, image_data, filename_prefix=None):
        """
        Saves image data, generates thumbnails and returns metadata.
        """
        artist_dir = os.path.join(self.storage_path, str(artist_id))
        os.makedirs(artist_dir, exist_ok=True)

        try:
            img = Image.open(BytesIO(image_data))

            # Basic info
            width, height = img.size
            mime_type = Image.MIME.get(img.format, 'image/jpeg')

            # Generate a unique hash for the filename to avoid duplicates/caching issues
            file_hash = hashlib.md5(image_data).hexdigest()
            ext = "jpg" # Always save as jpg for consistency

            base_filename = f"{source}-{file_hash}"
            if filename_prefix:
                base_filename = f"{filename_prefix}-{base_filename}"

            full_filename = f"{base_filename}.{ext}"
            cached_path = os.path.join(artist_dir, full_filename)

            # Convert to RGB if necessary (e.g. for PNG with transparency)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Square crop if requested (recommended)
            img = self._square_crop(img)

            # Save original (resized to a max if needed)
            img.save(cached_path, "JPEG", quality=90)

            # Generate thumbnails
            thumbnails = self._generate_thumbnails(img, artist_dir, base_filename)

            # Also save as primary.jpg for LMS convention
            primary_path = os.path.join(artist_dir, "primary.jpg")
            img.save(primary_path, "JPEG", quality=90)

            return {
                'cached_path': cached_path,
                'public_path': f"{self.public_base_url}/{artist_id}/{full_filename}",
                'width': img.size[0],
                'height': img.size[1],
                'mime_type': 'image/jpeg',
                'file_size': os.path.getsize(cached_path)
            }
        except Exception as e:
            self.logger.error(f"Error saving image for artist {artist_id}: {e}")
            raise

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
        sizes = [64, 160, 300, 640]
        paths = {}

        for size in sizes:
            thumb = img.copy()
            thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
            thumb_filename = f"{base_filename}_{size}.jpg"
            thumb_path = os.path.join(artist_dir, thumb_filename)
            thumb.save(thumb_path, "JPEG", quality=85)

            # Also save stable thumbnail paths
            stable_thumb_path = os.path.join(artist_dir, f"thumb_{size}.jpg")
            thumb.save(stable_thumb_path, "JPEG", quality=85)

            paths[size] = thumb_path

        return paths

class ImageDownloader:
    def __init__(self, timeout=10, retries=3):
        self.timeout = timeout
        self.retries = retries
        self.logger = logging.getLogger(__name__)

    def download(self, url):
        for i in range(self.retries):
            try:
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.content
            except Exception as e:
                self.logger.warning(f"Attempt {i+1} failed to download {url}: {e}")
                if i == self.retries - 1:
                    raise
        return None
