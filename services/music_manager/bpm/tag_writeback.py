"""Write the measured tempo into the files' own BPM tag (issue #139).

docs/designs/bpm-tag-writeback/. The bpm-analyzer container measures every track and stores
the result in `library_track_bpm`; it mounts the music share read-only on purpose. Writing
files is the tagger's job, so this runs in music-manager, as a step of the tagger's round,
after the retag queue (`TaggerManager.run_full`): decisions, new files and every other reason
are served first, and this step writes at most `bpm_tag_writeback_per_round` files per round,
one at a time, with a pause after every slice -- a bulk job in the API's process has starved
the API before.

Three parts:

- `decide` -- the rule: which existing tag gives way to the measurement.
- `read_bpm_tag` / `write_bpm_tag` -- one tag frame per format (ID3 TBPM, MP4 `tmpo`, Vorbis
  `BPM`), every other tag and the audio left as they are.
- `BpmTagStore` + `BpmTagWriteback` -- the queue and the round. The queue is
  `library_track_bpm` itself: a confident, current measurement whose `tag_bpm` (the measured
  value the file was last reconciled with) differs from `bpm`. Every outcome -- written, already
  matching, deliberately kept, unreadable -- stamps `tag_bpm`, so a file is looked at once per
  measurement; a new measurement with a different value queues it again.

Writing a file changes its mtime and size, which three other readers compare: the analyzer
(`library_track_bpm.file_mtime/size` -- it would measure the file again), the scanner
(`library_media_files` -- it would read every tag again, though it reads no BPM) and the tagger
(`tagger_processed_files.mtime` -- the daily walk would run the whole rule stack on it). Each is
moved to the new stat *only if it described the file as it was just before the write*, so a
change nobody had seen yet is not hidden. LMS is told the folder, the way the tagger tells it.
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from services.common.Helpers.ProcessedFilesHelper import changed_on_disk
from services.music_manager.bpm.octave import FOLD_VERSION

logger = logging.getLogger('music-manager.bpm.tags')

#: The estimator whose measurements are written: `estimator.METHOD`, spelled out rather than
#: imported, because the estimator pulls in numpy and this module is imported by the tagger
#: router at music-manager's start-up. test_bpm_tag_writeback.py keeps the two equal.
MEASURED_METHOD = 'acf-comb-v1'

# ----------------------------------------------------------------------------- the rule

#: Tags outside this range are noise (a zero, a mis-parsed 1500), the same bounds as effective.py.
MIN_BPM = 40.0
MAX_BPM = 500.0

#: The old analyzer (librosa's default beat tracker, the deprecated ml-analyzer and the tagger's
#: `analyze_bpm` rule) can only produce `60 * 22050 / (512 * lag)` for a lag in half frames:
#: 143.6, 147.7, 152.0, 156.6, 161.5 ... (docs/designs/bpm-browse/technical.md). A tag it wrote
#: is one of these, rounded or cut to an integer.
_GRID_NUMERATOR = 60 * 22050 / 512 * 2


def _librosa_grid_integers() -> frozenset[int]:
    """Every integer the old analyzer's tags can carry: each grid value rounded and truncated."""
    values: set[int] = set()
    for step in range(1, 1000):
        grid = _GRID_NUMERATOR / step
        if grid < MIN_BPM - 1:
            break
        if grid <= MAX_BPM + 1:
            values.add(math.floor(grid))
            values.add(math.floor(grid + 0.5))
    return frozenset(values)


LIBROSA_GRID_INTEGERS = _librosa_grid_integers()


def on_librosa_grid(value: float) -> bool:
    """True for an integer tag the old analyzer could have written."""
    return float(value).is_integer() and int(value) in LIBROSA_GRID_INTEGERS


def round_bpm(value: float) -> int:
    """A tempo as the integer the tag gets: half up (150.5 -> 151), not Python's half-even."""
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def parse_bpm(text: Any) -> float | None:
    """A tag's text as a tempo, or None when it is empty, unreadable or out of 40-500."""
    if text is None:
        return None
    raw = str(text).strip().replace(',', '.')
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or not MIN_BPM <= value <= MAX_BPM:
        return None
    return value


@dataclass(frozen=True)
class Decision:
    """What to do with one file's tag: write `value` or leave it, and why."""

    write: bool
    value: int
    reason: str


def decide(existing: Any, measured: float) -> Decision:
    """The rule. `existing` is the tag's text (or None), `measured` the stored measurement.

    - No usable tag -> write (`missing`).
    - The tag already says the measurement: within half a BPM, or the same integer -> leave
      (`matches`). A precise 150.4 against a measured 150.6 is not worth a write.
    - A whole-number tag the old analyzer cannot have produced (150, 155, 160 ...) within 1 BPM
      of the measurement -> leave (`kept`): somebody typed or bought that number, and the
      measurement is only ~84.5% within 1 BPM itself.
    - Anything else -> write: an octave off (`octave`, the tag is double or half), or just
      different (`differs`) -- the old coarse values end up here.
    """
    target = round_bpm(measured)
    tag = parse_bpm(existing)
    if tag is None:
        return Decision(True, target, 'missing')
    if abs(tag - measured) < 0.5 or round_bpm(tag) == target:
        return Decision(False, target, 'matches')
    if tag.is_integer() and not on_librosa_grid(tag) and abs(tag - measured) <= 1.0:
        return Decision(False, target, 'kept')
    if abs(tag - 2 * measured) <= 2.0 or abs(tag - measured / 2) <= 1.0:
        return Decision(True, target, 'octave')
    return Decision(True, target, 'differs')


# ----------------------------------------------------------------------------- the formats


class UnsupportedFormat(ValueError):
    """A file this step does not write (by extension)."""


ID3_EXTENSIONS = ('.mp3',)
WAVE_EXTENSIONS = ('.wav',)
MP4_EXTENSIONS = ('.m4a', '.mp4')
FLAC_EXTENSIONS = ('.flac',)
OPUS_EXTENSIONS = ('.opus',)
VORBIS_EXTENSIONS = ('.ogg', '.oga')
SUPPORTED_EXTENSIONS = (
    *ID3_EXTENSIONS,
    *WAVE_EXTENSIONS,
    *MP4_EXTENSIONS,
    *FLAC_EXTENSIONS,
    *OPUS_EXTENSIONS,
    *VORBIS_EXTENSIONS,
)


def _open(path: str) -> tuple[str, Any]:  # pylint: disable=too-many-return-statements  # one per format
    """(kind, mutagen object) for the file; mutagen is imported here so a test stub never sticks."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ID3_EXTENSIONS:
        from mutagen.id3 import ID3, ID3NoHeaderError  # pylint: disable=import-outside-toplevel

        try:
            return 'id3', ID3(path)
        except ID3NoHeaderError:
            return 'id3', ID3()
    if ext in WAVE_EXTENSIONS:
        from mutagen.wave import WAVE  # pylint: disable=import-outside-toplevel

        return 'wave', WAVE(path)
    if ext in MP4_EXTENSIONS:
        from mutagen.mp4 import MP4  # pylint: disable=import-outside-toplevel

        return 'mp4', MP4(path)
    if ext in FLAC_EXTENSIONS:
        from mutagen.flac import FLAC  # pylint: disable=import-outside-toplevel

        return 'vorbis', FLAC(path)
    if ext in OPUS_EXTENSIONS:
        from mutagen.oggopus import OggOpus  # pylint: disable=import-outside-toplevel

        return 'vorbis', OggOpus(path)
    if ext in VORBIS_EXTENSIONS:
        from mutagen.oggvorbis import OggVorbis  # pylint: disable=import-outside-toplevel

        return 'vorbis', OggVorbis(path)
    raise UnsupportedFormat(ext or '(no extension)')


def _id3_text(tags: Any) -> str | None:
    if tags is None:
        return None
    frame = tags.get('TBPM')
    if frame is None or not frame.text:
        return None
    return str(frame.text[0])


def _read(kind: str, audio: Any) -> str | None:
    if kind == 'id3':
        return _id3_text(audio)
    if kind == 'wave':
        return _id3_text(audio.tags)
    if kind == 'mp4':
        values = (audio.tags or {}).get('tmpo')
        return str(values[0]) if values else None
    values = (audio.tags or {}).get('BPM') if audio.tags is not None else None
    return str(values[0]) if values else None


def read_bpm_tag(path: str) -> str | None:
    """The file's BPM tag as text, or None when it has none."""
    kind, audio = _open(path)
    return _read(kind, audio)


def _id3_version(tags: Any) -> int:
    """The ID3v2 minor version to save as: what the file had (2.3 stays 2.3), else 2.4."""
    version = getattr(tags, 'version', None) or (2, 4, 0)
    return 3 if tuple(version[:2]) == (2, 3) else 4


def _set_tbpm(tags: Any, value: int) -> None:
    from mutagen.id3 import TBPM, Encoding  # pylint: disable=import-outside-toplevel

    tags.delall('TBPM')
    # Latin-1: the value is digits, and it is valid in both ID3v2.3 and 2.4.
    tags.add(TBPM(encoding=Encoding.LATIN1, text=[str(value)]))


def write_bpm_tag(path: str, value: int) -> None:
    """Set the file's BPM tag to the integer `value`; nothing else in the file changes.

    - MP3: the ID3v2 `TBPM` frame, saved in the version the file already had. A file without an
      ID3v2 tag gets one; the ID3v1 tag at the end, if any, is left to mutagen's default
      (updated only if present).
    - WAV: the same frame in the file's `id3 ` chunk.
    - M4A: the integer `tmpo` atom -- the real atom, never a freeform `----:` one, and never a
      bare name longer than four bytes (mutagen truncates those; see the M4A notes in
      services/tagger/constants.py).
    - FLAC, Opus, Ogg Vorbis: the Vorbis comment `BPM`, replacing any spelling of it.

    Integer, not a decimal: ID3's TBPM is defined as an integer, `tmpo` is one, and DJ software
    and TagLib (which LMS reads tags with) read a whole number everywhere. The precise value
    stays in the database.
    """
    kind, audio = _open(path)
    if kind == 'id3':
        _set_tbpm(audio, value)
        audio.save(path, v2_version=_id3_version(audio))
        return
    if kind == 'wave':
        if audio.tags is None:
            audio.add_tags()
        _set_tbpm(audio.tags, value)
        audio.save(v2_version=_id3_version(audio.tags))
        return
    if kind == 'mp4':
        if audio.tags is None:
            audio.add_tags()
        audio.tags['tmpo'] = [int(value)]
        audio.save()
        return
    if audio.tags is None:
        audio.add_tags()
    audio.tags['BPM'] = [str(value)]
    audio.save()


# ----------------------------------------------------------------------------- settings

#: (key, type, default, bounds) of the step's settings; the same keys and defaults as the BPM
#: group in services/common/config_store.py.
SETTINGS: tuple[tuple[str, str, Any, tuple[int, int] | None], ...] = (
    ('bpm_tag_writeback_enabled', 'boolean', True, None),
    ('bpm_tag_writeback_paused', 'boolean', False, None),
    ('bpm_tag_writeback_per_round', 'integer', 300, (0, 5000)),
    ('bpm_tag_writeback_min_confidence', 'integer', 75, (0, 100)),
    ('bpm_analysis_skip_forms', 'string', 'set,liveset,podcast,interview,preview', None),
)


def _coerce(kind: str, value: Any, default: Any) -> Any:
    if value is None:
        return default
    if kind == 'boolean':
        if isinstance(value, str):
            return value.strip().lower() not in ('0', 'false', 'no', 'off', '')
        return bool(value)
    if kind == 'integer':
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return str(value)


def read_settings(get: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """The step's settings from music-manager's ConfigStore (Beheer -> Config -> BPM), clamped."""
    if get is None:
        from services.common.config_store import ConfigStore  # pylint: disable=import-outside-toplevel

        get = ConfigStore().get
    values: dict[str, Any] = {}
    for key, kind, default, bounds in SETTINGS:
        value = _coerce(kind, get(key), default)
        if bounds:
            value = min(bounds[1], max(bounds[0], value))
        values[key] = value
    values['skip_forms'] = sorted(
        {form.strip().lower() for form in values['bpm_analysis_skip_forms'].split(',') if form.strip()}
    )
    return values


#: Folders the step writes in: the ones the tagger owns and tags itself. Not Lidarr, Hitzone or
#: Spotify (another tool's files), not Livesets, Podcasts or Warm Up Mixes (mixes, whatever form
#: the scanner gave a file there).
TAGGER_TRACK_FOLDERS = ('Soundcloud', 'Youtube', 'Telegram', 'Top 100')


def library_roots(settings: Any = None) -> list[str]:
    """The absolute roots the step may write under: the label tree and TAGGER_TRACK_FOLDERS."""
    if settings is None:
        from services.common.config_store import ConfigStore  # pylint: disable=import-outside-toplevel

        settings = ConfigStore()
    roots = []
    eps = settings.get('eps_folder_path')
    if eps:
        roots.append(str(eps))
    music = settings.get('music_folder_path')
    if music:
        roots.extend(str(Path(music) / folder) for folder in TAGGER_TRACK_FOLDERS)
    return roots


# ----------------------------------------------------------------------------- SQL

#: Confident, current measurements whose file has not been reconciled with this value yet,
#: newest track first. The value is the tempo set by hand when there is one (bug report 140),
#: else the measurement -- and a measurement only when its octave was chosen by the current rule
#: (`fold_version`; a deploy's refold must run first) and it is confident. A file this step once
#: wrote is queued again whenever its value changes, confident or not: the value it carries came
#: from a rule that has since changed its mind, so any current value is better than keeping it. A measurement is current while its file_mtime/size match what the
#: scanner last saw (the analyzer's own test); one that is not is the analyzer's to redo.
#: Folders: under a root (`{roots}`, one LIKE each), never through a hidden (`.quarantine`),
#: underscore (`__TODO`, the import queue), `#recycle` or `@eaDir` folder.
#: Parameters: method, min confidence, the skipped forms, the root patterns, the limit.
DUE_SQL = """
    SELECT t.id AS track_id, b.track_uid, COALESCE(mb.bpm, b.bpm) AS bpm, b.confidence,
           mb.bpm AS manual_bpm, b.file_mtime, b.file_size, mf.id AS media_id, mf.file_path
    FROM library_track_bpm b
    JOIN library_tracks t ON t.track_uid = b.track_uid
    JOIN library_media_files mf
      ON mf.id = (SELECT MIN(m2.id) FROM library_media_files m2 WHERE m2.track_id = t.id)
    LEFT JOIN library_track_bpm_manual mb ON mb.track_uid = b.track_uid
    WHERE b.status = 'ok' AND b.method = %s AND b.bpm IS NOT NULL
      AND (mb.bpm IS NOT NULL
           OR (b.fold_version = %s AND (b.confidence >= %s OR b.tag_action = 'written')))
      AND NOT (b.tag_bpm <=> COALESCE(mb.bpm, b.bpm))
      AND b.file_mtime <=> mf.file_mtime AND b.file_size <=> mf.file_size
      AND (t.form IS NULL OR t.form NOT IN ({forms}))
      AND ({roots})
      AND mf.file_path NOT LIKE '%%/.%%'
      AND mf.file_path NOT LIKE '%%/\\_%%'
      AND mf.file_path NOT LIKE '%%/#%%'
      AND mf.file_path NOT LIKE '%%/@%%'
    ORDER BY t.id DESC
    LIMIT %s
"""

#: The same queue, counted, for the round's summary line.
REMAINING_SQL = (
    'SELECT COUNT(*) AS remaining FROM (' + DUE_SQL.replace('ORDER BY t.id DESC\n    LIMIT %s', '') + ') AS due'
)

#: Stamp the outcome for the value that was read; a value that changed meanwhile (a new
#: measurement, a refold, a tempo set or cleared by hand) is left queued for its new value.
RECORD_SQL = """
    UPDATE library_track_bpm b
    LEFT JOIN library_track_bpm_manual mb ON mb.track_uid = b.track_uid
    SET b.tag_bpm = %s, b.tag_action = %s, b.tag_checked_at = %s
    WHERE b.track_uid = %s AND COALESCE(mb.bpm, b.bpm) = %s
"""

#: After a write: the measurement describes the new file, if it described the old one.
REFRESH_BPM_SQL = """
    UPDATE library_track_bpm SET file_mtime = %s, file_size = %s
    WHERE track_uid = %s AND file_mtime <=> %s AND file_size <=> %s
"""

#: After a write: the scanner's row describes the new file, if it described the old one. The
#: scanner reads no BPM, so reading the file again would change nothing.
REFRESH_MEDIA_SQL = """
    UPDATE library_media_files SET file_mtime = %s, file_size = %s
    WHERE id = %s AND file_mtime <=> %s AND file_size <=> %s
"""

PROCESSED_SQL = 'SELECT mtime, needs_rescan FROM tagger_processed_files WHERE filepath = %s'

#: After a write: the tagger's row, keeping last_processed (ON UPDATE CURRENT_TIMESTAMP would
#: otherwise push the deep run's next visit a month out for a file whose rules never ran).
REFRESH_PROCESSED_SQL = (
    'UPDATE tagger_processed_files SET mtime = %s, last_processed = last_processed '
    'WHERE filepath = %s AND needs_rescan = FALSE'
)


def _escape_like(text: str) -> str:
    return text.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')


def _due_params(config: dict, roots: list[str], limit: int | None) -> tuple[str, list]:
    """The queue statement and its parameters; `limit=None` gives the counting variant."""
    forms = [*config['skip_forms'], '']
    root_patterns = [f'{_escape_like(root.rstrip("/"))}/%' for root in roots] or ['']
    sql = (REMAINING_SQL if limit is None else DUE_SQL).format(
        forms=', '.join(['%s'] * len(forms)),
        roots=' OR '.join(['mf.file_path LIKE %s'] * len(root_patterns)),
    )
    params: list = [
        MEASURED_METHOD,
        FOLD_VERSION,
        config['bpm_tag_writeback_min_confidence'] / 100.0,
        *forms,
        *root_patterns,
    ]
    if limit is not None:
        params.append(int(limit))
    return sql, params


class BpmTagStore:
    """Every statement the step runs, one short-lived connection per call."""

    def __init__(self, connect: Callable[[], Any] | None = None):
        if connect is None:
            from services.music_manager.database import get_db_connection  # pylint: disable=import-outside-toplevel

            connect = get_db_connection
        self._connect_fn = connect

    def _connect(self) -> Any:
        conn = self._connect_fn()
        if not conn:
            raise RuntimeError('database connection failed')
        return conn

    def _rows(self, sql: str, params: Iterable) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(params))
                return list(cursor.fetchall())
        finally:
            conn.close()

    def due(self, config: dict, roots: list[str], limit: int) -> list[dict]:
        """Up to `limit` files to reconcile, newest track first."""
        sql, params = _due_params(config, roots, limit)
        return self._rows(sql, params)

    def remaining(self, config: dict, roots: list[str]) -> int:
        """How many files the queue holds right now."""
        sql, params = _due_params(config, roots, None)
        rows = self._rows(sql, params)
        return int(rows[0]['remaining']) if rows else 0

    def record(self, row: dict, action: str, now: datetime) -> None:
        """Stamp an outcome without a write: the file is reconciled with this measurement."""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(RECORD_SQL, (row['bpm'], action, now, row['track_uid'], row['bpm']))
            conn.commit()
        finally:
            conn.close()

    def record_written(self, row: dict, before: os.stat_result, after: os.stat_result, now: datetime) -> None:
        """Stamp a write and move the three readers' view of the file to its new stat.

        Each only if it described the file as it was just before the write (see the module
        docstring). One transaction: a half-applied refresh would leave the analyzer or the
        scanner re-reading a file for nothing, never worse, but there is no reason to allow it.
        """
        old_mtime, old_size = before.st_mtime, before.st_size
        new_mtime, new_size = after.st_mtime, after.st_size
        conn = self._connect()
        try:
            conn.begin()
            with conn.cursor() as cursor:
                cursor.execute(RECORD_SQL, (row['bpm'], 'written', now, row['track_uid'], row['bpm']))
                cursor.execute(REFRESH_BPM_SQL, (new_mtime, new_size, row['track_uid'], old_mtime, old_size))
                cursor.execute(REFRESH_MEDIA_SQL, (new_mtime, new_size, row['media_id'], old_mtime, old_size))
                cursor.execute(PROCESSED_SQL, (row['file_path'],))
                processed = cursor.fetchone()
                if processed:
                    stored = processed['mtime'] if isinstance(processed, dict) else processed[0]
                    flagged = processed['needs_rescan'] if isinstance(processed, dict) else processed[1]
                    # A row that was up to date stays up to date; one that was queued or already
                    # behind the file is left for the tagger to handle as it would have.
                    if not flagged and stored is not None and not changed_on_disk(old_mtime, float(stored)):
                        cursor.execute(REFRESH_PROCESSED_SQL, (new_mtime, row['file_path']))
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except Exception as rollback_error:  # pylint: disable=broad-except
                logger.warning('Rolling back the BPM tag bookkeeping failed: %s', rollback_error)
            raise
        finally:
            conn.close()


# ----------------------------------------------------------------------------- the round

#: Files written between two pauses; the pause is the tagger's own (TAGGER_BATCH_PAUSE).
SLICE = 24
DEFAULT_PAUSE_SECONDS = 0.5


@dataclass
class RoundResult:
    """What one round did, by outcome, for its summary line."""

    counts: dict[str, int] = field(default_factory=dict)
    folders: list[str] = field(default_factory=list)
    skipped: str | None = None

    def count(self, outcome: str) -> None:
        """Count one file under `outcome`."""
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    @property
    def handled(self) -> int:
        """Files the round looked at."""
        return sum(self.counts.values())


class BpmTagWriteback:
    """One capped round of BPM tag writes; see the module docstring."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # injectable for tests
        self,
        store: BpmTagStore | None = None,
        settings: Callable[[], dict] | None = None,
        roots: Callable[[], list[str]] | None = None,
        notify: Callable[[list[str]], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        pause_seconds: float = DEFAULT_PAUSE_SECONDS,
        now: Callable[[], datetime] = datetime.now,
    ):
        self.store = store or BpmTagStore()
        self._settings = settings or read_settings
        self._roots = roots or library_roots
        self._notify = notify
        self._sleep = sleep
        self.pause_seconds = pause_seconds
        self._now = now

    def _notify_folders(self, folders: list[str]) -> None:
        if not folders:
            return
        notify = self._notify
        if notify is None:
            # pylint: disable-next=import-outside-toplevel
            from services.common.Helpers.LmsScanTrigger import lms_scan_trigger

            notify = lms_scan_trigger.notify
        # One notify per folder, as the tagger does; the trigger's queue merges them.
        for folder in folders:
            try:
                notify([folder])
            except Exception as e:  # pylint: disable=broad-except  # never fails the round
                logger.warning('Could not tell LMS about %s: %s', folder, e)

    def run_round(self, should_stop: Callable[[], bool] = lambda: False) -> RoundResult:
        """Reconcile up to `bpm_tag_writeback_per_round` files. Never raises for one file."""
        result = RoundResult()
        config = self._settings()
        if not config['bpm_tag_writeback_enabled']:
            result.skipped = 'off'
            return result
        if config['bpm_tag_writeback_paused']:
            result.skipped = 'paused'
            return result
        limit = config['bpm_tag_writeback_per_round']
        roots = self._roots()
        if limit <= 0 or not roots:
            result.skipped = 'nothing to do'
            return result
        rows = self.store.due(config, roots, limit)
        written_since_pause = 0
        folders: dict[str, None] = {}
        for row in rows:
            if should_stop():
                break
            outcome = self._handle(row)
            result.count(outcome)
            if outcome == 'written':
                folders[str(Path(row['file_path']).parent)] = None
                written_since_pause += 1
                if written_since_pause >= SLICE and self.pause_seconds > 0 and not should_stop():
                    self._sleep(self.pause_seconds)
                    written_since_pause = 0
        result.folders = list(folders)
        self._notify_folders(result.folders)
        if result.handled:
            self._log_summary(result, config, roots)
        return result

    def _log_summary(self, result: RoundResult, config: dict, roots: list[str]) -> None:
        try:
            remaining: int | str = self.store.remaining(config, roots)
        except Exception as e:  # pylint: disable=broad-except  # a count is not worth failing for
            logger.debug('Could not count the remaining BPM tags: %s', e)
            remaining = 'unknown'
        counts = ', '.join(f'{outcome} {count}' for outcome, count in sorted(result.counts.items()))
        logger.info('BPM tags: %s; %s file(s) still to reconcile', counts, remaining)

    def _handle(self, row: dict) -> str:  # pylint: disable=too-many-return-statements  # one per outcome
        """Reconcile one file; the outcome is also what gets stamped (except `stale`)."""
        path = str(row['file_path'])
        now = self._now()
        try:
            before = os.stat(path)
        except FileNotFoundError:
            return self._record(row, 'missing', now)
        except OSError as e:
            logger.info('BPM tag: cannot stat %s: %s', path, e)
            return self._record(row, 'failed', now)
        if not _same_file(row, before):
            # Changed since the scanner and the analyzer saw it: the measurement may not be this
            # file's. Left queued, not stamped; the scanner notices, the analyzer measures again.
            return 'stale'
        try:
            existing = read_bpm_tag(path)
            decision = decide(existing, float(row['bpm']))
            if not decision.write:
                return self._record(row, decision.reason, now)
            write_bpm_tag(path, decision.value)
            after = os.stat(path)
        except UnsupportedFormat:
            return self._record(row, 'unsupported', now)
        except Exception as e:  # pylint: disable=broad-except  # mutagen raises many kinds
            # INFO, not WARNING: every WARNING is a push to the phone, and one unreadable file
            # is not news. It is stamped, so it is not retried until it is measured again.
            logger.info('BPM tag: could not write %s: %s: %s', path, type(e).__name__, e)
            return self._record(row, 'failed', now)
        try:
            self.store.record_written(row, before, after, now)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning('BPM tag written to %s but not recorded: %s', path, e)
        logger.debug('BPM tag %s -> %s (%s) on %s', existing, decision.value, decision.reason, path)
        return 'written'

    def _record(self, row: dict, action: str, now: datetime) -> str:
        try:
            self.store.record(row, action, now)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning('Could not record the BPM tag outcome %s for %s: %s', action, row.get('file_path'), e)
        return action


def _same_file(row: dict, stat: os.stat_result) -> bool:
    """Whether the file on disk is the one that was measured (mtime and size as stored)."""
    try:
        return float(row['file_mtime']) == stat.st_mtime and int(row['file_size']) == stat.st_size
    except (TypeError, ValueError, KeyError):
        return False
