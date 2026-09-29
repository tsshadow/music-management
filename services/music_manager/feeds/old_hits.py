"""The "Oude hitjes" feed's rules: what counts as old, which tier a song belongs to, how tiers fill.

Pure functions over plain values, no database -- `old_hits_build.py` gathers the rows and
calls these. docs/designs/old-hits-feed/technical.md is the binding description; in short:

- **Old** is released more than `min_age_years` ago (`is_old`). A song's age is its earliest
  known date across every version of the work, because a 2024 remaster of a 2009 anthem is
  a 2009 song.
- **Resting**: a song any version of which was played in the last `rest_days` is left out,
  and so is a song rated 1 or 2 stars.
- **Tier 1, favourites**: rated 4-5, longest unheard first.
- **Tier 2, worn**: played at least `min_plays` times, last played `stale_days` or more ago.
- **Tier 3, hits**: an artist the listener likes (`artist_affinity`), and a song the outside
  world plays (an external top-list match) or the library holds many versions of; unrated or
  rated 3 and up.
- Tiers fill `shares` of the places, a tier that runs short passes its places on
  (`fill_tiers`), one version per song and at most `max_per_artist` per artist, and the
  result is interleaved so a favourite, a worn one and a hit take turns (`interleave`).

Every order is a daily-stable weighted draw (`scoring.daily_sample_key`): the same list all
day, a different one tomorrow, with the stalest and most popular songs most likely first.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from services.music_manager.feeds.policy import DEFAULT_FEED_SIZE, FeedPolicy
from services.music_manager.feeds.scoring import daily_sample_key

OLD_HITS_SLUG = 'old-hits'
OLD_HITS_TITLE = 'Oude hitjes'
OLD_HITS_SUBTITLE = 'Oude favorieten die je minder draait'

#: The policy the router sizes and continues like any other feed. Only `slug`, `size` and
#: `max_track_seconds` are read by the old-hits build; the rest are FeedPolicy defaults.
OLD_HITS_POLICY = FeedPolicy(slug=OLD_HITS_SLUG, release_window_days=None, order='daily_sample')

TIER_FAVOURITES = 'favourites'
TIER_WORN = 'worn'
TIER_HITS = 'hits'
TIERS = (TIER_FAVOURITES, TIER_WORN, TIER_HITS)

#: A song never heard (the listen history starts in 2024) counts as unheard this long.
NEVER_HEARD_DAYS = 3 * 365
#: An undated song counts as old when at least this share of its artist's dated tracks is old,
#: and the artist has at least `MIN_ARTIST_DATED` dated tracks to judge from.
OLD_ARTIST_SHARE = 0.8
MIN_ARTIST_DATED = 3

#: Settings (services/common/config_store.py, group `Feeds`).
MIN_AGE_SETTING = 'old_hits_min_age_years'
REST_DAYS_SETTING = 'old_hits_rest_days'
STALE_DAYS_SETTING = 'old_hits_stale_days'
MIN_PLAYS_SETTING = 'old_hits_min_plays'
SHARES_SETTING = 'old_hits_tier_shares'
MAX_PER_ARTIST_SETTING = 'old_hits_max_per_artist'
MIN_VERSIONS_SETTING = 'old_hits_min_versions'
SETTINGS = (
    MIN_AGE_SETTING,
    REST_DAYS_SETTING,
    STALE_DAYS_SETTING,
    MIN_PLAYS_SETTING,
    SHARES_SETTING,
    MAX_PER_ARTIST_SETTING,
    MIN_VERSIONS_SETTING,
)


@dataclass(frozen=True)
class OldHitsConfig:
    """Every knob of the feed, validated. Defaults are the design's."""

    min_age_years: int = 3
    rest_days: int = 90
    stale_days: int = 180
    min_plays: int = 3
    shares: tuple[float, float, float] = (0.4, 0.3, 0.3)
    max_per_artist: int = 3
    min_versions: int = 4
    size: int = DEFAULT_FEED_SIZE


def _int_setting(raw: Any, default: int, minimum: int, maximum: int) -> int:
    if raw is None or isinstance(raw, bool):
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


def parse_shares(raw: Any) -> tuple[float, float, float]:
    """`"40,30,30"` as fractions summing to one; anything else falls back to the default."""
    default = OldHitsConfig.shares
    if not raw or not isinstance(raw, str):
        return default
    try:
        parts = [float(part.strip()) for part in raw.split(',')]
    except ValueError:
        return default
    if len(parts) != 3 or any(part < 0 for part in parts) or sum(parts) <= 0:
        return default
    total = sum(parts)
    return (parts[0] / total, parts[1] / total, parts[2] / total)


def parse_config(get: Callable[[str], Any], size: int = DEFAULT_FEED_SIZE) -> OldHitsConfig:
    """The feed's settings read through `get` (a ConfigStore's), garbage falling back per field."""
    base = OldHitsConfig()
    return OldHitsConfig(
        min_age_years=_int_setting(get(MIN_AGE_SETTING), base.min_age_years, 1, 50),
        rest_days=_int_setting(get(REST_DAYS_SETTING), base.rest_days, 0, 3650),
        stale_days=_int_setting(get(STALE_DAYS_SETTING), base.stale_days, 1, 3650),
        min_plays=_int_setting(get(MIN_PLAYS_SETTING), base.min_plays, 1, 1000),
        shares=parse_shares(get(SHARES_SETTING)),
        max_per_artist=_int_setting(get(MAX_PER_ARTIST_SETTING), base.max_per_artist, 1, 200),
        min_versions=_int_setting(get(MIN_VERSIONS_SETTING), base.min_versions, 2, 1000),
        size=size,
    )


def age_cutoff(today: date, years: int) -> date:
    """`today` minus `years` calendar years; 29 February lands on the 28th."""
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def is_old(
    earliest_date: str | None,
    earliest_year: int | None,
    artist_dated: int,
    artist_old: int,
    cutoff: date,
) -> bool:
    """Whether a song is older than `cutoff`, from the best evidence available.

    1. The earliest full release date among its versions (`YYYY-MM-DD`, the servers' own reading).
    2. Else the earliest release year the analyzer read off any version: old only when the
       whole year lies before the cutoff's year -- a song from the cutoff year itself might
       be younger, and a wrong "old" costs more than a missed one.
    3. Else the artist: at least `MIN_ARTIST_DATED` dated tracks, `OLD_ARTIST_SHARE` of them
       old. The file's own age cannot stand in: the library was rebuilt in 2026, so every
       `created_at` is recent, and the tagger rewrites files, so every mtime is too.
    """
    if earliest_date and len(earliest_date) >= 10:
        try:
            return date.fromisoformat(earliest_date[:10]) < cutoff
        except ValueError:
            pass
    if earliest_year and earliest_year > 1900:
        return earliest_year < cutoff.year
    if artist_dated >= MIN_ARTIST_DATED:
        return artist_old / artist_dated >= OLD_ARTIST_SHARE
    return False


@dataclass
class Song:
    """What the tiers need to know about one song (a work, or an ungrouped track)."""

    key: tuple
    track_id: int
    artist_id: int | None
    canonical_track_id: int | None = None
    rating: int | None = None
    plays: int = 0
    last_heard: datetime | None = None
    popular_position: int | None = None
    popular_source: str | None = None
    versions: int = 1
    old: bool = False
    # Filled by the build from the display row: title, artist name, label, file_path...
    row: dict = field(default_factory=dict)

    def days_unheard(self, now: datetime) -> float:
        """Days since any version was last played; `NEVER_HEARD_DAYS` when never."""
        if self.last_heard is None:
            return float(NEVER_HEARD_DAYS)
        return max(0.0, (now - self.last_heard).total_seconds() / 86400.0)


def song_rating(rows: list[dict]) -> dict[tuple, int]:
    """Per song, the listener's rating: the canonical's own when it has one, else the highest.

    The same roll-up `feeds.queries._SONG_RATING` applies (ratings are stored per track and
    shown per song): a rating given from a list is written to the canonical, so it must win
    over a higher one on some other version, or lowering it could never take effect.
    """
    canonical: dict[tuple, int] = {}
    highest: dict[tuple, int] = {}
    for row in rows:
        key = song_key(row)
        rating = int(row['rating'])
        if row.get('canonical_track_id') is not None and row['track_id'] == row['canonical_track_id']:
            canonical[key] = rating
        highest[key] = max(highest.get(key, rating), rating)
    return {key: canonical.get(key, value) for key, value in highest.items()}


def song_key(row: dict) -> tuple:
    """The work a row belongs to, or the track itself when it has none (the feeds' `song_key`)."""
    work_id = row.get('work_id')
    if work_id:
        return ('work', work_id)
    return ('track', row['track_id'])


def artist_affinity(songs: list[Song]) -> dict[int, float]:
    """How much the listener likes each artist, from their ratings and plays of its songs.

    A 5 counts 3, a 4 counts 2, a 3 half a point, a 2 minus one and a 1 minus two; every song
    played adds half the log of its play count. Only positive totals are returned: an artist
    the listener rates down, or never touched, has no affinity and no hits in tier 3.
    """
    weights = {5: 3.0, 4: 2.0, 3: 0.5, 2: -1.0, 1: -2.0}
    totals: dict[int, float] = {}
    for song in songs:
        if song.artist_id is None:
            continue
        value = weights.get(song.rating or 0, 0.0) + (0.5 * math.log1p(song.plays) if song.plays else 0.0)
        if value:
            totals[song.artist_id] = totals.get(song.artist_id, 0.0) + value
    return {artist: value for artist, value in totals.items() if value > 0}


def resting(song: Song, cfg: OldHitsConfig, now: datetime) -> bool:
    """Excluded outright: not old, rated 1-2, or played within `rest_days`."""
    if not song.old:
        return True
    if song.rating is not None and song.rating <= 2:
        return True
    return song.last_heard is not None and song.days_unheard(now) < cfg.rest_days


def _ordered(songs: list[Song], weight: Callable[[Song], float], username: str, feed_date: date) -> list[Song]:
    keyed = [(daily_sample_key(username, feed_date, repr(song.key), weight(song)), song) for song in songs]
    keyed.sort(key=lambda pair: (pair[0], repr(pair[1].key)))
    return [song for _, song in keyed]


def tier_favourites(songs: list[Song], cfg: OldHitsConfig, now: datetime, username: str, feed_date: date) -> list[Song]:
    """Tier 1: rated 4-5, not resting; the longer unheard, the likelier first."""
    pool = [song for song in songs if (song.rating or 0) >= 4 and not resting(song, cfg, now)]
    return _ordered(pool, lambda song: 1.0 + (song.days_unheard(now) / 30.0) ** 2, username, feed_date)


def tier_worn(songs: list[Song], cfg: OldHitsConfig, now: datetime, username: str, feed_date: date) -> list[Song]:
    """Tier 2: played `min_plays`+ times, last played `stale_days`+ ago; most played and stalest first."""
    pool = [
        song
        for song in songs
        if song.plays >= cfg.min_plays
        and song.last_heard is not None
        and song.days_unheard(now) >= cfg.stale_days
        and not resting(song, cfg, now)
    ]
    return _ordered(pool, lambda song: song.plays * (song.days_unheard(now) / cfg.stale_days), username, feed_date)


def hit_strength(song: Song, cfg: OldHitsConfig) -> float:
    """0-1: how much of a known hit a song looks like. The external top list's position counts
    most (1.0 at the top, 0.5 at place ten); many library versions count up to 0.8."""
    external = 10.0 / (9.0 + song.popular_position) if song.popular_position else 0.0
    versions = min(0.8, 0.8 * song.versions / (2.0 * cfg.min_versions)) if song.versions >= cfg.min_versions else 0.0
    return max(external, versions)


def tier_hits(
    songs: list[Song],
    affinity: dict[int, float],
    cfg: OldHitsConfig,
    now: datetime,
    username: str,
    feed_date: date,
) -> list[Song]:
    """Tier 3: a known hit by an artist the listener likes, unrated or rated 3+, not resting."""
    top = max(affinity.values(), default=0.0)

    def liked(song: Song) -> float:
        return affinity[song.artist_id] / top if top and song.artist_id is not None else 0.0

    pool = [
        song
        for song in songs
        if song.artist_id in affinity
        and hit_strength(song, cfg) > 0
        and (song.rating is None or song.rating >= 3)
        and not resting(song, cfg, now)
    ]
    return _ordered(
        pool,
        lambda song: hit_strength(song, cfg) * liked(song),
        username,
        feed_date,
    )


def quotas(size: int, shares: tuple[float, ...]) -> list[int]:
    """`size` places split by `shares`, largest remainders rounded up, summing to `size` exactly."""
    raw = [size * share for share in shares]
    counts = [int(math.floor(value)) for value in raw]
    order = sorted(range(len(raw)), key=lambda index: (-(raw[index] - counts[index]), index))
    for index in order[: size - sum(counts)]:
        counts[index] += 1
    return counts


def fill_tiers(
    pools: list[list[Song]],
    shares: tuple[float, ...],
    size: int,
    max_per_artist: int,
    artist_of: Callable[[Song], Any] = lambda song: song.artist_id,
) -> list[tuple[Song, int]]:
    """Pick `size` songs over the tiers: `(song, tier index)` in pick order.

    Each tier takes up to its quota plus whatever the tiers before it left unfilled; after the
    last tier, what is still unfilled goes round once more from the first. One song never
    takes two places (a song in two tiers stays in the first that picks it) and no artist
    takes more than `max_per_artist`.
    """
    picked: list[tuple[Song, int]] = []
    seen: set[tuple] = set()
    per_artist: dict[Any, int] = {}
    cursors = [0] * len(pools)

    def take(tier: int, wanted: int) -> int:
        taken = 0
        pool = pools[tier]
        while taken < wanted and cursors[tier] < len(pool):
            song = pool[cursors[tier]]
            cursors[tier] += 1
            artist = artist_of(song)
            if song.key in seen or (artist is not None and per_artist.get(artist, 0) >= max_per_artist):
                continue
            seen.add(song.key)
            if artist is not None:
                per_artist[artist] = per_artist.get(artist, 0) + 1
            picked.append((song, tier))
            taken += 1
        return taken

    carry = 0
    for tier, quota in enumerate(quotas(size, shares)):
        wanted = quota + carry
        carry = wanted - take(tier, wanted)
    for tier in range(len(pools)):
        if len(picked) >= size:
            break
        take(tier, size - len(picked))
    return picked


def interleave(picked: list[tuple[Song, int]]) -> list[tuple[Song, int]]:
    """The picks in playing order: tiers take turns in proportion to how many places each got.

    At every step the tier furthest behind its own pace goes next (a weighted round robin), so
    a list of 40/30/30 opens favourite, worn, hit, favourite... rather than forty favourites.
    """
    by_tier: dict[int, list[tuple[Song, int]]] = {}
    for entry in picked:
        by_tier.setdefault(entry[1], []).append(entry)
    total = len(picked)
    emitted = dict.fromkeys(by_tier, 0)
    ordered: list[tuple[Song, int]] = []
    while len(ordered) < total:
        position = len(ordered) + 1
        tier = min(
            (tier for tier in by_tier if emitted[tier] < len(by_tier[tier])),
            key=lambda tier: ((emitted[tier] + 1) / len(by_tier[tier]) - position / total, tier),
        )
        ordered.append(by_tier[tier][emitted[tier]])
        emitted[tier] += 1
    return ordered


def reason_for(song: Song, tier: int) -> str:
    """The `reason` a track view carries: which tier picked it and on what evidence."""
    name = TIERS[tier]
    if name == TIER_FAVOURITES:
        return f'favourite:{song.rating}'
    if name == TIER_WORN:
        return f'worn:{song.plays}'
    if song.popular_source:
        return f'hit:{song.popular_source}:{song.popular_position}'
    return f'hit:versions:{song.versions}'
