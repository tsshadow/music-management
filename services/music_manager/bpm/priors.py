"""Learned tempo priors: where a label's, an artist's and a genre's confident measurements sit.

docs/designs/bpm-octave/technical.md, "Priors". The octave choice (`octave.py`) asks "is this
track more likely 115 or 230?", and the collection itself answers it best: labels here are very
genre-pure (Scantraxx sits at ~150, Masters of Hardcore at ~180-200), and an artist's own tracks
mostly share a tempo. So once a day the bpm-analyzer recomputes, per key, the mean and standard
deviation of log2(BPM) over the *training rows*, and stores them in `library_bpm_priors`.

Training rows are measurements that are unlikely to be octave errors themselves:

- `status = 'ok'` and an estimator confidence (`raw_confidence`, else `confidence` for rows from
  before bug report 140) of at least `TRAINING_MIN_CONFIDENCE`;
- the raw estimate -- the estimator's own pick, before any folding, so no hand-set band leaks in
  -- and only when it lies in `TRAINING_BPM` (88-200), where neither a half-time reading (a 75
  hardstyle, an 87 drum 'n bass) nor a doubled one (a 234 pop song) can be, *unless* the track has
  a genre of its own whose tempos legitimately exceed 200 (`HARD_GENRES`: uptempo, terror, ...).

Per kind:

- `label`: every label of the track (`library_track_labels`).
- `artist`: the primary artist, over their *own* tracks only -- a title marking a remix, bootleg,
  edit of another style etc. (`REMIX_PATTERN`) is left out. This is what keeps André Hazes's
  hardstyle remixes from deciding the tempo of his ballads. One more kind of row counts here: a
  confident raw estimate above 200 on a track without any genre, outside the mainstream folders
  (`octave.MAINSTREAM_ROOTS`). Without it a genre-less uptempo producer's prior would be built
  from their half-time readings alone and fold their real 210s down; with it the evaluation set
  reaches its octave ceiling. (The same extension for labels made one uptempo label double its
  130 BPM tracks, so labels keep the plain window.) An artist's prior can still never double a
  track into hard dance on its own -- `octave.FOLD_UP_LIMIT`.
- `genre`: every genre of the track, by lower-cased name.
- `folder`: the uploader folder of a Soundcloud or YouTube upload (`octave.folder_key`, issue
  #241), over every upload in it, with the artist's extra fast genre-less rows. Applied leave-one-
  out: `Priors.for_folder` takes the track's own training row back out of the stored statistics
  (`without`), so a track never votes for its own octave.

The statistics are trimmed once: a first mean per key, then mean and spread over the rows within
`TRIM_OCTAVES` of it, so a stray half-time reading does not drag a label's centre. Keys with fewer
than `MIN_SAMPLES` trimmed rows are not stored; `octave.py` has its own, higher, thresholds per kind.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from services.music_manager.bpm.bands import GENRE_BANDS
from services.music_manager.bpm.octave import (
    FOLDER_KEY_LENGTH,
    MAINSTREAM_ROOTS,
    MUSIC_ROOT,
    UPLOADER_ROOTS,
    Prior,
    folder_key,
)

logger = logging.getLogger('music-manager.bpm')

TABLE = 'library_bpm_priors'
KIND_LABEL = 'label'
KIND_ARTIST = 'artist'
KIND_GENRE = 'genre'
KIND_FOLDER = 'folder'
KINDS = (KIND_LABEL, KIND_ARTIST, KIND_GENRE, KIND_FOLDER)

TRAINING_MIN_CONFIDENCE = 0.75
TRAINING_BPM = (88.0, 200.0)
TRIM_OCTAVES = 0.5
MIN_SAMPLES = 5

#: Genres whose tempos legitimately exceed 200 BPM: a training row above TRAINING_BPM is kept
#: when the track carries one of them. The genres whose hand-set band reaches above 200.
HARD_GENRES = tuple(sorted(name for name, (_, high) in GENRE_BANDS.items() if high > 200))

#: A title that marks someone else's take on the artist's track (MariaDB REGEXP, PCRE).
REMIX_PATTERN = (
    r'(?i)[([][^)\]]*\b(remix|rmx|bootleg|rework|refix|flip|mash ?-?up|remake|cover|vip|re-?edit'
    r'|uptempo|hardstyle|hardcore|frenchcore|rawstyle|terror)\b'
)

#: The uploader folder of a track's first file, as `octave.folder_key` spells it (before the
#: lower-casing, which the collation makes moot): the two folders under the music root.
_FOLDER_KEY_SQL = (
    f"LEFT(SUBSTRING(SUBSTRING_INDEX(fm.file_path, '/', {MUSIC_ROOT.rstrip('/').count('/') + 3}), "
    f'{len(MUSIC_ROOT.rstrip("/")) + 2}), {FOLDER_KEY_LENGTH})'
)

#: The key column and joins per kind. Fixed SQL only; every value is a bound parameter.
_KEY_SQL = {
    KIND_LABEL: ('tl.label_id', 'JOIN library_track_labels tl ON tl.track_id = t.id', ''),
    KIND_ARTIST: (
        't.primary_artist_id',
        '',
        " AND t.primary_artist_id IS NOT NULL AND NOT (IFNULL(t.title, '') REGEXP %s)",
    ),
    KIND_GENRE: (
        'LOWER(kg.name)',
        'JOIN library_track_genres ktg ON ktg.track_id = t.id JOIN rules_genres kg ON kg.id = ktg.genre_id',
        '',
    ),
    KIND_FOLDER: (
        _FOLDER_KEY_SQL,
        'JOIN library_media_files fm'
        ' ON fm.id = (SELECT MIN(m2.id) FROM library_media_files m2 WHERE m2.track_id = t.id)',
        ' AND ({uploaders})',
    ),
}

#: The artist's extra training rows: a fast raw estimate on a genre-less track outside the
#: mainstream folders. `{roots}` is one LIKE per MAINSTREAM_ROOTS folder.
FAST_GENRELESS_SQL = """
               OR (b.raw_bpm > %s
                   AND NOT EXISTS (SELECT 1 FROM library_track_genres tg3 WHERE tg3.track_id = t.id)
                   AND NOT EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id
                                   AND ({roots})))"""

PRIORS_SQL = """
    WITH training AS (
        SELECT {key} AS k, LOG2(b.raw_bpm) AS x
        FROM library_track_bpm b
        JOIN library_tracks t ON t.track_uid = b.track_uid
        {join}
        WHERE b.status = 'ok' AND b.raw_bpm IS NOT NULL
          AND COALESCE(b.raw_confidence, b.confidence) >= %s{extra}
          AND (b.raw_bpm BETWEEN %s AND %s
               OR EXISTS (SELECT 1 FROM library_track_genres tg
                          JOIN rules_genres g ON g.id = tg.genre_id
                          WHERE tg.track_id = t.id AND LOWER(g.name) IN ({hard})){fast})
    ),
    first_pass AS (
        SELECT k, AVG(x) AS mu FROM training GROUP BY k HAVING COUNT(*) >= %s
    )
    SELECT training.k AS prior_key, COUNT(*) AS samples, AVG(training.x) AS centre,
           STDDEV_POP(training.x) AS spread
    FROM training JOIN first_pass ON first_pass.k = training.k
    WHERE ABS(training.x - first_pass.mu) <= %s
    GROUP BY training.k
    HAVING COUNT(*) >= %s
"""

UPSERT_SQL = f"""
    INSERT INTO {TABLE} (kind, prior_key, centre, spread, samples, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE centre = VALUES(centre), spread = VALUES(spread),
                            samples = VALUES(samples), updated_at = VALUES(updated_at)
"""

#: Keys that no longer qualify: whatever the recompute did not touch.
PRUNE_SQL = f'DELETE FROM {TABLE} WHERE kind = %s AND updated_at < %s'

LOAD_SQL = f'SELECT kind, prior_key, centre, spread, samples FROM {TABLE}'

LAST_UPDATE_SQL = f'SELECT MAX(updated_at) AS updated_at FROM {TABLE}'

WRITE_BATCH = 1000


def _uploader_patterns() -> list[str]:
    """One LIKE pattern per uploader root: a file at least one folder below it."""
    root = MUSIC_ROOT.rstrip('/')
    return [f'{root}/{folder}/%/%' for folder in sorted(UPLOADER_ROOTS)]


def _mainstream_patterns() -> list[str]:
    """One LIKE pattern per mainstream folder (the collation makes LIKE case-insensitive)."""
    root = MUSIC_ROOT.rstrip('/')
    return [f'{root}/{folder}/%' for folder in sorted(MAINSTREAM_ROOTS)]


def priors_sql(kind: str) -> tuple[str, list]:
    """The statement that computes one kind's priors, and its parameters."""
    key, join, extra = _KEY_SQL[kind]
    patterns = _mainstream_patterns() if kind in (KIND_ARTIST, KIND_FOLDER) else []
    fast = FAST_GENRELESS_SQL.format(roots=' OR '.join(['mf.file_path LIKE %s'] * len(patterns))) if patterns else ''
    uploaders = _uploader_patterns() if kind == KIND_FOLDER else []
    extra = extra.format(uploaders=' OR '.join(['fm.file_path LIKE %s'] * len(uploaders)))
    sql = PRIORS_SQL.format(key=key, join=join, extra=extra, hard=', '.join(['%s'] * len(HARD_GENRES)), fast=fast)
    params: list = [TRAINING_MIN_CONFIDENCE]
    if kind == KIND_ARTIST:
        params.append(REMIX_PATTERN)
    params += uploaders
    params += [*TRAINING_BPM, *HARD_GENRES]
    if patterns:
        params += [TRAINING_BPM[1], *patterns]
    params += [MIN_SAMPLES, TRIM_OCTAVES, MIN_SAMPLES]
    return sql, params


@dataclass
class Priors:
    """Every learned prior, by kind: label and artist by id, genre and folder by lower-cased name."""

    label: dict[int, Prior] = field(default_factory=dict)
    artist: dict[int, Prior] = field(default_factory=dict)
    genre: dict[str, Prior] = field(default_factory=dict)
    folder: dict[str, Prior] = field(default_factory=dict)

    def best_label(self, label_ids: Iterable[Any]) -> Prior | None:
        """The prior of the best-sampled of a track's labels, or None when none has one."""
        found = [self.label[int(i)] for i in label_ids if _is_int(i) and int(i) in self.label]
        return max(found, key=lambda p: p.samples) if found else None

    def for_artist(self, artist_id: Any) -> Prior | None:
        """The prior of an artist's own tracks, or None."""
        return self.artist.get(int(artist_id)) if _is_int(artist_id) else None

    def for_folder(self, path: str | None, own: float | None = None) -> Prior | None:
        """The prior of a file's uploader folder, without `own` (the track's training value), or None.

        `own` is LOG2 of the track's raw estimate when the track is one of the folder's training
        rows (`training_value`), None when it is not.
        """
        key = folder_key(path)
        prior = self.folder.get(key) if key else None
        if prior is None or own is None:
            return prior
        return without(prior, own)

    def coverage(self) -> dict[str, int]:
        """How many keys each kind holds, for the log."""
        return {
            KIND_LABEL: len(self.label),
            KIND_ARTIST: len(self.artist),
            KIND_GENRE: len(self.genre),
            KIND_FOLDER: len(self.folder),
        }


def training_value(raw_bpm: Any, raw_confidence: Any, genres: Iterable[str]) -> float | None:
    """LOG2(raw) when a measurement is a training row of its folder's prior, else None.

    The PRIORS_SQL test for an uploader-folder row: confident, and in TRAINING_BPM, or carrying a
    HARD_GENRES genre, or fast without any genre. (The folder never lies under a mainstream root.)
    """
    try:
        raw, confidence = float(raw_bpm), float(raw_confidence)
    except (TypeError, ValueError):
        return None
    if raw <= 0 or confidence < TRAINING_MIN_CONFIDENCE:
        return None
    names = [g.strip().lower() for g in genres if g and g.strip()]
    low, high = TRAINING_BPM
    if low <= raw <= high or any(g in HARD_GENRES for g in names) or (raw > high and not names):
        return math.log2(raw)
    return None


def without(prior: Prior, own: float) -> Prior | None:
    """`prior` with one of its rows (`own`, in log2) taken out; None when too few rows remain.

    The row only counts when it survived the trim -- within TRIM_OCTAVES of the centre, which here
    stands in for the first pass's mean.
    """
    if abs(own - prior.centre) > TRIM_OCTAVES:
        return prior
    remaining = prior.samples - 1
    if remaining < MIN_SAMPLES:
        return None
    centre = (prior.samples * prior.centre - own) / remaining
    square = (prior.samples * (prior.spread**2 + prior.centre**2) - own * own) / remaining
    return Prior(centre, math.sqrt(max(0.0, square - centre * centre)), remaining)


def _is_int(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def from_rows(rows: Iterable[dict]) -> Priors:
    """A Priors from LOAD_SQL rows; a row of an unknown kind or a malformed key is skipped."""
    priors = Priors()
    for row in rows:
        prior = Prior(float(row['centre']), float(row['spread']), int(row['samples']))
        kind, key = row['kind'], row['prior_key']
        if kind in (KIND_GENRE, KIND_FOLDER):
            getattr(priors, kind)[str(key).strip().lower()] = prior
        elif kind in (KIND_LABEL, KIND_ARTIST) and _is_int(key):
            getattr(priors, kind)[int(key)] = prior
    return priors


def load(connect: Callable[[], Any]) -> Priors:
    """Every stored prior."""
    conn = connect()
    if not conn:
        raise RuntimeError('database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(LOAD_SQL)
            return from_rows(cursor.fetchall())
    finally:
        conn.close()


def last_update(connect: Callable[[], Any]) -> datetime | None:
    """When the priors were last recomputed, None when never."""
    conn = connect()
    if not conn:
        raise RuntimeError('database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(LAST_UPDATE_SQL)
            row = cursor.fetchone()
    finally:
        conn.close()
    return row.get('updated_at') if row else None


def compute(connect: Callable[[], Any]) -> dict[str, list[dict]]:
    """Every kind's prior rows as PRIORS_SQL computes them, without storing anything."""
    computed: dict[str, list[dict]] = {}
    for kind in KINDS:
        sql, params = priors_sql(kind)
        conn = connect()
        if not conn:
            raise RuntimeError('database connection failed')
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                computed[kind] = [dict(row) for row in cursor.fetchall() if row['prior_key'] is not None]
        finally:
            conn.close()
    return computed


def as_priors(computed: dict[str, list[dict]]) -> Priors:
    """A Priors from `compute()`'s rows."""
    return from_rows(
        {**row, 'kind': kind, 'spread': row['spread'] or 0.0} for kind, rows in computed.items() for row in rows
    )


def recompute(connect: Callable[[], Any], now: datetime) -> Priors:
    """Recompute and store every kind's priors, and return them.

    Computed first, then written kind by kind: upsert with `now`, then delete that kind's keys
    older than `now` -- the ones that no longer qualify. A failure part-way leaves the previous
    values of the kinds not yet written, never an empty table.
    """
    computed = compute(connect)
    stamp = now.replace(microsecond=0)
    for kind, found in computed.items():
        rows = [
            (kind, str(row['prior_key']), float(row['centre']), float(row['spread'] or 0.0), int(row['samples']), stamp)
            for row in found
        ]
        conn = connect()
        if not conn:
            raise RuntimeError('database connection failed')
        try:
            with conn.cursor() as cursor:
                for start in range(0, len(rows), WRITE_BATCH):
                    cursor.executemany(UPSERT_SQL, rows[start : start + WRITE_BATCH])
                cursor.execute(PRUNE_SQL, (kind, stamp))
            conn.commit()
        finally:
            conn.close()
    priors = as_priors(computed)
    logger.info('bpm: tempo priors recomputed (%s)', ', '.join(f'{k} {v}' for k, v in priors.coverage().items()))
    return priors
