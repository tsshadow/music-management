import hashlib
import logging
import os
import threading
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
from services.music_manager.rbac import require_admin
from services.music_manager.thread_registry import default_stale_after, run_forever
from services.music_manager.track_relink import relink_orphaned_tracks, relink_track, track_has_media_file
from services.scanner.Song.ReadonlySong import ReadonlySong
from services.tagger.Song.BaseSong import ExtensionNotSupportedException

router = APIRouter(tags=['scanner'])
logger = logging.getLogger('music-manager.scanner')


def verify_api_key(x_api_key: str | None = Header(None)):
    """Same system-or-user API key check the other routers use.

    Delegates rather than re-implementing it (as library.py/management.py do) so there is one
    place where "what counts as a valid key" is defined. Imported lazily because users.py is
    itself a router module that main.py imports alongside this one.
    """
    from services.music_manager.routers.users import verify_api_key as _verify

    return _verify(x_api_key)


class ScannerManager:
    #: How long a single-file scan waits for a running full scan before giving up. Kept
    #: under the 10 s the tagger's announce() gives the request: a full scan holds the
    #: lock for hours, and every announce that waited for it kept its thread-pool thread
    #: for that whole time. Forty of those and the sync endpoints -- /health included --
    #: never got a thread again until the scan ended (prod, 2026-09-19). The skipped file
    #: is not lost: its mtime changed, so the next full scan reads it anyway.
    SINGLE_SCAN_LOCK_TIMEOUT = float(os.getenv('SCANNER_SINGLE_LOCK_TIMEOUT', '5'))

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
        """Scan one file into the library tables; False when it could not be done right now.

        The lock comes first and the rules second. The reload is a query, and it used to
        run before the lock was even tried: while a full scan held the lock, every single
        scan paid for a reload whose result it then threw away when it gave up.
        """
        if not self._lock.acquire(timeout=self.SINGLE_SCAN_LOCK_TIMEOUT):
            logger.info('Full scan in progress, %s waits for the next scanner round', path)
            return False
        try:
            # Without this the curation rules are still empty on a process that has never run a
            # full scan, and process_file writes that emptiness: _write_genres deletes the
            # track's rows before inserting the nothing it resolved. Rescanning one track from
            # the UI or from LMS therefore used to strip its genres.
            #
            # A full reload rather than a load-once: curation decisions refresh the helpers in
            # the Cache registry (see curation_rules.refresh), never this instance, so a cached
            # map here would stay stale for the process lifetime. One query per user-triggered
            # single scan is the cheaper mistake.
            self.genre_helper.reload()
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
        finally:
            self._lock.release()

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
        for root, dirs, files in os.walk(self.music_path):
            # Hidden directories are not library content. The one that matters is
            # `.quarantine`: when no quarantine folder is configured it lands beside the
            # music root, and the pipeline parks duplicates and unreadable files there.
            # Walking it would index exactly the files the importer decided not to keep,
            # so a duplicate release would come straight back as library tracks. Synology
            # writes `@eaDir` thumbnail folders through the same tree; the tagger already
            # prunes those and this walk had no reason to read them either.
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '@eaDir']
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
        """Replace the track's genre rows, mirroring how library_track_artists is written.

        Unless the rules never loaded. `GenreRulesHelper._preload` logs a failed query and
        leaves an empty map behind, which resolves every genre to nothing -- and this
        method deletes first, so one unreachable database would strip the genre links of
        every file the scan touches. With no rules there is nothing this could correctly
        write, so it leaves the existing rows alone.
        """
        if not self.genre_helper.is_loaded():
            logger.warning('Curation rules unavailable, leaving the genres of track %s untouched', track_id)
            return
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

    def _resolve_label_id(self, cursor, song, path):
        """The label this file names, created on first sight, or None.

        A publisher is only stored as a label when it actually names one. SoundCloud, YouTube and
        Telegram arrive in this same tag and are platforms, not labels; `__TODO` and `__Free&none`
        are placeholders. Storing those made them the three largest "labels" in the collection.
        See services/common/channels.py.
        """
        label_name = song.publisher()
        if not (label_name and is_label(label_name) and path_can_carry_a_label(path, self.music_path)):
            return None
        cursor.execute('INSERT IGNORE INTO library_labels (name) VALUES (%s)', (label_name,))
        cursor.execute('SELECT id FROM library_labels WHERE name = %s', (label_name,))
        row = cursor.fetchone()
        return row['id'] if row else None

    def _write_links(self, cursor, track_id, path_hash, label_id=None, channel_id=None):
        """Replace the track's label and channel links with what its files say today.

        Used to be INSERT IGNORE only, so a corrected publisher kept its old label link for good.
        A track can own several files -- the FLAC and the MP3 of one release -- so the set is
        recomputed from every one of them: `label_id`/`channel_id` are what the file being
        scanned (`path_hash`) says, and the track's other files are read here. A file that is
        gone from disk supports nothing; a file that is there but cannot be read might still
        carry a label, so then the label links are only added to, never removed.
        """
        label_ids = {label_id} - {None}
        channel_ids = {channel_id} - {None}
        labels_known = True
        cursor.execute(
            'SELECT file_path FROM library_media_files WHERE track_id = %s AND file_path_hash <> %s',
            (track_id, path_hash or ''),
        )
        for row in cursor.fetchall():
            other = row['file_path']
            if not other or not os.path.exists(other):
                continue
            other_channel = self._resolve_channel_id(cursor, other)
            if other_channel:
                channel_ids.add(other_channel)
            try:
                other_label = self._resolve_label_id(cursor, ReadonlySong(other), other)
            except Exception:
                labels_known = False
                continue
            if other_label:
                label_ids.add(other_label)
        if labels_known:
            cursor.execute('DELETE FROM library_track_labels WHERE track_id = %s', (track_id,))
        for lid in sorted(label_ids):
            cursor.execute(
                'INSERT IGNORE INTO library_track_labels (track_id, label_id) VALUES (%s, %s)', (track_id, lid)
            )
        cursor.execute('DELETE FROM library_track_channels WHERE track_id = %s', (track_id,))
        for cid in sorted(channel_ids):
            cursor.execute(
                'INSERT IGNORE INTO library_track_channels (track_id, channel_id) VALUES (%s, %s)', (track_id, cid)
            )

    def _settle_previous_track(self, cursor, previous_track_id, track_id, path_hash):
        """Deal with the track a file just left: relink it away, or refresh what it still has.

        When the file was its last one, the old row is merged into the new one (ratings, listens,
        works) and deleted -- see track_relink.py. Otherwise it stays a track of its own, but the
        label and channel links the departed file contributed are recomputed away.
        """
        if track_has_media_file(cursor, previous_track_id):
            self._write_links(cursor, previous_track_id, path_hash)
            return None
        counts = relink_track(cursor, previous_track_id, track_id)
        # INFO -- and so an event -- only when a user's data actually moved; a retag of a
        # track nobody rated or played would otherwise put one row per file in the event log.
        if counts and (counts['ratings_moved'] or counts['ratings_merged'] or counts['listens_moved']):
            logger.info('Relinked track %s to %s: %s', previous_track_id, track_id, counts)
        elif counts:
            logger.debug('Relinked track %s to %s: %s', previous_track_id, track_id, counts)
        return counts

    def process_file(self, conn, path, force=False):
        path_hash = self.get_file_hash(path)
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, file_mtime, file_size, track_id FROM library_media_files WHERE file_path_hash = %s',
                (path_hash,),
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
            label_id = self._resolve_label_id(cursor, song, path)
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
            self._write_links(cursor, track_id, path_hash, label_id, channel_id)
            # A retag that changed the title or the primary artist gives the file a new track_uid
            # and so a new track row. Repointing the file and relinking the row it left are one
            # change: the pool runs autocommit, so without an explicit transaction a failure
            # half-way would leave ratings split between two rows.
            previous_track_id = record.get('track_id') if record else None
            moving = previous_track_id is not None and previous_track_id != track_id
            if moving:
                conn.begin()
            try:
                cursor.execute(
                    '\n                INSERT INTO library_media_files (file_path, file_path_hash, file_mtime, file_size, track_id, duration_secs)\n                VALUES (%s, %s, %s, %s, %s, %s)\n                ON DUPLICATE KEY UPDATE file_mtime=%s, file_size=%s, track_id=%s, duration_secs=%s\n            ',
                    (path, path_hash, mtime, size, track_id, duration, mtime, size, track_id, duration),
                )
                if moving:
                    self._settle_previous_track(cursor, previous_track_id, track_id, path_hash)
                    conn.commit()
            except Exception:
                if moving:
                    conn.rollback()
                raise
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
def api_scan_file(path: str = Query(...), force: bool = False, _auth: dict = Depends(verify_api_key)):
    # Plain `def`, so FastAPI runs it in the thread pool: the scan reads the file and writes
    # rows, and the workers call this for every file they tag -- an `async def` here parked
    # the whole event loop for the duration of each one.
    scanned = scanner_manager.scan_single(path, force=force)
    return {'message': f'Scan for {path} completed', 'scanned': bool(scanned)}


#: The last orphan relink, for GET /relink-orphans: None until one has run in this process.
relink_state: dict = {'running': False, 'last': None}


def run_orphan_relink():
    """Background body of POST /relink-orphans: relink every orphaned track, then report it.

    Holds the scanner lock so no scan repoints a file underneath it, and records its totals as an
    INFO event -- that, and GET /relink-orphans, is where an administrator reads the outcome.
    """
    if not scanner_manager._lock.acquire(blocking=False):
        logger.warning('A scan is running, orphan relink skipped')
        relink_state['running'] = False
        return None
    try:
        conn = get_db_connection()
        if not conn:
            logger.error('Could not get database connection')
            return None
        try:
            totals = relink_orphaned_tracks(conn)
        finally:
            conn.close()
    finally:
        scanner_manager._lock.release()
        relink_state['running'] = False
    relink_state['last'] = totals
    try:
        from services.common.Helpers.EventService import event_service

        event_service.emit(
            level='INFO',
            title='Orphaned tracks relinked',
            message=(
                f"{totals['relinked']} of {totals['orphans']} fileless tracks relinked, "
                f"{totals['unmatched']} without a single successor, {totals['failed']} failed. "
                f"Ratings moved {totals['ratings_moved']}, merged {totals['ratings_merged']}; "
                f"listens moved {totals['listens_moved']}, duplicates dropped {totals['listens_dropped']}."
            ),
            source='music-manager',
            logger=logger.name,
            context=totals,
        )
    except Exception as exc:
        logger.warning('Could not record the orphan relink event: %s', exc)
    return totals


@router.post('/relink-orphans')
def api_relink_orphans(background_tasks: BackgroundTasks, _auth: dict = Depends(require_admin())):
    """Start the one-off repair for track rows a retag left without a file (bug report 042).

    Admin only: it deletes track rows. Runs in the background; the totals arrive as an INFO event
    and on GET /relink-orphans. The previous run's totals, if any, come back straight away.
    """
    if relink_state['running'] or scanner_manager._lock.locked():
        raise HTTPException(status_code=409, detail='A scan or relink is already in progress')
    relink_state['running'] = True
    background_tasks.add_task(run_orphan_relink)
    return {'message': 'Orphaned track relink started in background', 'last': relink_state['last']}


@router.get('/relink-orphans')
def api_relink_orphans_status(_auth: dict = Depends(require_admin())):
    """Whether an orphan relink is running, and the totals of the last one in this process."""
    return {'running': relink_state['running'], 'last': relink_state['last']}


# A full scan over the CIFS share can run for hours on a first pass or after a forced rescan;
# half a day without a completed scan is stuck, whatever the interval.
SCANNER_STALE_AFTER_SECONDS = 12 * 3600


def _scanner_tick() -> None:
    """One full scan; its return value is not a sleep override, so it is dropped here."""
    scanner_manager.run_full()


def run_scanner_loop(sleeptime: int = 3600):
    """The `scanner` thread: a full scan on start, then one every `sleeptime` seconds, for good.

    Runs through thread_registry.run_forever, so a scan that raises is logged and retried
    instead of ending the loop.
    """
    logger.info('Starting background scanner loop with sleeptime %d', sleeptime)
    run_forever(
        'scanner',
        _scanner_tick,
        sleeptime,
        stale_after=max(SCANNER_STALE_AFTER_SECONDS, default_stale_after(sleeptime)),
    )
