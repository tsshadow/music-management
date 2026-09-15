"""A statistic for where a genre sits between soft and hard, and what a track's own
hardness is when nothing tags it directly.

Teun asked for daily mixes spread across the spectrum -- one soft, one in the middle,
one hard -- and for that to mean something, "soft" and "hard" have to be a number, not
a feeling. `rules_genres.hardness` (0-100) is that number, curated the same way genre
state is: seeded from a hand-picked anchor list (proposed defaults, not measured --
see docs/designs/feeds/functional.md, "Daily mixes v2"), inherited by an uncurated
genre from its nearest ancestor in `rules_subgenre_hierarchy`, and editable afterwards
from the genre edit page like any other curated fact.

A track rarely carries a genre with no hardness gap to fill: `track_hardness()` is the
fallback chain for when it does -- the track's own genres, then its label's, then its
primary artist's, then a straight tempo mapping, in that order. It is deliberately a
pure function over numbers a caller has already looked up (`feeds/queries.py` has the
bounded SQL for that), so it can be tested and read without a database, the same
contract as every other module in this package except `build.py`.
"""

from collections import Counter

from services.music_manager.feeds.hierarchy import nearest_ancestor

#: Proposed defaults (docs/designs/feeds/functional.md, "Daily mixes v2"), matched
#: case-insensitively against `rules_genres.name`. Not a measurement: nobody has yet
#: checked these against how the listeners here actually rank a mix by ear. Every
#: other curated genre inherits from the nearest one of these via
#: `rules_subgenre_hierarchy`; anything unreachable from an anchor stays NULL.
ANCHOR_HARDNESS: dict[str, int] = {
    'deep house': 10,
    'house': 12,
    'melodic house': 12,
    'progressive house': 15,
    'electro house': 18,
    'bass house': 20,
    'trance': 15,
    'dance': 18,
    'electronic': 18,
    'rock': 20,
    'rap': 20,
    'trap': 20,
    'dubstep': 30,
    "drum 'n bass": 35,
    'bass': 30,
    'euphoric hardstyle': 30,
    'happy hardcore': 35,
    'hard dance': 35,
    'freestyle': 35,
    'uk hardcore': 40,
    'techno': 40,
    'tekno': 45,
    'hardstyle': 45,
    'mainstream hardstyle': 45,
    'euphoric frenchcore': 55,
    'hard techno': 60,
    'raw hardstyle': 65,
    'hardcore techno': 65,
    'hardcore': 70,
    'mainstream hardcore': 70,
    'gabber': 75,
    'industrial': 78,
    'industrial hardcore': 80,
    'frenchcore': 80,
    'krach': 82,
    'uptempo hardcore': 85,
    'bouncy uptempo': 85,
    'zaagtempo': 88,
    'terror': 95,
    'speedcore': 100,
    'extratone': 100,
    'splittercore': 100,
}

#: Tempo -> hardness anchor points, piecewise linear between them. `tempo_hardness`
#: clamps outside the ends rather than extrapolating: nothing plays much faster than
#: 200 BPM, and nothing this collection tags plays meaningfully slower than a house
#: track hovering under 140.
_TEMPO_POINTS: list[tuple[float, float]] = [
    (140.0, 20.0),
    (150.0, 45.0),
    (160.0, 60.0),
    (175.0, 75.0),
    (190.0, 85.0),
    (200.0, 95.0),
]

#: The band edges a cold-start listener (fewer than this many heard tracks with a
#: known hardness) gets instead of their own, unmeasured percentiles.
MIN_TRACKS_FOR_OWN_BAND = 30
FALLBACK_BAND = (40.0, 70.0)
#: Below this gap, a listener's own p33/p67 are too close together to make three
#: meaningfully different mixes -- median +/- this becomes the band instead.
MIN_BAND_GAP = 15.0

#: A label or artist needs at least this many tracks with a known hardness before its
#: mean is trusted as another track's fallback -- one outlier release must not decide
#: a whole label's hardness.
MIN_TRACKS_FOR_ENTITY_MEAN = 5


def tempo_hardness(tempo: float | None) -> float | None:
    """The tempo-only hardness estimate, or None when there is no tempo at all.

    The last resort in `track_hardness`'s chain -- used only for a track with no
    known-hardness genre, no label mean and no artist mean, which on a curated
    collection like this one should be rare enough that the estimate's coarseness
    never gets much exposure.
    """
    if tempo is None:
        return None
    points = _TEMPO_POINTS
    if tempo <= points[0][0]:
        return points[0][1]
    if tempo >= points[-1][0]:
        return points[-1][1]
    for (t0, h0), (t1, h1) in zip(points, points[1:], strict=False):
        if t0 <= tempo <= t1:
            fraction = (tempo - t0) / (t1 - t0)
            return h0 + fraction * (h1 - h0)
    return None  # unreachable: the two clamps above cover everything outside the table


def track_hardness(
    genre_weighted_sum: float | None,
    genre_weight_sum: float | None,
    label_mean: float | None,
    artist_mean: float | None,
    tempo: float | None,
) -> tuple[float | None, str]:
    """A track's hardness, and which of the four signals actually decided it.

    The chain is genre, then label, then artist, then tempo, then nothing -- each
    step is only reached when the one before it had nothing to say. `genre_weight_sum`
    is a sum of `library_track_genres.weight` restricted to genres with a known
    `hardness`; a track whose only tag is one nobody has scored looks exactly like a
    track with no genre tag at all, which is what lets it fall through.
    """
    if genre_weighted_sum is not None and genre_weight_sum and genre_weight_sum > 0:
        return genre_weighted_sum / genre_weight_sum, 'genre'
    if label_mean is not None:
        return label_mean, 'label'
    if artist_mean is not None:
        return artist_mean, 'artist'
    tempo_value = tempo_hardness(tempo)
    if tempo_value is not None:
        return tempo_value, 'tempo'
    return None, 'none'


def _weighted_percentile(values: list[tuple[float, float]], q: float) -> float:
    """The value at quantile `q` (0-1) of a weighted distribution.

    Sorted by value, walking the cumulative weight until it crosses `q` of the total
    -- the standard "weighted median" construction, generalised to any quantile.
    `values` must be non-empty; the caller (`hardness_band_edges`) is the one place
    that decides when there is not enough data to ask this at all.
    """
    ordered = sorted(values, key=lambda item: item[0])
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2][0]
    target = q * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return value
    return ordered[-1][0]


def hardness_band_edges(weighted_hardness: list[tuple[float, float]]) -> tuple[float, float]:
    """The (soft/mid, mid/hard) edges for one listener's own hardness distribution.

    `weighted_hardness` is one `(hardness, listen_weight)` pair per *distinct* track
    they heard in the profile window that resolved to a known hardness -- the same
    listens `build_profile` reads, weighted the same way. Below
    `MIN_TRACKS_FOR_OWN_BAND` tracks, their own percentiles are not a measurement
    worth acting on, so a cold-start listener gets the same fixed edges everyone else
    without enough history gets, rather than one erratic pair of numbers derived from
    a handful of listens.
    """
    if len(weighted_hardness) < MIN_TRACKS_FOR_OWN_BAND:
        return FALLBACK_BAND
    lo = _weighted_percentile(weighted_hardness, 0.33)
    hi = _weighted_percentile(weighted_hardness, 0.67)
    if hi - lo < MIN_BAND_GAP:
        median = _weighted_percentile(weighted_hardness, 0.5)
        return median - MIN_BAND_GAP, median + MIN_BAND_GAP
    return lo, hi


def classify_band(hardness: float, lo: float, hi: float) -> str:
    """Which of the three daily mixes a hardness value belongs to.

    Boundaries are inclusive toward the middle: exactly `lo` is still soft, exactly
    `hi` is still hard, so a listener whose whole profile sits on one edge is not left
    with an accidentally empty mix.
    """
    if hardness <= lo:
        return 'soft'
    if hardness >= hi:
        return 'hard'
    return 'mid'


def seed_genre_hardness(cursor) -> int:
    """Fill in `rules_genres.hardness` for every row that does not have one yet.

    Idempotent and safe to run on every startup: it only ever writes a row whose
    `hardness` is still NULL, so a curator's own edit (from the genre edit page) is
    never overwritten. Anchors (`ANCHOR_HARDNESS`) are applied first, matched
    case-insensitively on the curated name; everything else inherits the value of its
    nearest ancestor in `rules_subgenre_hierarchy` -- `nearest_ancestor` already walks
    the whole graph in one call, so a multi-level chain (a raw subgenre of a subgenre
    of an anchor) resolves in the same pass, not over several restarts. A genre with
    no anchor ancestor at all is left NULL rather than guessed at.

    Takes a cursor, not a connection, the same contract `curation_rules.py` uses:
    the caller owns the transaction.
    """
    cursor.execute('SELECT id, name, hardness FROM rules_genres')
    rows = list(cursor.fetchall())

    known: dict[str, float] = {}
    to_update: dict[int, float] = {}
    for row in rows:
        key = (row['name'] or '').strip().lower()
        if row.get('hardness') is not None:
            known[key] = row['hardness']
            continue
        anchor = ANCHOR_HARDNESS.get(key)
        if anchor is not None:
            known[key] = anchor
            to_update[row['id']] = anchor

    cursor.execute('SELECT subgenre, genre FROM rules_subgenre_hierarchy')
    parents: dict[str, set[str]] = {}
    for row in cursor.fetchall():
        parents.setdefault(row['subgenre'].lower(), set()).add(row['genre'].lower())

    candidates = set(known)
    for row in rows:
        if row.get('hardness') is not None or row['id'] in to_update:
            continue
        key = (row['name'] or '').strip().lower()
        ancestor = nearest_ancestor(key, parents, candidates)
        if ancestor is not None:
            to_update[row['id']] = known[ancestor]

    for genre_id, value in to_update.items():
        cursor.execute('UPDATE rules_genres SET hardness = %s WHERE id = %s AND hardness IS NULL', (value, genre_id))
    return len(to_update)


def hardness_source_counts(sources: list[str]) -> dict[str, int]:
    """A `{'genre': n, 'label': n, ...}` tally, for the dry run and the feed response."""
    return dict(Counter(sources))
