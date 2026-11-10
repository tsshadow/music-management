"""Choose the octave of every stored measurement again, without re-measuring the audio.

docs/designs/bpm-octave/technical.md, "Refold". A measurement's raw estimate (and, once measured
with bug report 140's worker, its comb scores) is stored, so a better rule or fresher priors can
be applied to the whole table from the database alone: `refold()` streams every `ok` row with its
evidence, runs `octave.choose_octave`, and writes back only the rows whose outcome changed. The
bpm-analyzer runs it at start and after the daily priors recompute; a row's `fold_version` says
which rule chose it.

The same inputs serve the worker when it measures a batch (`evidence_for`), so a fresh measurement
and a refolded one are decided identically.

Run by hand as a dry run -- nothing is written, not even the priors -- to see what a change
would do on a database:

    python -m services.music_manager.bpm.refold --dry-run [--sample 20]
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from services.music_manager.bpm import getsongbpm, octave
from services.music_manager.bpm.effective import GENRE_SEPARATOR, split_genres
from services.music_manager.bpm.priors import HARD_GENRES, Priors

logger = logging.getLogger('music-manager.bpm')

#: Every `ok` measurement with the evidence its octave is chosen on. Correlated subqueries rather
#: than joins so a track's genres and labels do not multiply each other. `{where}` is fixed SQL
#: only (a run of `%s` for track ids).
FOLD_INPUTS_SQL = f"""
    SELECT b.track_uid, t.id AS track_id, b.raw_bpm, b.raw_confidence, b.confidence,
           b.strength, b.half_score, b.double_score,
           b.bpm, b.octave_corrected, b.fold_evidence, b.fold_margin, b.fold_version, b.external_bpm,
           t.primary_artist_id, t.title,
           (SELECT a.name FROM library_artists a WHERE a.id = t.primary_artist_id) AS artist_name,
           (SELECT mf.file_path FROM library_media_files mf WHERE mf.track_id = t.id
            ORDER BY mf.id LIMIT 1) AS file_path,
           (SELECT GROUP_CONCAT(g.name SEPARATOR '{GENRE_SEPARATOR}') FROM library_track_genres tg
            JOIN rules_genres g ON g.id = tg.genre_id WHERE tg.track_id = t.id) AS genres,
           (SELECT GROUP_CONCAT(tl.label_id) FROM library_track_labels tl
            WHERE tl.track_id = t.id) AS labels
    FROM library_track_bpm b
    JOIN library_tracks t ON t.track_uid = b.track_uid
    WHERE b.status = 'ok' AND b.raw_bpm IS NOT NULL{{where}}
"""

#: The evidence of tracks about to be measured (they may have no library_track_bpm row yet).
EVIDENCE_SQL = f"""
    SELECT t.id AS track_id, t.primary_artist_id, t.title,
           (SELECT a.name FROM library_artists a WHERE a.id = t.primary_artist_id) AS artist_name,
           (SELECT GROUP_CONCAT(g.name SEPARATOR '{GENRE_SEPARATOR}') FROM library_track_genres tg
            JOIN rules_genres g ON g.id = tg.genre_id WHERE tg.track_id = t.id) AS genres,
           (SELECT GROUP_CONCAT(tl.label_id) FROM library_track_labels tl
            WHERE tl.track_id = t.id) AS labels
    FROM library_tracks t
    WHERE t.id IN ({{placeholders}})
"""

#: Write one refolded row, unless a new measurement replaced its raw estimate meanwhile.
UPDATE_SQL = """
    UPDATE library_track_bpm
    SET bpm = %s, confidence = %s, raw_confidence = %s, octave_corrected = %s,
        fold_evidence = %s, fold_margin = %s, fold_version = %s, external_bpm = %s
    WHERE track_uid = %s AND raw_bpm <=> %s
"""

FETCH_BATCH = 2000
WRITE_BATCH = 1000


def _float(value: Any) -> float | None:
    """`value` as a float, None when it is NULL or unreadable."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evidence_from(
    row: dict,
    priors: Priors,
    file_path: str | None = None,
    external: Mapping[str, float] | None = None,
) -> octave.Evidence:
    """The octave evidence of one row shaped like FOLD_INPUTS_SQL / EVIDENCE_SQL.

    `external` maps a GetSongBPM lookup key to its cached tempo (issue #152); empty or None while
    the GetSongBPM key is not set. It is only read for a track with weak priors.
    """
    labels = [label for label in str(row.get('labels') or '').split(',') if label.strip()]
    evidence = octave.Evidence(
        genres=split_genres(row.get('genres')),
        root=octave.root_of(file_path if file_path is not None else row.get('file_path')),
        label=priors.best_label(labels),
        artist=priors.for_artist(row.get('primary_artist_id')),
        genre_priors=priors.genre,
    )
    prior = getsongbpm.evidence_prior(row, evidence, external or {})
    return evidence if prior is None else replace(evidence, external=prior)


def scores_from(row: dict) -> octave.Scores | None:
    """The stored comb scores, None for a row measured before they were kept."""
    strength = _float(row.get('strength'))
    if strength is None:
        return None
    return octave.Scores(strength, _float(row.get('half_score')), _float(row.get('double_score')))


def raw_confidence_of(row: dict) -> float | None:
    """The estimator's own confidence: `raw_confidence`, else `confidence` for an older row."""
    value = _float(row.get('raw_confidence'))
    return value if value is not None else _float(row.get('confidence'))


def choose(row: dict, priors: Priors, external: Mapping[str, float] | None = None) -> octave.Choice:
    """The octave choice for one FOLD_INPUTS_SQL row."""
    return octave.choose_octave(
        float(row['raw_bpm']), raw_confidence_of(row), evidence_from(row, priors, external=external), scores_from(row)
    )


def _stored(row: dict) -> tuple:
    """The part of a row a refold compares, normalised like `_outcome`."""
    return (
        round(float(row['bpm']), 2) if row.get('bpm') is not None else None,
        round(float(row['confidence']), 3) if row.get('confidence') is not None else None,
        int(bool(row.get('octave_corrected'))),
        row.get('fold_evidence'),
        round(float(row['fold_margin']), 3) if row.get('fold_margin') is not None else None,
        row.get('fold_version'),
        row.get('raw_confidence') is not None,
        round(float(row['external_bpm']), 2) if row.get('external_bpm') is not None else None,
    )


def _outcome(choice: octave.Choice) -> tuple:
    return (
        choice.bpm,
        choice.confidence,
        int(choice.octave_corrected),
        choice.evidence,
        round(choice.margin, 3),
        octave.FOLD_VERSION,
        True,
        choice.external_bpm,
    )


@dataclass
class RefoldResult:
    """What one refold pass found, and did."""

    rows: int = 0
    changed: int = 0
    bpm_changed: int = 0
    written: int = 0
    above_200_before: int = 0
    above_200_after: int = 0
    above_200_soft_before: int = 0
    above_200_soft_after: int = 0
    below_70_before: int = 0
    below_70_after: int = 0
    reliable_before: int = 0
    reliable_after: int = 0
    ambiguous: int = 0
    folded_confident_raw_before: int = 0
    decided_by: Counter = field(default_factory=Counter)
    samples: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        """For the dry run's JSON output."""
        return {**self.__dict__, 'decided_by': dict(self.decided_by)}


def _stream(cursor, fetch_batch: int = FETCH_BATCH) -> Iterator[dict]:
    while True:
        chunk = cursor.fetchmany(fetch_batch)
        if not chunk:
            return
        yield from chunk


def _unbuffered_cursor(conn):
    """A streaming cursor where pymysql provides one, else the connection's default cursor."""
    try:
        import pymysql.cursors  # pylint: disable=import-outside-toplevel

        cursor_class = pymysql.cursors.SSDictCursor
        if isinstance(cursor_class, type):
            return conn.cursor(cursor_class)
    except (ImportError, AttributeError):
        pass
    return conn.cursor()


def compare(
    rows: Iterable[dict],
    priors: Priors,
    reliable: float = 0.75,
    sample: int = 0,
    seed: int = 140,
    external: Mapping[str, float] | None = None,
) -> tuple[list[tuple], RefoldResult]:
    """(UPDATE_SQL rows for what changed, the tally) over FOLD_INPUTS_SQL `rows`."""
    result = RefoldResult()
    updates: list[tuple] = []
    hard = set(HARD_GENRES)
    rng = random.Random(seed)
    for row in rows:
        result.rows += 1
        choice = choose(row, priors, external)
        before = _float(row.get('bpm'))
        soft = not any(g.lower() in hard for g in split_genres(row.get('genres')))
        result.above_200_before += bool(before and before > 200)
        result.above_200_after += choice.bpm > 200
        result.above_200_soft_before += bool(before and before > 200 and soft)
        result.above_200_soft_after += choice.bpm > 200 and soft
        result.below_70_before += bool(before and before < 70)
        result.below_70_after += choice.bpm < 70
        result.reliable_before += (_float(row.get('confidence')) or 0.0) >= reliable
        result.reliable_after += choice.confidence >= reliable
        result.ambiguous += choice.ambiguous
        result.folded_confident_raw_before += (
            bool(row.get('octave_corrected')) and (raw_confidence_of(row) or 0.0) >= reliable
        )
        if _stored(row) == _outcome(choice):
            continue
        result.changed += 1
        if before is None or abs(before - choice.bpm) > 0.005:
            result.bpm_changed += 1
            result.decided_by[choice.evidence] += 1
            if sample:
                view = {
                    'track_id': row.get('track_id'),
                    'file_path': row.get('file_path'),
                    'genres': row.get('genres'),
                    'raw_bpm': _float(row.get('raw_bpm')),
                    'before': before,
                    'after': choice.bpm,
                    'confidence_before': _float(row.get('confidence')),
                    'confidence_after': choice.confidence,
                    'evidence': choice.evidence,
                    'margin': choice.margin,
                }
                # Reservoir sampling: a uniform sample of the changes in one pass.
                if len(result.samples) < sample:
                    result.samples.append(view)
                else:
                    slot = rng.randrange(result.bpm_changed)
                    if slot < sample:
                        result.samples[slot] = view
        updates.append(
            (
                choice.bpm,
                choice.confidence,
                raw_confidence_of(row),
                int(choice.octave_corrected),
                choice.evidence,
                round(choice.margin, 3),
                octave.FOLD_VERSION,
                choice.external_bpm,
                row['track_uid'],
                row['raw_bpm'],
            )
        )
    return updates, result


def inputs_sql(track_ids: list[int] | None) -> str:
    """FOLD_INPUTS_SQL over every row, or over the given track ids (bound as parameters)."""
    if track_ids is None:
        return FOLD_INPUTS_SQL.format(where='')
    return FOLD_INPUTS_SQL.format(where=f'\n      AND t.id IN ({", ".join(["%s"] * len(track_ids))})')


def refold(
    connect: Callable[[], Any],
    priors: Priors,
    *,
    track_ids: Iterable[int] | None = None,
    dry_run: bool = False,
    reliable: float = 0.75,
    sample: int = 0,
    external: Mapping[str, float] | None = None,
) -> RefoldResult:
    """Choose every (or the given tracks') octave again; write the changes unless `dry_run`.

    `external` is the GetSongBPM tempo cache (`getsongbpm.load_tempos`), empty while it is off.
    """
    ids = None if track_ids is None else sorted({int(i) for i in track_ids})
    if ids is not None and not ids:
        return RefoldResult()
    conn = connect()
    if not conn:
        raise RuntimeError('database connection failed')
    try:
        cursor = _unbuffered_cursor(conn)
        try:
            cursor.execute(inputs_sql(ids), ids or [])
            updates, result = compare(_stream(cursor), priors, reliable=reliable, sample=sample, external=external)
        finally:
            cursor.close()
    finally:
        conn.close()
    if updates and not dry_run:
        conn = connect()
        if not conn:
            raise RuntimeError('database connection failed')
        try:
            with conn.cursor() as cursor:
                for start in range(0, len(updates), WRITE_BATCH):
                    cursor.executemany(UPDATE_SQL, updates[start : start + WRITE_BATCH])
            conn.commit()
        finally:
            conn.close()
        result.written = len(updates)
    return result


def evidence_for(connect: Callable[[], Any], track_ids: list[int]) -> dict[int, dict]:
    """EVIDENCE_SQL rows by track id, for a batch the worker is about to measure."""
    if not track_ids:
        return {}
    conn = connect()
    if not conn:
        raise RuntimeError('database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(EVIDENCE_SQL.format(placeholders=', '.join(['%s'] * len(track_ids))), list(track_ids))
            return {int(row['track_id']): row for row in cursor.fetchall()}
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> None:
    """`--dry-run`: compute the priors in memory, refold everything, print what would change."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n', maxsplit=1)[0])
    parser.add_argument('--dry-run', action='store_true', help='write nothing (the only mode offered by hand)')
    parser.add_argument('--sample', type=int, default=20, help='how many changed rows to print')
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error('only --dry-run is supported by hand; the bpm-analyzer applies the refold itself')
    # pylint: disable-next=import-outside-toplevel
    from services.music_manager.bpm import priors as priors_module
    from services.music_manager.database import get_db_connection  # pylint: disable=import-outside-toplevel

    computed = priors_module.as_priors(priors_module.compute(get_db_connection))
    result = refold(get_db_connection, computed, dry_run=True, sample=args.sample)
    print(json.dumps({'priors': computed.coverage(), **result.as_dict()}, indent=2, default=str))


if __name__ == '__main__':
    main()
