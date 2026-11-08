"""Remembering the folder conflicts the importer cannot resolve on its own (bug report 091).

The renamer and the mover both leave two folders in place when the name one of them wants
is taken by a folder holding something else. Nothing on the next cycle is any different,
so the same pair used to be compared again -- reading the length of every track over
CIFS -- and warned about again, every five minutes: 49 pairs on production produced about
490 WARNING events an hour, each of them also a candidate for the alerts topic.

`ConflictTracker` makes a standing conflict cost one WARNING, the first time it is seen.
After that the pair is only compared again when either folder changed on disk, a repeat is
logged at DEBUG, and each cycle ends with one line counting what stands. A pair that is no
longer met -- someone removed or renamed one of the folders -- is forgotten, and would warn
again if it ever came back. Nothing here moves, merges or deletes a folder.

The pairs live in `importer_conflicts`, so a restart or a deploy does not warn about the
whole list again, and so Management can show them next to the label proposals. When that table
cannot be read the tracker falls back to what this process remembers.

The extractor files its standing problems in the same table (bug report 119): a file in the
import folder that is not an archive -- a video a browser download left behind, say -- or an
archive no backend can extract. `FileProblemTracker` keys those on the file alone, with a
`reason` code saying what is wrong, and looks at the file again only when its size or mtime
changed.
"""

import hashlib
import logging
import os
from dataclasses import dataclass

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.importer.settle import folder_signature

#: The two steps that can meet a conflict. Stored with the pair, so each step prunes only
#: the pairs it is responsible for.
RENAMER = 'renamer'
MOVER = 'mover'
#: The extract step, whose rows are single files rather than folder pairs (bug report 119).
EXTRACTOR = 'extractor'

#: Longest `target` the table holds; an extractor row keeps its detail there.
TARGET_MAX = 1024

SNAPSHOT_QUERY = 'SELECT pair_key, fingerprint FROM importer_conflicts WHERE step = %s'

RECORD_QUERY = """
    INSERT INTO importer_conflicts (pair_key, step, source, target, fingerprint, reason)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE fingerprint = VALUES(fingerprint), target = VALUES(target),
        reason = VALUES(reason), last_seen = CURRENT_TIMESTAMP
"""

TOUCH_QUERY = 'UPDATE importer_conflicts SET last_seen = CURRENT_TIMESTAMP WHERE pair_key = %s'

FORGET_QUERY = 'DELETE FROM importer_conflicts WHERE pair_key = %s'


def pair_key(step: str, source: str, target: str) -> str:
    """The key one conflict is filed under. Hashed because two full paths exceed an index."""
    return hashlib.sha256('\x1f'.join((step, source, target)).encode('utf-8')).hexdigest()


def pair_fingerprint(source: str, target: str) -> str | None:
    """What the two folders looked like when they were last compared, or None if unreadable.

    Built from `folder_signature` -- entries, total size and newest mtime, one walk of
    `stat` calls -- so deciding that nothing changed never opens a file.
    """
    try:
        source_signature, target_signature = folder_signature(source), folder_signature(target)
    except OSError:
        return None
    if source_signature is None or target_signature is None:
        return None
    return hashlib.sha256(f'{source_signature}\x1f{target_signature}'.encode()).hexdigest()


def file_fingerprint(path: str) -> str | None:
    """Size and mtime of one file, hashed; None when it cannot be stat'ed. Never opens it."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return hashlib.sha256(f'{stat.st_size}\x1f{stat.st_mtime_ns}'.encode()).hexdigest()


class ConflictStore:
    """Reads and writes `importer_conflicts`. Every failure is logged and swallowed."""

    def __init__(self):
        self.db_connector = DatabaseConnector()
        #: Whether the last read failed, so an outage is warned about once and not every cycle.
        self._unreadable = False

    def snapshot(self, step: str) -> dict[str, str | None] | None:
        """pair_key -> fingerprint for every standing conflict of `step`; None when unreadable.

        The first failure in a row is a WARNING, the repeats are DEBUG: this runs every cycle,
        and replacing one warning per conflict with one per cycle would be the same spam.
        """
        try:
            with self.db_connector.connection() as connection, connection.cursor() as cursor:
                cursor.execute(SNAPSHOT_QUERY, (step,))
                rows = cursor.fetchall()
            snapshot = {str(key): (str(fp) if fp is not None else None) for key, fp in rows}
        except Exception as e:  # noqa: BLE001 - a missing memory is never a reason to fail the import
            level = logging.DEBUG if self._unreadable else logging.WARNING
            logging.log(level, 'Could not read the standing import conflicts, remembering them in-process: %s', e)
            self._unreadable = True
            return None
        self._unreadable = False
        return snapshot

    def _execute(self, query: str, params: tuple) -> None:
        """Run one write and commit it; skipped while the table cannot even be read."""
        if self._unreadable:
            return
        try:
            with self.db_connector.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                connection.commit()
        except Exception as e:  # noqa: BLE001 - see snapshot
            logging.error(f'Could not update the standing import conflicts: {e}')

    def record(
        self, key: str, step: str, source: str, target: str, fingerprint: str | None, reason: str | None = None
    ) -> None:
        """Remember a conflict, or refresh the fingerprint of one already remembered.

        `reason` is NULL for a folder conflict and one of the extractor's reason codes for a
        file it could not import (bug report 119).
        """
        self._execute(RECORD_QUERY, (key, step, source, target, fingerprint, reason))

    def touch(self, key: str) -> None:
        """Mark a remembered conflict as met again this cycle."""
        self._execute(TOUCH_QUERY, (key,))

    def forget(self, key: str) -> None:
        """Drop a conflict that is no longer met."""
        self._execute(FORGET_QUERY, (key,))


@dataclass
class _Pair:
    """One conflict as this process last saw it."""

    fingerprint: str | None


class ConflictTracker:
    """Once-per-pair logging and a per-cycle count for one step's folder conflicts.

    Used as: `begin()` at the start of a cycle; for each conflict, `unchanged(src, dst)`
    to learn whether the comparison can be skipped, then `differs(...)` or `same(...)`
    with its outcome; `end()` once the cycle is done.
    """

    #: How the per-cycle summary line names what it counts.
    summary = 'Standing folder conflicts'

    def __init__(self, step: str, store: ConflictStore | None = None):
        self.step = step
        self.store = store if store is not None else ConflictStore()
        #: What stood at the end of the last cycle; the fallback when the table is unreadable.
        self._known: dict[str, _Pair] = {}
        self._from_database = False
        self._seen: set[str] = set()
        self._new = 0
        self._fingerprints: dict[str, str | None] = {}

    def begin(self) -> None:
        """Start a cycle: load what stands, and forget what was met last cycle."""
        snapshot = self.store.snapshot(self.step)
        self._from_database = snapshot is not None
        if snapshot is not None:
            self._known = {key: _Pair(fp) for key, fp in snapshot.items()}
        self._seen = set()
        self._new = 0
        self._fingerprints = {}

    def unchanged(self, source: str, target: str) -> bool:
        """Whether this pair already stands and neither folder changed since it was compared.

        True means the caller can skip the comparison: the answer would be the same. The
        repeat is logged at DEBUG, which never reaches the events table.
        """
        key = pair_key(self.step, source, target)
        fingerprint = self._fingerprint(source, target)
        self._fingerprints[key] = fingerprint
        known = self._known.get(key)
        if known is None or fingerprint is None or known.fingerprint != fingerprint:
            return False
        self._seen.add(key)
        logging.debug('Conflict still stands: %s and %s', target, source)
        if self._from_database:
            self.store.touch(key)
        return True

    def differs(self, source: str, target: str, dry_run: bool = False) -> None:
        """Record a pair that was compared and found to hold different releases.

        WARNING the first time the pair is seen; INFO when it was already standing and one
        of the folders changed without resolving it.
        """
        key = pair_key(self.step, source, target)
        fingerprint = self._fingerprints.get(key, self._fingerprint(source, target))
        self._seen.add(key)
        if key in self._known:
            logging.info(
                'Conflict: %s still differs from %s after a change on disk; both left in place', target, source
            )
        else:
            self._new += 1
            logging.warning(
                'Conflict: %s already exists but its contents differ from %s. Leaving both in place for '
                'manual intervention',
                target,
                source,
            )
        self._known[key] = _Pair(fingerprint)
        if not dry_run:
            self.store.record(key, self.step, source, target, fingerprint)

    def _fingerprint(self, source: str, target: str) -> str | None:
        """What decides that nothing changed since the pair was last looked at."""
        return pair_fingerprint(source, target)

    def same(self, source: str, target: str) -> None:
        """A pair that turned out to be a duplicate: the caller parks the source, nothing stands."""
        key = pair_key(self.step, source, target)
        self._seen.discard(key)

    def end(self, dry_run: bool = False) -> int:
        """Close the cycle: forget pairs no longer met, log one summary line, return the count.

        Nothing is forgotten in a dry run, which does not meet every conflict a real run does.
        """
        resolved = [key for key in self._known if key not in self._seen]
        if not dry_run:
            for key in resolved:
                if self._from_database:
                    self.store.forget(key)
                del self._known[key]
        standing = len(self._seen)
        if standing or resolved:
            logging.info(
                '%s (%s): %d, %d new this cycle, %d resolved since the last one',
                self.summary,
                self.step,
                standing,
                self._new,
                len(resolved),
            )
        return standing


#: Why the extractor left a file in the import folder, as stored in `importer_conflicts.reason`
#: and translated by Management. The text here is what the one WARNING says.
NOT_AN_ARCHIVE = 'not-an-archive'
LOOSE_AUDIO = 'loose-audio'
NOT_MUSIC_VIDEO = 'not-music-video'
NOT_MUSIC_IMAGE = 'not-music-image'
NOT_MUSIC_DOCUMENT = 'not-music-document'
NOT_MUSIC_OTHER = 'not-music-other'
UNREADABLE = 'unreadable'
EXTRACTION_FAILED = 'extraction-failed'
EXTRACTION_EMPTY = 'extraction-empty'
EXTRACTION_NAME_TAKEN = 'extraction-name-taken'
EXTRACTION_UNSAFE = 'extraction-unsafe'

REASONS: dict[str, str] = {
    NOT_AN_ARCHIVE: 'named like an archive, but its contents are not one',
    LOOSE_AUDIO: 'an audio file outside a release folder',
    NOT_MUSIC_VIDEO: 'not music: video file',
    NOT_MUSIC_IMAGE: 'not music: image',
    NOT_MUSIC_DOCUMENT: 'not music: document',
    NOT_MUSIC_OTHER: 'not music and not an archive',
    UNREADABLE: 'the file cannot be read',
    EXTRACTION_FAILED: 'no backend could extract this archive',
    EXTRACTION_EMPTY: 'this archive extracted to nothing',
    EXTRACTION_NAME_TAKEN: 'this archive holds a folder whose name is taken by a different release',
    EXTRACTION_UNSAFE: 'this archive holds a link to a place outside its own folder',
}


class FileProblemTracker(ConflictTracker):
    """Once-per-file logging for what the extract step cannot import (bug report 119).

    Each cycle, `standing(path)` says whether a file already stands and is unchanged -- in
    which case the step leaves it alone, without opening it -- and `problem(...)` records one
    it just looked at. A file that is removed, renamed or finally extracted is forgotten at
    `end()`; one that changes on disk (a re-download over a broken archive, say) is looked at
    again. Nothing here moves or deletes a file.
    """

    summary = 'Standing import files'

    def __init__(self, store: ConflictStore | None = None):
        super().__init__(EXTRACTOR, store)

    def _fingerprint(self, source: str, target: str) -> str | None:
        """Size and mtime of the file; `target` is always empty for a file."""
        return file_fingerprint(source)

    def standing(self, path: str) -> bool:
        """Whether `path` was recorded before and has not changed since: skip it this cycle.

        A row recorded with `watch_folder` also counts as changed once the folder holding
        the file changed -- an entry added, removed or renamed beside it.
        """
        key = pair_key(self.step, path, '')
        fingerprint = file_fingerprint(path)
        self._fingerprints[key] = fingerprint
        known = self._known.get(key)
        if known is None or fingerprint is None:
            return False
        if known.fingerprint not in (fingerprint, _with_folder(fingerprint, path)):
            return False
        self._seen.add(key)
        logging.debug('Still left in place, unchanged: %s', path)
        if self._from_database:
            self.store.touch(key)
        return True

    def problem(
        self, path: str, reason: str, detail: str = '', dry_run: bool = False, watch_folder: bool = False
    ) -> None:
        """Record a file the step left in place, with a WARNING only the first time it is seen.

        `watch_folder` is for a problem that lies beside the file rather than in it: an
        archive whose release folder name is taken is worth extracting again as soon as the
        folder that took the name is gone, even though the archive itself never changed.
        """
        key = pair_key(self.step, path, '')
        fingerprint = self._fingerprints.get(key) or file_fingerprint(path)
        if watch_folder and fingerprint is not None:
            fingerprint = _with_folder(fingerprint, path)
        self._seen.add(key)
        description = REASONS.get(reason, reason)
        suffix = f' ({detail})' if detail else ''
        if key in self._known:
            logging.info('Still left in place after a change on disk, %s: %s%s', description, path, suffix)
        else:
            self._new += 1
            logging.warning(
                'Left in the import folder, %s: %s%s. Not retried until the file changes; listed in Management '
                'for manual intervention',
                description,
                path,
                suffix,
            )
        self._known[key] = _Pair(fingerprint)
        if not dry_run:
            self.store.record(key, self.step, path, detail[:TARGET_MAX], fingerprint, reason)


def _with_folder(fingerprint: str, path: str) -> str | None:
    """`fingerprint` combined with the mtime of the folder holding `path`; None if that is unreadable."""
    try:
        folder_mtime = os.stat(os.path.dirname(path) or '.').st_mtime_ns
    except OSError:
        return None
    return hashlib.sha256(f'{fingerprint}\x1f{folder_mtime}'.encode()).hexdigest()
