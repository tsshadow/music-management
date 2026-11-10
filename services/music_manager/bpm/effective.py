"""One tempo per track: which of the three BPM sources wins, and how far to trust it.

docs/designs/bpm-browse/technical.md, "Effective BPM". Four places can hold a track's
tempo, and this module is the only one that decides between them:

0. `library_track_bpm_manual` -- a tempo a person set in the track details (bug report 140).
   Always wins, always `high`, and nothing automatic ever overwrites it.
1. `library_track_bpm` -- a measurement at 0.01 BPM by the BPM analysis worker. Its octave is
   already chosen by the worker (`octave.choose_octave`), and its confidence already includes how
   sure that choice is, so it is taken as it is.
2. `library_track_audio_features.bpm_tag` -- the file's BPM tag, as the deprecated
   ml-analyzer read it. Most of these were themselves written by an older librosa pass.
3. `library_track_audio_features.tempo` -- the ml-analyzer's own estimate.

Sources 2 and 3 sit on librosa's coarse lag grid (152.0, 156.6, 161.5, ...), so they are
marked `approximate`, and a value outside the band of the track's genres is folded by a factor
of two into it first (`bands.fold_into_band`): the analyzer's commonest mistake is reading a
hardstyle track at half its tempo.

The confidence is deliberately coarse, three words rather than a number the old data cannot
back up:

- `high`   -- a tempo set by hand, or a measurement at or above `bpm_reliable_confidence`.
- `medium` -- a measurement below it, or a tag the analyzer agrees with (within 2 BPM after
  folding both) that already sat inside a genre's band without folding.
- `low`    -- everything else: a tag or tempo alone, a folded value, or one no genre vouches for.

"Betrouwbaar" in the browse page means medium or better.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from services.music_manager.bpm.bands import band_for_genres, fold_into_band

SOURCE_MANUAL = 'manual'
SOURCE_MEASURED = 'measured'
SOURCE_TAG = 'tag'
SOURCE_ANALYZER = 'analyzer'
#: Not a source of the tempo itself: the prior a measurement's octave was weighed on (issue #152).
SOURCE_GETSONGBPM = 'getsongbpm'

CONFIDENCE_HIGH = 'high'
CONFIDENCE_MEDIUM = 'medium'
CONFIDENCE_LOW = 'low'
#: Order for "at least this confident" comparisons.
CONFIDENCE_RANK = {CONFIDENCE_LOW: 0, CONFIDENCE_MEDIUM: 1, CONFIDENCE_HIGH: 2}

#: A stored value outside this range is noise (a zero tag, a mis-parsed 1500), not a tempo.
VALID_MIN = 40.0
VALID_MAX = 500.0
#: How close tag and analyzer must be, after folding both, to count as agreeing.
AGREEMENT_BPM = 2.0
DEFAULT_RELIABLE_CONFIDENCE = 0.75


@dataclass(frozen=True)
class EffectiveBpm:
    """The tempo the browse shows and filters on, where it came from, and how far to trust it."""

    bpm: float
    source: str
    confidence: str
    folded: bool
    approximate: bool
    #: `getsongbpm` when a measurement's octave was weighed on GetSongBPM's tempo (issue #152):
    #: the details sheet then shows the attribution link GetSongBPM asks for.
    external_source: str | None = None


def _valid(value) -> float | None:
    """`value` as a float when it is a plausible tempo, else None."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if VALID_MIN <= number <= VALID_MAX else None


def resolve(
    *,
    manual: float | None = None,
    measured: float | None = None,
    measured_confidence: float | None = None,
    measured_folded: bool = False,
    measured_external: float | None = None,
    tag: float | None = None,
    tempo: float | None = None,
    genres: Iterable[str] = (),
    reliable_confidence: float = DEFAULT_RELIABLE_CONFIDENCE,
) -> EffectiveBpm | None:
    """The effective BPM from whatever the track has, or None when it has nothing usable."""
    manual_value = _valid(manual)
    if manual_value is not None:
        return EffectiveBpm(
            bpm=round(manual_value, 2),
            source=SOURCE_MANUAL,
            confidence=CONFIDENCE_HIGH,
            folded=False,
            approximate=False,
        )
    measured_value = _valid(measured)
    if measured_value is not None:
        sure = measured_confidence is not None and float(measured_confidence) >= reliable_confidence
        return EffectiveBpm(
            bpm=round(measured_value, 2),
            source=SOURCE_MEASURED,
            confidence=CONFIDENCE_HIGH if sure else CONFIDENCE_MEDIUM,
            folded=bool(measured_folded),
            approximate=False,
            external_source=SOURCE_GETSONGBPM if measured_external is not None else None,
        )

    tag_value = _valid(tag)
    tempo_value = _valid(tempo)
    if tag_value is None and tempo_value is None:
        return None
    band = band_for_genres(genres)
    source, value = (SOURCE_TAG, tag_value) if tag_value is not None else (SOURCE_ANALYZER, tempo_value)
    assert value is not None  # one of the two is set, checked above
    folded = fold_into_band(value, band)

    confidence = CONFIDENCE_LOW
    if source == SOURCE_TAG and tempo_value is not None and band is not None:
        other = fold_into_band(tempo_value, band)
        agree = abs(other.bpm - folded.bpm) <= AGREEMENT_BPM
        if agree and folded.in_band and not folded.octave_corrected:
            confidence = CONFIDENCE_MEDIUM
    return EffectiveBpm(
        bpm=folded.bpm,
        source=source,
        confidence=confidence,
        folded=folded.octave_corrected,
        approximate=True,
    )


#: Separator for the genre names GROUP_CONCAT joins; no curated genre name holds one.
GENRE_SEPARATOR = '|'


def split_genres(joined: str | None) -> tuple[str, ...]:
    """The genre names of a `GROUP_CONCAT(... SEPARATOR '|')` column, empty ones left out."""
    return tuple(g for g in (joined or '').split(GENRE_SEPARATOR) if g)


def resolve_row(row: dict, reliable_confidence: float = DEFAULT_RELIABLE_CONFIDENCE) -> EffectiveBpm | None:
    """`resolve()` for one row shaped like `index.INPUTS_SQL` (manual, measured, bpm_tag, tempo, genres).

    The browse index, the materialised `library_track_effective_bpm` table and the track details
    all read their inputs in that shape, so the column-to-argument mapping lives here once.
    """
    return resolve(
        manual=row.get('manual'),
        measured=row.get('measured'),
        measured_confidence=row.get('measured_confidence'),
        measured_folded=bool(row.get('measured_folded')),
        measured_external=row.get('measured_external'),
        tag=row.get('bpm_tag'),
        tempo=row.get('tempo'),
        genres=split_genres(row.get('genres')),
        reliable_confidence=reliable_confidence,
    )
