import logging
import math
import struct

from services.common.Helpers.DatabaseConnector import DatabaseConnector


def _escape_like(text: str) -> str:
    """A path as a literal inside a LIKE pattern: '_' and '%' are wildcards there."""
    return text.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')


def _float32(value: float) -> float:
    return struct.unpack('f', struct.pack('f', value))[0]


def _float32_step(value: float) -> float:
    """The spacing between neighbouring float32 values at this magnitude: 128 s at today's epoch."""
    return math.ldexp(1.0, math.frexp(value)[1] - 24) if value else 0.0


def changed_on_disk(mtime: float, stored: float) -> bool:
    """Whether the file's mtime says it was written after the tagger last saw it.

    `stored` used to live in a FLOAT column, which at today's epoch has a step of 128 s: the
    value written back was the real mtime rounded to the nearest step, so 70 % of the library
    compared as "newer than stored" on every walk and was retagged for nothing, round after
    round. The column is DOUBLE now (migrate_v29) but the rounded values are still in it. A
    stored value that is exactly float32-representable and within one float32 step of the
    mtime is that artefact, not an edit; an edit lands a real mtime outside the step. Rows
    heal as they are tagged for other reasons, which stores the exact value from then on.
    """
    if mtime <= stored:
        return False
    rounded_by_the_old_column = stored == _float32(stored) and mtime - stored <= _float32_step(stored)
    return not rounded_by_the_old_column


class ProcessedFilesHelper:
    """
    Helper class to track processed song files in the database.
    Stores song path and modification time to avoid redundant tagging.
    """

    #: A rule change can match thousands of files, so the IN-list of a bulk mark is
    #: chunked rather than handed to the database in one statement of unbounded size.
    BATCH_SIZE = 500

    #: Marker in the snapshot for a row flagged for rescan: it needs processing whatever
    #: the file's mtime says, so no real mtime is kept for it.
    FLAGGED = -1.0

    #: Reasons that queue the library wholesale rather than because somebody decided
    #: something about these files. They are served after every other reason, so a genre
    #: decision made this morning is not parked behind a month-old "rescan all". A row
    #: without a reason predates reasons being recorded and is treated the same way.
    BULK_REASONS = ('rescan_all', 'deep_run')
    #: The reason a file gets when the scanner has indexed it and the tagger has never
    #: seen it -- a file somebody dropped into the library by hand.
    NEW_IN_LIBRARY = 'new_in_library'

    #: The reason left on the row of a file that failed PARK_AFTER times in a row. The
    #: row is taken off the queue (needs_rescan FALSE) and carries the file's mtime, so
    #: neither the pending pass nor the walk touches it again until the file changes, a
    #: retag request queues it on purpose, or the deep run hands it back.
    FAILED = 'failed'
    #: The reason a file gets when it failed before anything had queued it (the walk
    #: found it): it goes on the queue so the backoff, not the daily walk, paces it.
    RETRY = 'retry'
    #: How many failed attempts in a row park a file, unless the caller says otherwise.
    PARK_AFTER = 5
    #: The base of the retry backoff: a row that failed `attempts` times is not handed
    #: out again until `last_attempt + 2^attempts * RETRY_BASE_SECONDS`. One tagger
    #: loop period, so the first retry skips one round and the fourth waits 80 minutes.
    RETRY_BASE_SECONDS = 300

    #: Appended to every UPDATE that queues a file on purpose: a fresh request is a
    #: fresh start for the retry backoff, and takes a parked row back onto the queue.
    _RESET_ATTEMPTS = ', attempts = 0, last_attempt = NULL'

    def __init__(self, table_name='tagger_processed_files'):
        self.table_name = table_name
        self.db_connector = DatabaseConnector()
        # filepath -> mtime (or FLAGGED) for the whole table, while a tagging round holds
        # one. None means every needs_processing goes to the database.
        self._snapshot: dict[str, float] | None = None

    def create_table(self):
        """Creates the table if it doesn't exist."""
        # filepath is utf8mb4_bin: the table default, utf8mb4_general_ci, folds case and
        # accents and weighs every emoji the same, so two files whose paths differ only in
        # such a character shared one row and overwrote each other's mtime. The snapshot
        # matches exactly; the key has to as well. See migrate_v37_processed_files_binary_path.sql.
        # attempts/last_attempt drive the retry backoff of a file that keeps failing.
        query = (
            f'CREATE TABLE IF NOT EXISTS {self.table_name} ('
            'filepath VARCHAR(767) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin PRIMARY KEY, '
            'mtime DOUBLE, '
            'last_processed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, '
            'needs_rescan BOOLEAN DEFAULT FALSE, '
            'rescan_reason VARCHAR(64) NULL, '
            'attempts INT NOT NULL DEFAULT 0, '
            'last_attempt TIMESTAMP NULL DEFAULT NULL'
            ')'
        )
        # pending_paths pages through the queued rows by primary key; without this the
        # table is scanned once per page, and there are 327k rows on production. The
        # reason is not in the key on purpose: filepath is VARCHAR(767) in utf8mb4, 3068
        # of the 3072 bytes a key may have, so nothing wider than a flag fits beside it.
        # A per-reason page filters on the reason while it walks this index, and because
        # the cursor only ever moves forward, one reason's pages together read each
        # queued row once.
        index = (
            f'CREATE INDEX IF NOT EXISTS idx_{self.table_name}_pending ON {self.table_name} (needs_rescan, filepath)'
        )
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                cursor.execute(index)
            connection.commit()
        except Exception as e:
            logging.error(f'Error creating {self.table_name}: {e}')
        finally:
            connection.close()

    def load_snapshot(self) -> bool:
        """Read the whole table once, so the round that follows asks it nothing per file.

        A tagging round walks every file in the library and asked this table about each
        one on a fresh connection: measured on production, 14 ms per file of which
        0.1 ms was the query, over 327k files -- 75 minutes of connecting per round,
        with nothing to tag. The same 327k rows come back in one SELECT in 1.4 s and
        fit in about 100 MB. The walk reads the dict, mark_processed keeps it current,
        and drop_snapshot ends the round. A file flagged for rescan *after* the load is
        missed by this round's walk and picked up by the next round's pending pass.

        Returns False when the table could not be read; the round then falls back to
        per-file queries rather than tagging nothing.
        """
        query = f'SELECT filepath, mtime, needs_rescan FROM {self.table_name}'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                snapshot: dict[str, float] = {}
                for filepath, db_mtime, needs_rescan in cursor.fetchall():
                    snapshot[str(filepath)] = self.FLAGGED if needs_rescan else float(db_mtime or 0)
            self._snapshot = snapshot
            return True
        except Exception as e:
            logging.error(f'Error loading the processed files snapshot: {e}')
            self._snapshot = None
            return False
        finally:
            connection.close()

    def drop_snapshot(self) -> None:
        self._snapshot = None

    def needs_processing(self, song_path: str, mtime: float) -> bool:
        """
        Checks if a song needs to be processed.
        Returns True if the song is not in the database, its mtime has changed,
        or it has been explicitly marked for rescan.
        """
        snapshot = self._snapshot
        if snapshot is not None:
            known = snapshot.get(song_path)
            if known is None or known == self.FLAGGED:
                return True
            return changed_on_disk(mtime, known)
        query = f'SELECT mtime, needs_rescan FROM {self.table_name} WHERE filepath = %s'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (song_path,))
                result = cursor.fetchone()
                if not result:
                    return True
                db_mtime, needs_rescan = result
                if needs_rescan:
                    return True
                return changed_on_disk(mtime, float(db_mtime))
        except Exception as e:
            logging.error(f'Error checking if song needs processing: {e}')
            return True
        finally:
            connection.close()

    def mark_processed(self, song_path: str, mtime: float):
        """Marks a song as processed in the database."""
        query = (
            f'INSERT INTO {self.table_name} (filepath, mtime, needs_rescan) VALUES (%s, %s, FALSE) '
            'ON DUPLICATE KEY UPDATE mtime = VALUES(mtime), needs_rescan = FALSE, rescan_reason = NULL'
            f'{self._RESET_ATTEMPTS}'
        )
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (song_path, mtime))
            connection.commit()
            snapshot = self._snapshot
            if snapshot is not None:
                snapshot[song_path] = mtime
        except Exception as e:
            logging.error(f'Error marking song as processed: {e}')
        finally:
            connection.close()

    def mark_failed(self, song_path: str, mtime: float, park_after: int = PARK_AFTER) -> int:
        """Count one failed tagging attempt; park the file once it has failed `park_after` times.

        The row stays (or is put) on the queue with its attempt counter raised, so the
        pending pass retries it only after the backoff in pending_paths. A row that was
        not queued yet -- the walk found the file -- is queued with reason RETRY; a
        queued row keeps the reason that queued it. On the `park_after`-th failure the
        row is taken off the queue with reason FAILED and the file's current mtime, so
        the walk leaves it alone too until the file changes.

        Returns the number of failed attempts now on the row, or 0 when the database
        could not be written; the caller picks its log level from it.
        """
        # Assignments in ON DUPLICATE KEY UPDATE are applied left to right, so the reason
        # is decided on the old needs_rescan before the flag is raised.
        upsert = (
            f'INSERT INTO {self.table_name} (filepath, mtime, needs_rescan, rescan_reason, attempts, last_attempt) '
            'VALUES (%s, 0, TRUE, %s, 1, NOW()) '
            'ON DUPLICATE KEY UPDATE rescan_reason = IF(needs_rescan, rescan_reason, VALUES(rescan_reason)), '
            'needs_rescan = TRUE, attempts = attempts + 1, last_attempt = NOW()'
        )
        read = f'SELECT attempts FROM {self.table_name} WHERE filepath = %s'
        park = f'UPDATE {self.table_name} SET needs_rescan = FALSE, rescan_reason = %s, mtime = %s WHERE filepath = %s'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(upsert, (song_path, self.RETRY))
                cursor.execute(read, (song_path,))
                row = cursor.fetchone()
                attempts = int(row[0]) if row else 1
                parked = attempts >= park_after
                if parked:
                    cursor.execute(park, (self.FAILED, mtime, song_path))
            connection.commit()
            snapshot = self._snapshot
            if snapshot is not None:
                snapshot[song_path] = mtime if parked else self.FLAGGED
            return attempts
        except Exception as e:
            logging.error(f'Error recording a failed tagging attempt: {e}')
            return 0
        finally:
            connection.close()

    def mark_stale_for_rescan(self, older_than_days: int, limit: int) -> int:
        """Hands the oldest rows back to the tagger, at most `limit` of them.

        Rows that are already queued are left alone, so a file that keeps failing cannot
        crowd out the rest of the library. `last_processed` is refreshed by
        mark_processed, which is what makes the whole library cycle past the current
        rules once every `older_than_days`.
        """
        query = (
            f'UPDATE {self.table_name} SET needs_rescan = TRUE, rescan_reason = %s{self._RESET_ATTEMPTS} '
            'WHERE needs_rescan = FALSE AND last_processed < NOW() - INTERVAL %s DAY '
            'ORDER BY last_processed LIMIT %s'
        )
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, ('deep_run', older_than_days, limit))
                marked = cursor.rowcount
            connection.commit()
            return marked
        except Exception as e:
            logging.error(f'Error queueing stale songs for rescan: {e}')
            return 0
        finally:
            connection.close()

    def count_stale(self, older_than_days: int) -> int:
        """How many rows are still waiting to be handed back to the tagger."""
        query = f'\n            SELECT COUNT(*) FROM {self.table_name}\n            WHERE needs_rescan = FALSE AND last_processed < NOW() - INTERVAL %s DAY\n        '
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (older_than_days,))
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logging.error(f'Error counting stale songs: {e}')
            return 0
        finally:
            connection.close()

    def mark_for_rescan(self, song_path: str = None, reason: str | None = None):
        """Marks one or all songs for rescan, optionally recording why.

        A retag asked for on purpose starts the file's failure count over, which is also
        what takes a parked (FAILED) row back onto the queue.
        """
        reason_sql = (', rescan_reason = %s' if reason else '') + self._RESET_ATTEMPTS
        if song_path:
            query = f'UPDATE {self.table_name} SET needs_rescan = TRUE{reason_sql} WHERE filepath = %s'
            args = (reason, song_path) if reason else (song_path,)
        else:
            query = f'UPDATE {self.table_name} SET needs_rescan = TRUE{reason_sql}'
            args = (reason,) if reason else None
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, args)
            connection.commit()
        except Exception as e:
            logging.error(f'Error marking songs for rescan: {e}')
        finally:
            connection.close()

    def mark_paths_for_rescan(self, paths: list[str], reason: str) -> int:
        """Marks an explicit list of paths, in batches of BATCH_SIZE.

        Returns how many paths were handed to the database, not how many rows actually
        changed: a path the tagger has never processed has no row here, and the caller
        only wants to know the size of what it just queued.
        """
        if not paths:
            return 0
        marked = 0
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                for start in range(0, len(paths), self.BATCH_SIZE):
                    chunk = paths[start : start + self.BATCH_SIZE]
                    placeholders = ', '.join(['%s'] * len(chunk))
                    query = (
                        f'UPDATE {self.table_name} SET needs_rescan = TRUE, rescan_reason = %s{self._RESET_ATTEMPTS} '
                        f'WHERE filepath IN ({placeholders})'
                    )
                    cursor.execute(query, (reason, *chunk))
                    marked += len(chunk)
            connection.commit()
        except Exception as e:
            logging.error(f'Error marking paths for rescan: {e}')
            return 0
        finally:
            connection.close()
        return marked

    def pending_reasons(self) -> list[str | None]:
        """The reasons with queued files, in the order the queue is served.

        Decisions first -- a genre or artist decision, a rule, a hand-picked file -- then
        files the scanner found that the tagger never saw, then the bulk reasons, then
        rows from before reasons were recorded. Within a class, alphabetical, which is
        stable and good enough: the point is that "rescan all" never buries a decision.
        """
        query = f'SELECT DISTINCT rescan_reason FROM {self.table_name} WHERE needs_rescan = TRUE'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                reasons = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f'Error reading the pending rescan reasons: {e}')
            return []
        finally:
            connection.close()

        def rank(reason):
            if reason is None:
                return (3, '')
            if reason in self.BULK_REASONS:
                return (2, reason)
            if reason == self.NEW_IN_LIBRARY:
                return (1, reason)
            return (0, reason)

        return sorted(reasons, key=rank)

    def pending_paths(self, limit: int, after: str = '', reason: str | None = None) -> list[str]:
        """The next page of files queued for one reason, in primary-key order.

        Keyed on the path rather than offset so that a file which fails to clear its
        flag -- unreadable, gone between the SELECT and the stat -- is not handed out
        again on the very next page. A round that is cut short by a restart resumes
        where it was for free: what it tagged is no longer queued. One reason per call,
        which is what lets a decision go first; see create_table for why the reason is a
        filter on the (flag, path) index rather than part of it.
        """
        reason_sql = 'rescan_reason IS NULL' if reason is None else 'rescan_reason = %s'
        # A file that failed is skipped until its backoff has run out: without this a
        # file that always raises was handed out every round, forever, with an ERROR
        # (and so an alert) each time. See mark_failed and bug report 051.
        backoff_sql = (
            '(last_attempt IS NULL OR last_attempt <= NOW() - INTERVAL (%s * POW(2, LEAST(attempts, 16))) SECOND)'
        )
        query = (
            f'SELECT filepath FROM {self.table_name} WHERE needs_rescan = TRUE AND {reason_sql} AND {backoff_sql} '
            f'AND filepath > %s ORDER BY filepath LIMIT %s'
        )
        tail = (self.RETRY_BASE_SECONDS, after, int(limit))
        args = tail if reason is None else (reason, *tail)
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, args)
                return [str(row[0]) for row in cursor.fetchall() if row and row[0]]
        except Exception as e:
            logging.error(f'Error reading the pending rescan queue: {e}')
            return []
        finally:
            connection.close()

    def queue_new_library_files(self, roots: list[str], extensions: tuple[str, ...]) -> int:
        """Queue every file the scanner has indexed that this table has never seen.

        A file dropped into the library by hand is found by nobody until a folder walk
        reaches it; the scanner, which walks on its own schedule, has usually seen it
        long before. The anti-join is that list. Limited to the roots and extensions the
        tagger would walk itself (the scanner also indexes Lidarr, Hitzone and .opus,
        which the tagger has no rules for), so this never queues what a walk would skip.
        Returns how many rows were added.
        """
        if not roots or not extensions:
            return 0
        root_sql = ' OR '.join(['mf.file_path LIKE %s'] * len(roots))
        ext_sql = ' OR '.join(['mf.file_path LIKE %s'] * len(extensions))
        query = (
            f'INSERT IGNORE INTO {self.table_name} (filepath, mtime, needs_rescan, rescan_reason) '
            f'SELECT mf.file_path, 0, TRUE, %s FROM library_media_files mf '
            f'LEFT JOIN {self.table_name} t ON t.filepath = mf.file_path COLLATE utf8mb4_bin '
            f'WHERE t.filepath IS NULL AND ({root_sql}) AND ({ext_sql})'
        )
        # The LIKEs run on library_media_files.file_path, which is case-insensitive
        # (utf8mb4_general_ci), so '.mp3' also finds the '.MP3' files the walk's
        # case-sensitive glob never did; BaseSong lower-cases the extension and reads them
        # fine. The join is binary -- this table's filepath is utf8mb4_bin since migrate_v37
        # -- so a path that differs from a known one only in case or an emoji is new. The
        # COLLATE is explicit because library_media_files may carry any _ci collation the
        # server defaulted to, and MariaDB will not pick between two of them implicitly.
        args = (
            self.NEW_IN_LIBRARY,
            *(f'{_escape_like(root.rstrip("/"))}/%' for root in roots),
            *(f'%.{_escape_like(ext)}' for ext in extensions),
        )
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, args)
                added = cursor.rowcount
            connection.commit()
            return max(added, 0)
        except Exception as e:
            logging.error(f'Error queueing files the scanner found: {e}')
            return 0
        finally:
            connection.close()

    #: The reason left on the row of a file that was queued but is not on disk.
    MISSING = 'missing'

    def forget(self, song_path: str) -> None:
        """Take a file that is no longer on disk off the queue, and remember that it is gone.

        A queued row whose file was moved or deleted would otherwise stay queued for
        ever: nothing walks into it to mark it processed, and the pending count keeps
        promising work that cannot be done. The row is kept, not deleted, as a tombstone
        with reason `missing` and no mtime: the scanner's own table keeps rows for files
        it has not seen since (768 on production the day this shipped, __TODO releases
        that the importer moved), and deleting ours let queue_new_library_files re-add
        every one of them each round. Should the file come back, its mtime is newer than
        0 and the next walk tags it; the deep run hands the row back after its window and
        this runs again, which is cheap.
        """
        query = (
            f'INSERT INTO {self.table_name} (filepath, mtime, needs_rescan, rescan_reason) VALUES (%s, 0, FALSE, %s) '
            'ON DUPLICATE KEY UPDATE needs_rescan = FALSE, rescan_reason = VALUES(rescan_reason)'
        )
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (song_path, self.MISSING))
            connection.commit()
        except Exception as e:
            logging.error(f'Error marking a vanished file as missing: {e}')
        finally:
            connection.close()

    def pending_summary(self) -> dict:
        """How many files are waiting for a retag, grouped by why, and how many are parked.

        `failed` counts the files parked after PARK_AFTER failures in a row. They are not
        in `total`: nothing picks them up until the file changes or somebody asks for a
        retag, and a pending count that never goes down reads as a stuck tagger.
        """
        query = (
            f'SELECT COALESCE(rescan_reason, %s) AS reason, COUNT(*) FROM {self.table_name} '
            f'WHERE needs_rescan = TRUE GROUP BY reason ORDER BY COUNT(*) DESC'
        )
        parked = f'SELECT COUNT(*) FROM {self.table_name} WHERE needs_rescan = FALSE AND rescan_reason = %s'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, ('unknown',))
                rows = [{'reason': str(row[0]), 'count': int(row[1])} for row in cursor.fetchall()]
                cursor.execute(parked, (self.FAILED,))
                failed = cursor.fetchone()
                return {
                    'total': sum(row['count'] for row in rows),
                    'by_reason': rows,
                    'failed': int(failed[0]) if failed else 0,
                }
        except Exception as e:
            logging.error(f'Error building the pending rescan summary: {e}')
            return {'total': 0, 'by_reason': [], 'failed': 0}
        finally:
            connection.close()
