import html
import logging
import os
import re
from pathlib import Path

from yt_dlp.postprocessor import PostProcessor
from yt_dlp.utils import sanitize_filename

from services.common.Helpers.NotificationService import notification_service
from services.downloader.redownload import REPLACED_KEY
from services.downloader.youtube.YoutubeAccount import AUDIO, VIDEO
from services.downloader.youtube.YoutubeArchive import YoutubeArchive
from services.tagger.announce import announce
from services.tagger.constants import SongTypeEnum
from services.tagger.Song.ReleaseDate import format_release_date
from services.tagger.tagger import Tagger

# Anything below this came out of a progressive-only fallback or a channel that
# genuinely offers nothing better. Worth saying out loud either way, because the
# whole point of the video pass is not ending up with another 640x360 library.
MIN_EXPECTED_VIDEO_HEIGHT = 720


def _video_message(info: dict, title) -> str:
    """The push body for a video download, in the same `Label=value` shape BaseSong uses.

    A video is never tagged, so there is no Song to ask -- the date has to come off the
    info dict here. `release_date` is what YouTube states for a premiere or a music video;
    `upload_date` is the fallback and the only one most channels set.
    """
    released = format_release_date(info.get('release_date') or info.get('upload_date'))
    if not released:
        return str(title)
    return f'{title}\nReleased={released}'


class YoutubeSongProcessor(PostProcessor):
    """Postprocessor that archives metadata and tags downloaded YouTube songs.

    A video download is archived the same way but not tagged: an mkv of a
    two-hour festival set is not a track, and running it through the tagger would
    only add a bogus artist/title split to the library.
    """

    _GENERIC_TITLE_RE = re.compile('.+ video #[0-9A-Za-z_-]+$', re.IGNORECASE)

    def __init__(self, downloader=None, download_type: str = AUDIO):
        super().__init__(downloader)
        self.download_type = download_type

    def run(self, info):
        path = info.get('filepath') or info.get('_filename')
        url = info.get('webpage_url')
        if not path or not url:
            logging.warning('Postprocessor: no path or URL found in info dict')
            return ([], info)
        logging.info(f'Postprocessing downloaded file: {path}')
        corrected_title = self._ensure_real_title(info, url)
        # Not after a redownload was put in place of a library file: that name is the one
        # the library already knows, and renaming it would move it into the staging folder
        # yt-dlp's filename template points at. The corrected title still reaches the tags.
        if corrected_title and not info.get(REPLACED_KEY):
            path = self._apply_title_correction(path, info, corrected_title)
        title_for_archive = info.get('title')
        account = info.get('uploader_id') or info.get('channel_id') or info.get('uploader') or info.get('channel')
        video_id = info.get('id')
        if not YoutubeArchive.exists(account, video_id, self.download_type):
            # The whole info dict goes with it. The tagger reads four fields out of it
            # and drops the rest, so the music-credit artists/track/album, the
            # categories and a long set's chapter list were never written down.
            YoutubeArchive.insert(
                account,
                video_id,
                path,
                url,
                title_for_archive,
                download_type=self.download_type,
                raw_info=info,
            )
        else:
            logging.info(
                f'Track already in downloads_youtube_archive: {account}/{video_id} '
                f'({self.download_type}) — skipping insert.'
            )
        if self.download_type == VIDEO:
            self._report_resolution(info, title_for_archive)
            notification_service.notify(
                _video_message(info, title_for_archive), title='YouTube Video Download Complete'
            )
            return ([], info)
        song = Tagger.parse_song(Path(path), SongTypeEnum.YOUTUBE, extra_info=info)
        if song:
            # Bookkeeping, LMS and the scanner -- the file is tagged, now make it exist
            # for everyone else without waiting for the walk.
            announce(path)
            notification_service.notify(str(song), title='YouTube Download Complete')
        return ([], info)

    def _report_resolution(self, info: dict, title) -> None:
        """Log what we actually got, so a silent quality drop cannot hide."""
        height = info.get('height')
        width = info.get('width')
        if not height:
            logging.info('Downloaded video %s without a reported resolution.', title)
            return
        logging.info('Downloaded video %s at %sx%s.', title, width or '?', height)
        if height < MIN_EXPECTED_VIDEO_HEIGHT:
            logging.warning(
                'Video %s came in at only %sp. Either the channel offers nothing better, '
                'or yt-dlp fell back to a progressive stream because merging failed.',
                title,
                height,
            )

    def _ensure_real_title(self, info: dict, url: str) -> str | None:
        """Return a better title if yt-dlp provided a generic placeholder."""
        title = info.get('title')
        if not self._needs_title_fix(title, info):
            return None
        logging.debug('Attempting to recover missing YouTube title for %s', info.get('id'))
        webpage_title = self._fetch_title_from_webpage(url)
        if webpage_title and (not self._needs_title_fix(webpage_title, info)):
            info['title'] = webpage_title
            info['fulltitle'] = webpage_title
            return webpage_title
        return None

    def _needs_title_fix(self, title: str | None, info: dict) -> bool:
        if not title or not str(title).strip():
            return True
        extractor = info.get('extractor')
        video_id = info.get('id')
        if extractor and video_id:
            generic = f"{extractor.replace(':', '-')} video #{video_id}"
            if str(title).strip().lower() == generic.lower():
                return True
        return bool(self._GENERIC_TITLE_RE.match(str(title).strip()))

    def _fetch_title_from_webpage(self, url: str) -> str | None:
        if not url:
            return None
        try:
            response = self._downloader.urlopen(url)
            data = response.read()
        except Exception as exc:
            logging.warning('Failed to refetch title from %s: %s', url, exc)
            return None
        try:
            webpage = data.decode('utf-8', 'replace')
        except Exception:
            webpage = data.decode('latin-1', 'replace')
        for pattern in (
            '<meta[^>]+property=["\\\']og:title["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
            '<meta[^>]+name=["\\\']title["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
            '<title>([^<]+)</title>',
        ):
            match = re.search(pattern, webpage, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            raw = html.unescape(match.group(1)).strip()
            if raw.lower().endswith('- youtube'):
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
                logging.warning('Cannot rename %s to %s because the target already exists', path, new_path)
            else:
                try:
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    os.replace(path, new_path)
                    logging.info('Renamed download %s -> %s', path, new_path)
                    current_path = new_path
                except OSError as exc:
                    logging.warning('Failed to rename %s to %s: %s', path, new_path, exc)
        info['title'] = new_title
        info['fulltitle'] = new_title
        info['filepath'] = current_path
        info['_filename'] = current_path
        for entry in info.get('requested_downloads') or []:
            entry['filepath'] = current_path
            entry['_filename'] = current_path
            if 'filename' in entry:
                entry['filename'] = os.path.basename(current_path)
        return current_path

    def _build_target_path(self, info: dict, title: str) -> str | None:
        info_for_template = dict(info)
        info_for_template['title'] = title
        info_for_template['fulltitle'] = title
        try:
            return self._downloader.prepare_filename(info_for_template)
        except Exception as exc:
            logging.warning('Could not compute filename for corrected title: %s', exc)
            path = info.get('filepath') or info.get('_filename')
            if not path:
                return None
            directory, _ = os.path.split(path)
            ext = info.get('ext') or os.path.splitext(path)[1].lstrip('.')
            sanitized = sanitize_filename(title, restricted=False)
            if not sanitized:
                return None
            return os.path.join(directory, f'{sanitized}.{ext}')
