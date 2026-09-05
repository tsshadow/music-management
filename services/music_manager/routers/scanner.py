import hashlib
import logging
import os
import threading
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query

from services.common.channels import (
    channel_from_path,
    is_label,
    normalize_channel_name,
    path_can_carry_a_label,
)
from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.GenreRulesHelper import BLACK, GenreRulesHelper
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.music_manager.database import get_db_connection
from services.scanner.Song.ReadonlySong import ReadonlySong
from services.tagger.Song.BaseSong import ExtensionNotSupportedException

router = APIRouter(tags=['scanner'])
logger = logging.getLogger('music-manager.scanner')


async def verify_api_key(x_api_key: str | None = Header(None)):
    """Same system-or-user API key check the other routers use.

    Delegates rather than re-implementing it (as library.py/management.py do) so there is one
    place where "what counts as a valid key" is defined. Imported lazily because users.py is
    itself a router module that main.py imports alongside this one.
    """
    from services.music_manager.routers.users import verify_api_key as _verify

    return await _verify(x_api_key)


class ScannerManager:
    def __init__(self):
        self.settings = Settings()
        self.music_path = self.settings.music_folder_path
        self._lock = threading.Lock()
        # Curation state is read, never written: the tagger owns adding genres via
        # record_unknown(). Preloading is deferred so constructing a ScannerManager
        # (including at import time) never needs a database.
        self.genre_helper = GenreRulesHelper(preload=False)

    def get_file_hash(self, path):
        return hashlib.sha256(path.encode('utf-8')).hexdigest()

    def scan_single(self, path: str | Path, force=False):
        with self._lock:
            logger.info('Processing single file scan request: %s', path)
            conn = get_db_connection()
            if not conn:
                logger.error('Could not get database connection')
                return False
            try:
                full_path = str(Path(path).resolve())
                if not os.path.exists(full_path):
                    logger.error(f'File not found for scanning: {full_path}')
                    return False
                result = self._process_file_safe(conn, full_path, force=force)
                return result
            finally:
                conn.close()

    def run_full(self, force=False):
        if not self.music_path or not os.path.exists(self.music_path):
            logger.error(f'Music path does not exist: {self.music_path}')
            return
        if self._lock.locked():
            logger.warning('Scan already in progress, skipping full run')
            return
        # A scan started after a curation decision must honour it, so the rules are
        # refreshed per full run rather than cached for the process lifetime.
        self.genre_helper.reload()
        with self._lock:
            logger.info(f'Starting scan of {self.music_path} (force={force})')
            conn = get_db_connection()
            if not conn:
                logger.error('Could not get database connection')
                return
            try:
                count = self._scan_recursive(conn, force)
                logger.info(f'Scan completed. Total files processed/updated: {count}')
            finally:
                conn.close()
        # Deliberately after the lock is released: an unreachable LMS must not keep the
        # next scan waiting. One trigger per run, not per file -- LMS's incremental scan
        # only reprocesses what actually changed.
        lms_scan_trigger.trigger()

    def _scan_recursive(self, conn, force):
        count = 0
        for root, _, files in os.walk(self.music_path):
            for file in files:
                if file.startswith('.'):
                    continue
                full_path = os.path.join(root, file)
                if self._process_file_safe(conn, full_path, force):
                    count += 1
                    if count % 100 == 0:
                        logger.info(f'Processed {count} files...')
        return count

    def _process_file_safe(self, conn, full_path, force):
        try:
            return self.process_file(conn, full_path, force)
        except ExtensionNotSupportedException:
            pass
        except Exception as e:
            logger.error(f'Error processing {full_path}: {e}')
        return False

    def _resolve_genre_ids(self, song):
        """Map a file's genre tags onto rules_genres ids.

        White genres index under their curated name, so 'uptempo' lands on
        'Uptempo Hardcore'. Black genres are dropped. Unknown genres index under
        their raw name -- they are in the file and LMS shows them, so hiding them
        would leave tracks looking genre-less. An expansion ('Upterror') yields
        several targets. Order is preserved and duplicates removed.
        """
        genre_ids = []
        for raw in song.rules_genres() or []:
            if not raw:
                continue
            for part in self.genre_helper.split_composite(raw):
                decision = self.genre_helper.resolve(part)
                if decision.state == BLACK:
                    continue
                for value in decision.values:
                    row = self.genre_helper.get_row(value)
                    if row is not None and row.id not in genre_ids:
                        genre_ids.append(row.id)
        return genre_ids

    def _write_genres(self, cursor, track_id, genre_ids):
        """Replace the track's genre rows, mirroring how library_track_artists is written."""
        cursor.execute('DELETE FROM library_track_genres WHERE track_id = %s', (track_id,))
        for genre_id in genre_ids:
            cursor.execute(
                'INSERT IGNORE INTO library_track_genres (track_id, genre_id) VALUES (%s, %s)', (track_id, genre_id)
            )

    def _resolve_channel_id(self, cursor, path):
        """The channel this file arrived through, created on first sight, or None.

        Read from the path rather than from a tag: the path is what the downloader wrote, so this
        is correct for every file already on disk without retagging any of them. A channel starts
        out pointing at neither a label nor an artist -- deciding which it is belongs to a person,
        not to a scan.
        """
        found = channel_from_path(path, self.music_path)
        if not found:
            return None
        platform, name = found
        normalized = normalize_channel_name(name)
        if not normalized:
            return None
        cursor.execute(
            'INSERT IGNORE INTO channels (platform, name, normalized_name) VALUES (%s, %s, %s)',
            (platform, name, normalized),
        )
        cursor.execute('SELECT id FROM channels WHERE platform = %s AND normalized_name = %s', (platform, normalized))
        row = cursor.fetchone()
        return row['id'] if row else None

    def process_file(self, conn, path, force=False):
        path_hash = self.get_file_hash(path)
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, file_mtime, file_size FROM library_media_files WHERE file_path_hash = %s', (path_hash,)
            )
            record = cursor.fetchone()
            if not force and record and (record['file_mtime'] == mtime) and (record['file_size'] == size):
                return False
            try:
                song = ReadonlySong(path)
            except Exception:
                return False
            artist_names = song.library_artists()
            artist_ids = []
            for name in artist_names:
                if not name:
                    continue
                cursor.execute('INSERT IGNORE INTO library_artists (name) VALUES (%s)', (name,))
                cursor.execute('SELECT id FROM library_artists WHERE name = %s', (name,))
                artist_ids.append(cursor.fetchone()['id'])
            # A publisher is only stored as a label when it actually names one. SoundCloud, YouTube
            # and Telegram arrive in this same tag and are platforms, not labels; `__TODO` and
            # `__Free&none` are placeholders. Storing those made them the three largest "labels" in
            # the collection. See services/common/channels.py.
            label_name = song.publisher()
            label_id = None
            if label_name and is_label(label_name) and path_can_carry_a_label(path, self.music_path):
                cursor.execute('INSERT IGNORE INTO library_labels (name) VALUES (%s)', (label_name,))
                cursor.execute('SELECT id FROM library_labels WHERE name = %s', (label_name,))
                label_id = cursor.fetchone()['id']
            channel_id = self._resolve_channel_id(cursor, path)
            title = song.title()
            duration = song.length()
            primary_artist_id = artist_ids[0] if artist_ids else None
            display_artist = song.original_artist()
            track_uid = hashlib.sha256(f'{title}-{duration}-{primary_artist_id}'.encode()).hexdigest()
            cursor.execute(
                '\n                INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id, display_artist)\n                VALUES (%s, %s, %s, %s, %s)\n                ON DUPLICATE KEY UPDATE title=%s, duration_secs=%s, primary_artist_id=%s,\n                    display_artist=COALESCE(%s, display_artist)\n            ',
                (
                    track_uid,
                    title,
                    duration,
                    primary_artist_id,
                    display_artist,
                    title,
                    duration,
                    primary_artist_id,
                    display_artist,
                ),
            )
            cursor.execute('SELECT id FROM library_tracks WHERE track_uid = %s', (track_uid,))
            track_id = cursor.fetchone()['id']
            cursor.execute('DELETE FROM library_track_artists WHERE track_id = %s', (track_id,))
            for i, a_id in enumerate(artist_ids):
                role = 'primary' if i == 0 else 'featuring'
                cursor.execute(
                    'INSERT IGNORE INTO library_track_artists (track_id, artist_id, role, position) VALUES (%s, %s, %s, %s)',
                    (track_id, a_id, role, i),
                )
            self._write_genres(cursor, track_id, self._resolve_genre_ids(song))
            if label_id:
                cursor.execute(
                    'INSERT IGNORE INTO library_track_labels (track_id, label_id) VALUES (%s, %s)', (track_id, label_id)
                )
            if channel_id:
                cursor.execute(
                    'INSERT IGNORE INTO library_track_channels (track_id, channel_id) VALUES (%s, %s)',
                    (track_id, channel_id),
                )
            cursor.execute(
                '\n                INSERT INTO library_media_files (file_path, file_path_hash, file_mtime, file_size, track_id, duration_secs)\n                VALUES (%s, %s, %s, %s, %s, %s)\n                ON DUPLICATE KEY UPDATE file_mtime=%s, file_size=%s, track_id=%s, duration_secs=%s\n            ',
                (path, path_hash, mtime, size, track_id, duration, mtime, size, track_id, duration),
            )
            return True


scanner_manager = ScannerManager()


@router.get('/health')
async def health():
    return {'status': 'OK', 'busy': scanner_manager._lock.locked()}


@router.post('/scan/all')
async def api_scan_all(background_tasks: BackgroundTasks, force: bool = False, _auth: dict = Depends(verify_api_key)):
    if scanner_manager._lock.locked():
        raise HTTPException(status_code=409, detail='A scan operation is already in progress')
    background_tasks.add_task(scanner_manager.run_full, force=force)
    return {'message': 'Full library scan started in background'}


@router.post('/scan/file')
async def api_scan_file(path: str = Query(...), force: bool = False, _auth: dict = Depends(verify_api_key)):
    scanner_manager.scan_single(path, force=force)
    return {'message': f'Scan for {path} completed'}


def run_scanner_loop(sleeptime: int = 3600):
    logger.info('Starting background scanner loop with sleeptime %d', sleeptime)
    scanner_manager.run_full()
    while True:
        time.sleep(sleeptime)
        scanner_manager.run_full()
