import hashlib
import logging
import os
import threading
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from services.common.channels import (
    channel_from_path,
    is_label,
    normalize_channel_name,
    path_can_carry_a_label,
)
from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.FestivalHelper import FestivalHelper
from services.common.Helpers.GenreRulesHelper import BLACK, GenreRulesHelper
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.PodcastHelper import PodcastHelper
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.common.track_form import classify
from services.music_manager.database import get_db_connection, transaction
from services.music_manager.orphan_purge import purge_orphaned_tracks
from services.music_manager.rbac import require_admin
from services.music_manager.routers.users import verify_api_key
from services.music_manager.thread_registry import default_stale_after, run_forever
from services.music_manager.track_relink import (
    RELINK_KEYS,
    relink_orphaned_tracks,
    relink_track,
    track_has_media_file,
)
from services.scanner.Song.ReadonlySong import ReadonlySong
from services.tagger.Song.BaseSong import ExtensionNotSupportedException

router = APIRouter(tags=['scanner'])
logger = logging.getLogger('music-manager.scanner')

#: Character lengths of the columns process_file writes a tag value into (db_init.py).
#: MariaDB counts VARCHAR length in characters -- code points under utf8mb4 -- and so does
#: Python's str slicing, so a slice to this length can never split a character.
TITLE_MAX_CHARS = 512
DISPLAY_ARTIST_MAX_CHARS = 512
NAME_MAX_CHARS = 255

#: Why the scanner hands a file back to the tagger when one of its values did not fit.
OVERLONG_TAG_REASON = 'overlong_tag'

#: Failed scans in a row, of one unchanged file, after which the scanner parks it until the
#: file changes. Without this a file that fails fails again on every full pass, forever: one
#: error per file per hour in the event log (bug report 117).
SCANNER_PARK_AFTER = 3


def fit_column(value, max_chars):
    """`value` cut to at most `max_chars` characters; None and short values pass unchanged.

    A value the column cannot hold used to fail the whole file with MariaDB error 1406, and
    because the file then had no row the next full scan read it again, and the next -- 10 to
    30 errors per file per 12 h on production (bug report 117). Cutting at the write boundary
    keeps the rest of the file's data; the full value stays in the file itself.
    """
    if value is None or len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip()


def request_retag(path):
    """Put `path` back on the tagger queue: its tags carry a value too long to index.

    On production every such file was an m4a whose title had been multiplied by a since-fixed
    tagger defect (bug report 117); the tagger's CollapseRepeatedValuesRule repairs it, and the
    tagger's own write makes the next scan read the file again. Best effort: failing to queue
    must not fail the scan that already stored the file.
    """
    try:
        ProcessedFilesHelper().mark_for_rescan(path, reason=OVERLONG_TAG_REASON)
    except Exception as exc:
        logger.warning('Could not queue %s for a retag: %s', path, exc)


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
        # The festival and podcast lists the form of a file is read against (see
        # services/common/track_form.py). Loaded with the genre rules, for the same reason.
        self.festival_helper = FestivalHelper(preload=False)
        self.podcast_helper = PodcastHelper(preload=False)
        # path -> (mtime, size, failures in a row) for files whose scan raised. In memory on
        # purpose: a restart (every deploy) gives each parked file one more try, which is the
        # moment a code fix for its failure arrives, and no schema is needed for it.
        self._failures: dict[str, tuple[float, int, int]] = {}

    def _reload_rules(self):
        """Re-read the genre, festival and podcast rules this scan resolves against.

        The festival and podcast lists only decide a file's form and performance date; a failure
        to load them leaves them empty (both helpers log it), which classifies a long download as
        a plain set until the hourly pass in track_form_sync corrects it.
        """
        self.genre_helper.reload()
        self.festival_helper.reload()
        self.podcast_helper.reload()

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
            self._reload_rules()
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
        self._reload_rules()
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

    @staticmethod
    def _file_version(full_path):
        """(mtime, size) of a file, or None when it cannot be stat'ed."""
        try:
            stat = os.stat(full_path)
        except OSError:
            return None
        return stat.st_mtime, stat.st_size

    def _is_parked(self, full_path, version) -> bool:
        """Whether this exact version of the file already failed SCANNER_PARK_AFTER times."""
        failure = self._failures.get(full_path)
        if not failure or version is None:
            return False
        mtime, size, count = failure
        if (mtime, size) != version:
            # The file changed -- a retag, a redownload -- so it gets a fresh start.
            del self._failures[full_path]
            return False
        return count >= SCANNER_PARK_AFTER

    def _record_failure(self, full_path, version, error) -> None:
        """Count a failed scan; log it, or -- on the one that parks the file -- say so instead."""
        previous = self._failures.get(full_path)
        count = 1
        if previous and version is not None and previous[:2] == version:
            count = previous[2] + 1
        if version is not None:
            self._failures[full_path] = (version[0], version[1], count)
        if count >= SCANNER_PARK_AFTER:
            logger.warning(
                'Parked %s after %d failed scans in a row (last: %s); it is scanned again when the '
                'file changes or the service restarts',
                full_path,
                count,
                error,
            )
        else:
            logger.error(f'Error processing {full_path}: {error}')

    def _process_file_safe(self, conn, full_path, force):
        """Scan one file without letting its failure end the walk; park a file that keeps failing.

        A forced scan ignores the parking, as it ignores the up-to-date check.
        """
        version = self._file_version(full_path)
        if not force and self._is_parked(full_path, version):
            return False
        try:
            result = self.process_file(conn, full_path, force)
        except ExtensionNotSupportedException:
            return False
        except Exception as e:
            self._record_failure(full_path, version, e)
            return False
        self._failures.pop(full_path, None)
        return result

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
        # INSERT IGNORE would store a longer name cut short, and the SELECT by the full name
        # below would then find nothing; cutting it here keeps the two statements agreeing.
        label_name = fit_column(label_name, NAME_MAX_CHARS)
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

    @staticmethod
    def _is_up_to_date(record, mtime, size) -> bool:
        """Whether a file's row still describes it, so reading its tags again would change nothing.

        An unchanged mtime and size used to be enough. A row without a length is not up to date
        whatever the file's mtime says: an early scan in May 2026 stored ~39,000 files with the
        file name as title and no length, and because their files never changed, no later walk
        read them again -- so the hourly form pass could never classify them (bug report 093).
        A length is the one thing every readable audio file has, so its absence marks a row the
        scanner has to redo; once written, the file drops back onto the fast path.
        """
        if not record:
            return False
        if not record.get('duration_secs'):
            return False
        return record['file_mtime'] == mtime and record['file_size'] == size

    def process_file(self, conn, path, force=False):
        path_hash = self.get_file_hash(path)
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, file_mtime, file_size, track_id, duration_secs FROM library_media_files '
                'WHERE file_path_hash = %s',
                (path_hash,),
            )
            record = cursor.fetchone()
            if not force and self._is_up_to_date(record, mtime, size):
                return False
            try:
                song = ReadonlySong(path)
            except Exception:
                return False
            artist_names = song.library_artists()
            artist_ids = []
            overlong = []
            for name in artist_names:
                if not name:
                    continue
                if len(name) > NAME_MAX_CHARS:
                    overlong.append('artist')
                    name = fit_column(name, NAME_MAX_CHARS)
                # Recording the name is not approving it. A name new to the library enters
                # the artist curation queue as pending: the tagger's artist rules match
                # only approved or grandfathered names (TrustedArtistHelper), so a name a
                # rule guessed out of a title cannot confirm itself on the next file. The
                # file keeps its tag and the track is linked to the name as before.
                cursor.execute('INSERT IGNORE INTO library_artists (name) VALUES (%s)', (name,))
                cursor.execute('SELECT id FROM library_artists WHERE name = %s', (name,))
                artist_ids.append(cursor.fetchone()['id'])
            label_id = self._resolve_label_id(cursor, song, path)
            channel_id = self._resolve_channel_id(cursor, path)
            title = song.title()
            duration = song.length()
            primary_artist_id = artist_ids[0] if artist_ids else None
            display_artist = song.original_artist()
            if title and len(title) > TITLE_MAX_CHARS:
                overlong.append('title')
                title = fit_column(title, TITLE_MAX_CHARS)
            if display_artist and len(display_artist) > DISPLAY_ARTIST_MAX_CHARS:
                overlong.append('display_artist')
                display_artist = fit_column(display_artist, DISPLAY_ARTIST_MAX_CHARS)
            if overlong:
                # Once per scan of the file, and only until the retag has shortened it.
                logger.warning('Cut %s of %s to fit the database; queued it for a retag', ', '.join(overlong), path)
                request_retag(path)
            track_uid = hashlib.sha256(f'{title}-{duration}-{primary_artist_id}'.encode()).hexdigest()
            # What the file is and, for a live set, when it was played -- from the same path,
            # title and duration the hourly pass (track_form_sync) reads, so the two agree.
            form, performance_date = classify(
                path, self.music_path, duration, title, self.festival_helper, self.podcast_helper
            )
            cursor.execute(
                '\n                INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id, display_artist,\n                    form, performance_date)\n                VALUES (%s, %s, %s, %s, %s, %s, %s)\n                ON DUPLICATE KEY UPDATE title=%s, duration_secs=%s, primary_artist_id=%s,\n                    display_artist=COALESCE(%s, display_artist), form=%s, performance_date=%s\n            ',
                (
                    track_uid,
                    title,
                    duration,
                    primary_artist_id,
                    display_artist,
                    form,
                    performance_date,
                    title,
                    duration,
                    primary_artist_id,
                    display_artist,
                    form,
                    performance_date,
                ),
            )
            cursor.execute('SELECT id FROM library_tracks WHERE track_uid = %s', (track_uid,))
            track_id = cursor.fetchone()['id']
            genre_ids = self._resolve_genre_ids(song)
            # A retag that changed the title or the primary artist gives the file a new track_uid
            # and so a new track row; the row it left is relinked below.
            previous_track_id = record.get('track_id') if record else None
            moving = previous_track_id is not None and previous_track_id != track_id
            # One transaction for everything that deletes and rewrites: the artist, genre, label
            # and channel links, the file row and the relink. The pool runs autocommit, so without
            # it a failure between a DELETE and its INSERTs leaves the track with no links at all,
            # and a failed relink leaves ratings split between two rows.
            with transaction(conn):
                cursor.execute('DELETE FROM library_track_artists WHERE track_id = %s', (track_id,))
                for i, a_id in enumerate(artist_ids):
                    role = 'primary' if i == 0 else 'featuring'
                    cursor.execute(
                        'INSERT IGNORE INTO library_track_artists (track_id, artist_id, role, position) VALUES (%s, %s, %s, %s)',
                        (track_id, a_id, role, i),
                    )
                self._write_genres(cursor, track_id, genre_ids)
                self._write_links(cursor, track_id, path_hash, label_id, channel_id)
                cursor.execute(
                    '\n                INSERT INTO library_media_files (file_path, file_path_hash, file_mtime, file_size, track_id, duration_secs)\n                VALUES (%s, %s, %s, %s, %s, %s)\n                ON DUPLICATE KEY UPDATE file_mtime=%s, file_size=%s, track_id=%s, duration_secs=%s\n            ',
                    (path, path_hash, mtime, size, track_id, duration, mtime, size, track_id, duration),
                )
                if moving:
                    self._settle_previous_track(cursor, previous_track_id, track_id, path_hash)
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
#: `progress` is the running totals of the run in flight, filled in place.
relink_state: dict = {'running': False, 'last': None, 'progress': None}

#: The same for the orphan purge (POST/GET /purge-orphans).
purge_state: dict = {'running': False, 'last': None, 'progress': None}


def _emit_orphan_event(title: str, message: str, context: dict) -> None:
    """Record one INFO event for an orphan relink or purge; a failure to record is only logged."""
    try:
        from services.common.Helpers.EventService import event_service

        event_service.emit(
            level='INFO',
            title=title,
            message=message,
            source='music-manager',
            logger=logger.name,
            context=context,
        )
    except Exception as exc:
        logger.warning('Could not record the %s event: %s', title.lower(), exc)


def _run_locked(state: dict, work):
    """Run `work(conn)` holding the scanner lock, so no scan repoints a file underneath it.

    Returns its result, or None when a scan held the lock or no connection could be had. Clears
    `state['running']` whatever happens.
    """
    if not scanner_manager._lock.acquire(blocking=False):
        logger.warning('A scan is running, orphan repair skipped')
        state['running'] = False
        return None
    try:
        conn = get_db_connection()
        if not conn:
            logger.error('Could not get database connection')
            return None
        try:
            return work(conn)
        finally:
            conn.close()
    finally:
        scanner_manager._lock.release()
        state['running'] = False


def run_orphan_relink(dry_run: bool = False):
    """Background body of POST /relink-orphans: relink every orphaned track, then report it.

    Holds the scanner lock, and records its totals as an INFO event -- that, and GET
    /relink-orphans, is where an administrator reads the outcome. A dry run is reported on GET
    only: it changed nothing, so it has no place in the event log.
    """
    progress: dict = {}
    relink_state['progress'] = progress
    totals = _run_locked(relink_state, lambda conn: relink_orphaned_tracks(conn, dry_run=dry_run, totals=progress))
    relink_state['progress'] = None
    if totals is None:
        return None
    totals['finished_at'] = time.time()
    relink_state['last'] = totals
    if dry_run:
        return totals
    _emit_orphan_event(
        'Orphaned tracks relinked',
        f"{totals['relinked']} of {totals['orphans']} fileless tracks relinked "
        f"({totals['relinked_metadata']} on metadata, {totals['relinked_file_name']} on file name), "
        f"{totals['unmatched']} without a single successor "
        f"({totals['ambiguous_file_name']} of them named like several files), {totals['failed']} failed. "
        f"Ratings moved {totals['ratings_moved']}, merged {totals['ratings_merged']}; "
        f"listens moved {totals['listens_moved']}, duplicates dropped {totals['listens_dropped']}.",
        totals,
    )
    return totals


def run_orphan_purge(dry_run: bool = False):
    """Background body of POST /purge-orphans: delete the unreferenced orphans, then report it."""
    progress: dict = {}
    purge_state['progress'] = progress
    totals = _run_locked(purge_state, lambda conn: purge_orphaned_tracks(conn, dry_run=dry_run, totals=progress))
    purge_state['progress'] = None
    if totals is None:
        return None
    totals['finished_at'] = time.time()
    purge_state['last'] = totals
    if dry_run:
        return totals
    _emit_orphan_event(
        'Orphaned tracks purged',
        f"{totals['purged']} of {totals['orphans']} fileless tracks deleted; {totals['kept']} kept because a "
        f"user made something that points at them (listens {totals['kept_listens']}, ratings "
        f"{totals['kept_ratings']}, pins {totals['kept_pinned']}, reviewed ml labels "
        f"{totals['kept_reviewed_labels']}). {totals['skipped_changed']} changed since the survey and were "
        f"left, {totals['failed_batches']} batches failed.",
        {key: value for key, value in totals.items() if key != 'kept_list'},
    )
    return totals


def _refuse_if_busy() -> None:
    """409 while a scan, a relink or a purge holds the library."""
    if relink_state['running'] or purge_state['running'] or scanner_manager._lock.locked():
        raise HTTPException(status_code=409, detail='A scan, relink or purge is already in progress')


@router.post('/relink-orphans')
def api_relink_orphans(
    background_tasks: BackgroundTasks, dry_run: bool = False, _auth: dict = Depends(require_admin())
):
    """Start the repair for track rows a retag left without a file (bug reports 042 and 104).

    Admin only: it deletes track rows. Runs in the background; the totals arrive as an INFO event
    and on GET /relink-orphans. The previous run's totals, if any, come back straight away. With
    `dry_run=1` it counts what each key would relink and writes nothing.
    """
    _refuse_if_busy()
    relink_state['running'] = True
    background_tasks.add_task(run_orphan_relink, dry_run)
    return {'message': 'Orphaned track relink started in background', 'dry_run': dry_run, 'last': relink_state['last']}


@router.get('/relink-orphans')
def api_relink_orphans_status(_auth: dict = Depends(require_admin())):
    """Whether an orphan relink is running, its progress, and the totals of the last one in this process.

    `keys` names the match keys this build tries, so a caller can tell it from a build without the
    file-name key even before any run has happened.
    """
    return {
        'running': relink_state['running'],
        'keys': list(RELINK_KEYS),
        'dry_run_supported': True,
        'progress': relink_state['progress'],
        'last': relink_state['last'],
    }


@router.post('/purge-orphans')
def api_purge_orphans(background_tasks: BackgroundTasks, dry_run: bool = False, _auth: dict = Depends(require_admin())):
    """Start deleting fileless track rows nothing a user made refers to (bug report 104).

    Admin only. Meant to run after POST /relink-orphans. Runs in the background; the totals arrive
    as an INFO event and on GET /purge-orphans, which also lists the kept orphans. With
    `dry_run=1` it counts and lists, and writes nothing.
    """
    _refuse_if_busy()
    purge_state['running'] = True
    background_tasks.add_task(run_orphan_purge, dry_run)
    return {'message': 'Orphaned track purge started in background', 'dry_run': dry_run, 'last': purge_state['last']}


@router.get('/purge-orphans')
def api_purge_orphans_status(_auth: dict = Depends(require_admin())):
    """Whether an orphan purge is running, its progress, and the totals of the last one in this process."""
    return {'running': purge_state['running'], 'progress': purge_state['progress'], 'last': purge_state['last']}


# A full scan over the CIFS share can run for hours on a first pass or after a forced rescan;
# half a day without a completed scan is stuck, whatever the interval.
SCANNER_STALE_AFTER_SECONDS = 12 * 3600


def _scanner_tick() -> None:
    """One full scan; its return value is not a sleep override, so it is dropped here."""
    scanner_manager.run_full()


def run_scanner_loop(sleeptime: int = 3600, stop: threading.Event | None = None):
    """The `scanner` thread: a full scan on start, then one every `sleeptime` seconds, for good.

    Runs through thread_registry.run_forever, so a scan that raises is logged and retried
    instead of ending the loop. `stop` ends the loop when set (tests use it to run an exact
    number of rounds).
    """
    logger.info('Starting background scanner loop with sleeptime %d', sleeptime)
    run_forever(
        'scanner',
        _scanner_tick,
        sleeptime,
        stale_after=max(SCANNER_STALE_AFTER_SECONDS, default_stale_after(sleeptime)),
        stop=stop,
    )
