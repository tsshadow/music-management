import json
import logging
import subprocess
from urllib.parse import urlparse

from yt_dlp.postprocessor import PostProcessor

from downloader.SoundcloudArchive import SoundcloudArchive
from postprocessing.Song.SoundcloudSong import SoundcloudSong


class SoundcloudSongProcessor(PostProcessor):
    """
    A yt-dlp postprocessor for SoundCloud downloads.

    After a track is downloaded, this postprocessor:
    - Fetches enriched metadata using yt-dlp's --dump-single-json.
    - Checks if the track already exists in the soundcloud_archive table.
    - If not present, inserts metadata into the database.
    - Finally, passes the file to SoundcloudSong for tagging and processing.

    This class ensures that all SoundCloud downloads are archived in the database
    and enriched with metadata for later tagging or analysis.
    """
    def run(self, info):
        path = info.get('filepath') or info.get('_filename')  # filepath may vary by yt-dlp version
        url = info.get('webpage_url')
        if not path or not url:
            logging.warning("Postprocessor: no path or URL found in info dict")
            return [], info

        logging.info(f"Postprocessing downloaded file: {path}")

        # Try to fetch extra metadata like uploader_id, original_url, and full title
        enriched_info = self._fetch_enriched_info(url)
        if not enriched_info:
            # Fallback: basic SoundcloudSong instance without extra metadata
            s = SoundcloudSong(path)
            s.parse()
            return [], info

        # Merge extra info into yt-dlp's original info dict
        info.update(enriched_info)

        account_name = self._extract_account_name_from_url(enriched_info.get("uploader_url"))
        account_id = enriched_info.get("channel_id")  or enriched_info.get("uploader_id") # '12345678' (sometimes present)
        video_id = enriched_info.get("id")

        # Check if we've already archived this track
        if SoundcloudArchive.exists(account_id, video_id):
            logging.info(f"Track already in soundcloud_archive: {account_name}/{video_id} — skipping.")
            return [], info

        # Store metadata in the archive table
        SoundcloudArchive.insert(
            account_name= account_name,
            account_id=account_id,
            video_id=video_id,
            path=path,
            url=enriched_info.get("original_url"),
            title=enriched_info.get("title")
        )

        # Tag or further process the song
        s = SoundcloudSong(path, enriched_info)
        s.parse()
        return [], info

    @staticmethod
    def _extract_account_name_from_url(uploader_url: str) -> str | None:
        try:
            path = urlparse(uploader_url).path  # e.g. '/aalst-dj'
            return path.strip('/').split('/')[0] or None
        except Exception as e:
            logging.warning(f"Failed to parse uploader_url '{uploader_url}': {e}")
            return None

    @staticmethod
    def _fetch_enriched_info(url: str):
        """
        Fetch full metadata from a SoundCloud URL using yt-dlp's --dump-single-json.

        This typically includes fields like:
        - uploader_id
        - title
        - original_url
        - id
        - description
        - tags

        Returns:
            dict: Enriched metadata, or None if the fetch failed.
        """
        try:
            result = subprocess.run(
                ["yt-dlp", "--dump-single-json", "--no-playlist", url],
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to enrich metadata for {url}: {e.stderr}")
        except Exception as e:
            logging.error(f"Unexpected error enriching metadata for {url}: {e}", exc_info=True)
        return None
