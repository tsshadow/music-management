import html
import logging
import os
import re
from typing import Optional

from yt_dlp.postprocessor import PostProcessor
from yt_dlp.utils import sanitize_filename

from downloader.YoutubeArchive import YoutubeArchive
from postprocessing.Song.YoutubeSong import YoutubeSong
from postprocessing.constants import TITLE


class YoutubeSongProcessor(PostProcessor):
    """Postprocessor that archives metadata and tags downloaded YouTube songs."""

    _GENERIC_TITLE_RE = re.compile(r".+ video #[0-9A-Za-z_-]+$", re.IGNORECASE)

    def run(self, info):
        path = info.get("filepath") or info.get("_filename")
        url = info.get("webpage_url")
        if not path or not url:
            logging.warning("Postprocessor: no path or URL found in info dict")
            return [], info

        logging.info(f"Postprocessing downloaded file: {path}")

        corrected_title = self._ensure_real_title(info, url)
        if corrected_title:
            path = self._apply_title_correction(path, info, corrected_title)

        title_for_archive = info.get("title")

        account = (
            info.get("uploader_id")
            or info.get("channel_id")
            or info.get("uploader")
            or info.get("channel")
        )
        video_id = info.get("id")

        if not YoutubeArchive.exists(account, video_id):
            YoutubeArchive.insert(account, video_id, path, url, title_for_archive)
        else:
            logging.info(
                f"Track already in youtube_archive: {account}/{video_id} — skipping insert."
            )

        song = YoutubeSong(path, info)
        if corrected_title:
            try:
                song.tag_collection.set_item(TITLE, corrected_title)
            except Exception as exc:  # pragma: no cover - defensive guard
                logging.warning(
                    "Failed to apply corrected title tag for %s: %s", path, exc
                )
        song.parse()
        return [], info

    def _ensure_real_title(self, info: dict, url: str) -> Optional[str]:
        """Return a better title if yt-dlp provided a generic placeholder."""

        title = info.get("title")
        if not self._needs_title_fix(title, info):
            return None

        logging.debug(
            "Attempting to recover missing YouTube title for %s", info.get("id")
        )
        webpage_title = self._fetch_title_from_webpage(url)
        if webpage_title and not self._needs_title_fix(webpage_title, info):
            info["title"] = webpage_title
            info["fulltitle"] = webpage_title
            return webpage_title

        return None

    def _needs_title_fix(self, title: Optional[str], info: dict) -> bool:
        if not title or not str(title).strip():
            return True

        extractor = info.get("extractor")
        video_id = info.get("id")
        if extractor and video_id:
            generic = f"{extractor.replace(':', '-') } video #{video_id}"
            if str(title).strip().lower() == generic.lower():
                return True

        return bool(self._GENERIC_TITLE_RE.match(str(title).strip()))

    def _fetch_title_from_webpage(self, url: str) -> Optional[str]:
        if not url:
            return None

        try:
            response = self._downloader.urlopen(url)
            data = response.read()
        except Exception as exc:  # pragma: no cover - network/IO failures
            logging.warning("Failed to refetch title from %s: %s", url, exc)
            return None

        try:
            webpage = data.decode("utf-8", "replace")
        except Exception:
            webpage = data.decode("latin-1", "replace")

        for pattern in (
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']title["\'][^>]+content=["\']([^"\']+)["\']',
            r"<title>([^<]+)</title>",
        ):
            match = re.search(pattern, webpage, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            raw = html.unescape(match.group(1)).strip()
            if raw.lower().endswith("- youtube"):
                raw = raw[:-9].strip()
            if raw:
                return raw

        return None

    def _apply_title_correction(self, path: str, info: dict, new_title: str) -> str:
        """Rename the downloaded file and update metadata to use *new_title*."""

        new_path = self._build_target_path(info, new_title)
        current_path = path

        if new_path and os.path.normpath(new_path) != os.path.normpath(path):
            if os.path.exists(new_path):
                logging.warning(
                    "Cannot rename %s to %s because the target already exists",
                    path,
                    new_path,
                )
            else:
                try:
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    os.replace(path, new_path)
                    logging.info("Renamed download %s -> %s", path, new_path)
                    current_path = new_path
                except OSError as exc:  # pragma: no cover - filesystem errors
                    logging.warning(
                        "Failed to rename %s to %s: %s", path, new_path, exc
                    )

        info["title"] = new_title
        info["fulltitle"] = new_title
        info["filepath"] = current_path
        info["_filename"] = current_path

        for entry in info.get("requested_downloads") or []:
            entry["filepath"] = current_path
            entry["_filename"] = current_path
            if "filename" in entry:
                entry["filename"] = os.path.basename(current_path)

        return current_path

    def _build_target_path(self, info: dict, title: str) -> Optional[str]:
        info_for_template = dict(info)
        info_for_template["title"] = title
        info_for_template["fulltitle"] = title

        try:
            return self._downloader.prepare_filename(info_for_template)
        except Exception as exc:
            logging.warning("Could not compute filename for corrected title: %s", exc)

            path = info.get("filepath") or info.get("_filename")
            if not path:
                return None
            directory, _ = os.path.split(path)
            ext = info.get("ext") or os.path.splitext(path)[1].lstrip(".")
            sanitized = sanitize_filename(title, restricted=False)
            if not sanitized:
                return None
            return os.path.join(directory, f"{sanitized}.{ext}")

