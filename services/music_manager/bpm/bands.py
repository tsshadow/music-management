"""Which octave a measured tempo belongs in, decided by the track's genre.

docs/designs/bpm-browse/technical.md, "Octave folding". An autocorrelation cannot tell a
150 BPM hardstyle kick from a 75 BPM half-time feel or an uptempo track at 210 from its own
105 -- the pulse is periodic at all of them. What decides it is the genre: hardstyle plays
between roughly 135 and 175, uptempo between 180 and 260. `fold_into_band` moves an estimate
by a factor of two until it lands in the band of the track's genres, and says whether it had
to.

Every band is narrower than an octave (hi < 2 * lo), so at most one octave of any tempo fits
in it and the fold is unambiguous. Bands are matched on `rules_genres.name`, lower-cased;
a track with several genres gets the intersection of their bands, or the narrowest one when
they do not overlap (a hardstyle track that is also tagged hardcore sits where both agree,
150-175). A track without any known genre gets `DEFAULT_BAND`: only the half-time readings
below it are doubled, because in this collection a 75 is almost always a 150 and there is
no genre to argue otherwise.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

#: (low, high) in BPM per genre name. Proposed defaults from the genres' usual tempo ranges,
#: checked against the evaluation set (tools/bpm_eval.py); not a curated table yet.
GENRE_BANDS: dict[str, tuple[float, float]] = {
    # The hardstyle family.
    'hardstyle': (135.0, 175.0),
    'euphoric hardstyle': (140.0, 165.0),
    'mainstream hardstyle': (140.0, 165.0),
    'raw hardstyle': (145.0, 175.0),
    'rawstyle': (145.0, 175.0),
    'reverse bass': (140.0, 165.0),
    'jumpstyle': (135.0, 155.0),
    'jump': (135.0, 155.0),
    'hard dance': (135.0, 175.0),
    'hardbass': (140.0, 175.0),
    'freestyle': (140.0, 165.0),
    # The hardcore family.
    'hardcore': (150.0, 245.0),
    'mainstream hardcore': (160.0, 215.0),
    'hardcore techno': (150.0, 245.0),
    'early hardcore': (150.0, 200.0),
    'millennium hardcore': (160.0, 200.0),
    'gabber': (160.0, 240.0),
    'gabba': (160.0, 240.0),
    'melodic hardcore': (150.0, 200.0),
    'crossbreed': (165.0, 185.0),
    'hardtek': (165.0, 195.0),
    'industrial': (140.0, 230.0),
    'industrial hardcore': (140.0, 230.0),
    'happy hardcore': (160.0, 190.0),
    'uk hardcore': (160.0, 190.0),
    'frenchcore': (175.0, 240.0),
    'euphoric frenchcore': (180.0, 230.0),
    'krach': (180.0, 240.0),
    'uptempo hardcore': (180.0, 260.0),
    'uptempo': (180.0, 260.0),
    'hardcore uptempo': (180.0, 260.0),
    'bouncy uptempo': (180.0, 260.0),
    'zaagtempo': (190.0, 260.0),
    'terror': (200.0, 350.0),
    'terrorcore': (200.0, 350.0),
    'speedcore': (250.0, 480.0),
    # Everything else the collection holds in any number.
    'hard techno': (135.0, 170.0),
    'hardtechno': (135.0, 170.0),
    'techno': (120.0, 160.0),
    'tekno': (160.0, 200.0),
    'trance': (125.0, 150.0),
    'hard trance': (135.0, 160.0),
    'psytrance': (135.0, 150.0),
    'tech trance': (130.0, 150.0),
    'house': (115.0, 135.0),
    'deep house': (110.0, 128.0),
    'deephouse': (110.0, 128.0),
    'melodic house': (110.0, 128.0),
    'tech house': (120.0, 135.0),
    'progressive house': (118.0, 135.0),
    'electro house': (122.0, 135.0),
    'bass house': (120.0, 135.0),
    'big room': (124.0, 150.0),
    'dance': (110.0, 160.0),
    "drum 'n bass": (160.0, 185.0),
    'drum and bass': (160.0, 185.0),
    'drum & bass': (160.0, 185.0),
    'jungle': (155.0, 180.0),
    'dubstep': (130.0, 155.0),
    'riddim': (135.0, 155.0),
    'hip hop': (70.0, 115.0),
    'hip-hop': (70.0, 115.0),
    'rap': (70.0, 115.0),
}

#: The band for a track whose genres are all unknown: only half-time readings are doubled.
DEFAULT_BAND: tuple[float, float] = (88.0, 250.0)

#: The factors tried when folding, nearest first.
_FACTORS = (1.0, 2.0, 0.5, 4.0, 0.25)


@dataclass(frozen=True)
class Folded:
    """A tempo after folding, the band it was folded into, and whether that changed it."""

    bpm: float
    band: tuple[float, float]
    octave_corrected: bool
    #: False when no octave of the estimate fits in the band; `bpm` is then the nearest one.
    in_band: bool
    #: True when the band came from DEFAULT_BAND rather than a genre.
    default_band: bool


def band_for_genres(genres: Iterable[str]) -> tuple[float, float] | None:
    """The band the named genres agree on, the narrowest when they disagree, None when unknown."""
    bands = [GENRE_BANDS[name] for name in {(g or '').strip().lower() for g in genres} if name in GENRE_BANDS]
    if not bands:
        return None
    low = max(b[0] for b in bands)
    high = min(b[1] for b in bands)
    if low < high:
        return (low, high)
    return min(bands, key=lambda b: b[1] / b[0])


def _log_distance(bpm: float, band: tuple[float, float]) -> float:
    """How far `bpm` lies outside `band`, in octaves (0 inside)."""
    low, high = band
    if bpm < low:
        return math.log2(low / bpm)
    if bpm > high:
        return math.log2(bpm / high)
    return 0.0


def fold_into_band(bpm: float, band: tuple[float, float] | None) -> Folded:
    """Move `bpm` by a power of two into `band` (DEFAULT_BAND when None), nearest octave first."""
    default = band is None
    target = DEFAULT_BAND if band is None else band
    for factor in _FACTORS:
        candidate = bpm * factor
        if target[0] <= candidate <= target[1]:
            return Folded(round(candidate, 2), target, factor != 1.0, True, default)
    nearest = min((bpm * f for f in _FACTORS), key=lambda c: (_log_distance(c, target), abs(math.log2(c / bpm))))
    return Folded(round(nearest, 2), target, nearest != bpm, False, default)
