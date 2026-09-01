import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import NamedTuple

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.Cache import databaseHelpers
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.tagger.Song.SoundcloudSong import SoundcloudSong

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# How a failed yt-dlp call is understood.
PERMANENT = 'permanent'  # the track is gone or encrypted: it will never arrive
RATE_LIMITED = 'rate_limited'  # SoundCloud is refusing us for now
TRANSIENT = 'transient'  # anything else: network hiccups, unexpected output

# The pause after a call. A successful fetch pays the full rate-limit pause; a
# track that SoundCloud answered instantly with "gone" is not worth a minute,
# because a pass over the archive is thousands of tracks long.
SUCCESS_PAUSE = 60
PERMANENT_PAUSE = 5
TRANSIENT_PAUSE = 60
RATE_LIMIT_PAUSE = 300
RATE_LIMIT_PAUSE_CAP = 3600

# Being refused this many times in a row means the source wants us gone, so the
# pass stops instead of walking the rest of the archive into the same wall.
MAX_CONSECUTIVE_RATE_LIMITS = 5

_PERMANENT_MARKERS = (
    'drm protected',
    'http error 404',
    'has been removed',
    'no longer available',
    'not available',
    'requires payment',
)
_RATE_LIMIT_MARKERS = (
    'http error 403',
    'http error 429',
    'forbidden',
    'too many requests',
    'rate limit',
)


class FetchResult(NamedTuple):
    """The metadata, or why it could not be had."""

    metadata: dict | None
    failure: str | None


@dataclass
class FetcherCounts:
    """What one pass over the archive did."""

    updated: int = 0
    skipped: int = 0
    not_found: int = 0
    permanent: int = 0
    rate_limited: int = 0
    transient: int = 0
    aborted: bool = False


def get_tracks_to_process():
    """Fetch all SoundCloud tracks from the archive."""
    try:
        conn = DatabaseConnector().connect()
        with conn.cursor() as cursor:
            # We fetch url and filename. Filename contains the local path.
            cursor.execute("SELECT id, url, filename FROM downloads_soundcloud_archive")
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Failed to fetch tracks from archive: {e}")
        return []


def classify_failure(stderr: str) -> str:
    """Read yt-dlp's complaint and decide what kind of failure it is."""
    message = (stderr or '').lower()
    if any(marker in message for marker in _PERMANENT_MARKERS):
        return PERMANENT
    if any(marker in message for marker in _RATE_LIMIT_MARKERS):
        return RATE_LIMITED
    return TRANSIENT


def pause_for(status: str | None, consecutive_rate_limits: int = 0) -> int:
    """How long to wait after a call that ended in `status`."""
    if status == PERMANENT:
        return PERMANENT_PAUSE
    if status == RATE_LIMITED:
        steps = max(0, consecutive_rate_limits - 1)
        return min(RATE_LIMIT_PAUSE * 2**steps, RATE_LIMIT_PAUSE_CAP)
    if status == TRANSIENT:
        return TRANSIENT_PAUSE
    return SUCCESS_PAUSE


def first_line(stderr: str) -> str:
    """The one line worth logging out of yt-dlp's multi-line grumbling."""
    for line in (stderr or '').splitlines():
        if line.startswith('ERROR'):
            return line.strip()
    return (stderr or '').strip().splitlines()[-1] if (stderr or '').strip() else 'no output'


def fetch_metadata(url) -> FetchResult:
    """Fetch metadata from SoundCloud using yt-dlp binary."""
    try:
        # Using the same approach as SoundcloudSongProcessor
        result = subprocess.run(
            ['yt-dlp', '--dump-single-json', '--no-playlist', url], capture_output=True, text=True, check=True
        )
        return FetchResult(json.loads(result.stdout), None)
    except subprocess.CalledProcessError as e:
        status = classify_failure(e.stderr)
        logging.warning(f"yt-dlp {status} failure for {url}: {first_line(e.stderr)}")
        return FetchResult(None, status)
    except Exception as e:
        logging.error(f"Unexpected error fetching metadata for {url}: {e}")
        return FetchResult(None, TRANSIENT)


def resolve_path(filename: str, track_id) -> str | None:
    """The playable path for this archive row, or None if the file is gone."""
    if filename and os.path.exists(filename):
        return filename
    if filename and filename.startswith('/mnt/music'):
        # The container mounts the library somewhere else than the row records.
        settings_path = Settings().music_folder_path
        if settings_path and settings_path != '/mnt/music':
            alternative_path = filename.replace('/mnt/music', settings_path, 1)
            if os.path.exists(alternative_path):
                logging.info(f"Found alternative path: {alternative_path}")
                return alternative_path
    logging.warning(f"File not found or path empty: {filename} (ID: {track_id})")
    return None


def process_tracks(
    tracks, genre_helper, fetch=fetch_metadata, sleep=time.sleep, song_factory=SoundcloudSong
) -> FetcherCounts:
    """Walk the archive, tagging what SoundCloud is still willing to describe."""
    counts = FetcherCounts()
    consecutive_rate_limits = 0

    for track_id, url, filename in tracks:
        path = resolve_path(filename, track_id)
        if not path:
            counts.not_found += 1
            continue

        logging.info(f"Processing: {url}")
        result = fetch(url)

        if result.failure:
            if result.failure == RATE_LIMITED:
                consecutive_rate_limits += 1
                counts.rate_limited += 1
                if consecutive_rate_limits >= MAX_CONSECUTIVE_RATE_LIMITS:
                    logging.error(f"SoundCloud refused {consecutive_rate_limits} calls in a row; stopping this pass.")
                    counts.aborted = True
                    break
            elif result.failure == PERMANENT:
                counts.permanent += 1
            else:
                counts.transient += 1
            sleep(pause_for(result.failure, consecutive_rate_limits))
            continue

        consecutive_rate_limits = 0
        metadata = result.metadata or {}

        # Respect SoundCloud's rate limits
        sleep(pause_for(None))

        sc_genre = metadata.get('genre')
        logging.info(f"Got genre: '{sc_genre}'")
        if not sc_genre:
            counts.skipped += 1
            continue

        # Normalize genre (SoundCloud often uses hashtags)
        if sc_genre.startswith('#'):
            sc_genre = sc_genre[1:]
            logging.info(f"Normalized to: '{sc_genre}'")

        # Check if the genre is allowed/validated. The helper answers with the
        # spelling `rules_genres` stores, so the library never gets 'uptempo'
        # next to 'Uptempo' just because two uploaders typed it differently.
        allowed_genre = genre_helper.get_corrected_or_exists(sc_genre)

        if not allowed_genre:
            logging.info(f"Not valid (not in rules_genres): '{sc_genre}'")
            counts.skipped += 1
            continue

        logging.info(f"Valid: '{allowed_genre}'")
        metadata['genre'] = allowed_genre
        try:
            song = song_factory(path, metadata)

            # Check if genre already exists in file to avoid redundant writes
            if allowed_genre in song.rules_genres():
                logging.info(f"Already exists: '{allowed_genre}'")
                counts.skipped += 1
                continue

            logging.info(f"Assigning: '{allowed_genre}'")
            song.parse()
            song.save_file()

            logging.info(f"Successfully updated: {os.path.basename(path)}")
            counts.updated += 1
        except Exception as e:
            logging.error(f"Failed to update {os.path.basename(path)}: {e}")
            counts.skipped += 1

    return counts


def main():
    logging.info("Starting SoundCloud genre fetcher...")

    tracks = get_tracks_to_process()
    if not tracks:
        logging.info("No tracks found in archive to process.")
        return

    logging.info(f"Found {len(tracks)} tracks to check.")

    # Get the genre helper from cache or create one
    genre_helper = databaseHelpers.get('rules_genres')
    if not genre_helper:
        logging.warning("Genre helper not found in cache, creating new instance.")
        genre_helper = FilterTableHelper('rules_genres', 'name', 'corrected_genre')

    counts = process_tracks(tracks, genre_helper)

    logging.info("--- Processing Finished ---")
    logging.info(f"Total tracks checked: {len(tracks)}")
    logging.info(f"Updated:             {counts.updated}")
    logging.info(f"Skipped/Unchanged:   {counts.skipped}")
    logging.info(f"Files not found:     {counts.not_found}")
    logging.info(f"Gone (404/DRM):      {counts.permanent}")
    logging.info(f"Refused (403/429):   {counts.rate_limited}")
    logging.info(f"Other failures:      {counts.transient}")
    if counts.aborted:
        logging.warning("Pass stopped early because SoundCloud kept refusing us.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
