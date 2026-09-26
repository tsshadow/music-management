"""What separates one feed from another.

Every number here is a proposed default, not a measured one (see
docs/designs/feeds/functional.md, Open Questions). They live in one frozen
dataclass so that trying a different window is a value change and never a second
query: the radar and the daily mix are the same ranker with different parameters.
"""

from dataclasses import dataclass, replace

from services.music_manager.feeds.hardness import DEFAULT_BAND_EDGES

#: How many tracks a feed holds when the `feeds_size` setting says nothing usable.
#: 100 since docs/designs/feed-length/: 30 was under two hours, and a live build of
#: 100 costs the same as one of 30 (the profile and candidate queries dominate).
DEFAULT_FEED_SIZE = 100

#: The range `feeds_size` accepts. The floor keeps a typo from emptying every feed;
#: the ceiling keeps a nightly refresh and a response bounded (LMS resolves at most
#: 100 paths per getSongsByPath call, so the clients resolve in chunks of 100).
MIN_FEED_SIZE = 10
MAX_FEED_SIZE = 200

#: The runtime setting (services/common/config_store.py, group `Feeds`) holding the
#: number of tracks every feed is built with -- the first page of a feed.
FEED_SIZE_SETTING = 'feeds_size'


def parse_feed_size(raw) -> int:
    """The configured feed length, or `DEFAULT_FEED_SIZE` for anything unusable.

    Unusable is None, empty, not a whole number, or outside
    `MIN_FEED_SIZE`..`MAX_FEED_SIZE` -- garbage falls back rather than raising,
    the same contract as `parse_hardness_edges`, because a feed that fails to build
    over a mistyped setting is worse than one at the default length.
    """
    if raw is None or isinstance(raw, bool):
        return DEFAULT_FEED_SIZE
    try:
        size = int(str(raw).strip())
    except ValueError:
        return DEFAULT_FEED_SIZE
    if MIN_FEED_SIZE <= size <= MAX_FEED_SIZE:
        return size
    return DEFAULT_FEED_SIZE


@dataclass(frozen=True)
class FeedPolicy:
    """The knobs of one feed: its size, time windows and scoring weights."""

    slug: str
    # The code default; the router replaces it per request with the `feeds_size`
    # setting (`parse_feed_size`), so a tuned length never needs a release.
    size: int = DEFAULT_FEED_SIZE
    profile_window_days: int = 90
    # None means "no release-date requirement at all".
    release_window_days: int | None = 7
    max_track_seconds: int = 600
    # A subset of {'any', 'unheard', 'loved'}; several pools are OR-ed.
    pools: frozenset[str] = frozenset({'any'})
    loved_min_rating: int = 4
    heard_rank_penalty: bool = True
    order: str = 'release'  # 'release' | 'daily_sample'
    max_per_artist: int = 3
    label_bonus: float = 0.10
    soundcloud_penalty: float = 0.10
    # 'soft' | 'mid' | 'hard' | None. Set only on the three spectrum daily mixes:
    # candidates are restricted to this third of the listener's own hardness
    # distribution (feeds/hardness.py), and a track with no resolvable hardness is
    # excluded rather than guessed into a bucket. See build.py's relaxation loop for
    # what happens when a band comes up short.
    hardness_band: str | None = None
    # 'artist' | 'label' | None. Set only on the two rotating daily mixes: candidates
    # are restricted to one artist or one label, chosen by a stable hash of
    # (username, date) over the listener's own top ten, skipping any name with fewer
    # than build.MIN_ROTATION_CANDIDATES playable songs -- see
    # scoring.pick_playable_entity and build._ranked_names.
    rotate: str | None = None


def resize(policy: FeedPolicy, size: int) -> FeedPolicy:
    """`policy` with `size` places -- the one way anything changes a feed's length.

    A policy whose per-artist cap equals its size is uncapped by construction (the
    artist mix: every candidate shares one artist, bug report 110), so its cap moves
    with the size; a length of 150 must not leave it capped at the code default.
    Every other cap is a fixed number of tracks per artist and stays as it is. The
    `feeds_size` setting and a continuation's bigger build both go through here.
    """
    if policy.size == size:
        return policy
    if policy.max_per_artist >= policy.size:
        return replace(policy, size=size, max_per_artist=size)
    return replace(policy, size=size)


#: The runtime setting (services/common/config_store.py, group `Feeds`) holding
#: the comma-separated fallback genres for a server nobody has listened on yet.
STARTING_GENRES_SETTING = 'feeds_starting_genres'


def parse_starting_genres(raw: str | None) -> list[str] | None:
    """The configured fallback genres, or None when nothing is configured.

    None and `''` mean the same thing here and both mean "no fallback at all":
    a server with no listening history reports `not_enough_data` rather than
    inventing a taste. Parsing lives here, next to the setting's name, because
    the router and the dry run both read the same key and have to read it the
    same way -- a dry run that resolves a different fallback than production
    measures the wrong feed.
    """
    genres = [genre.strip() for genre in (raw or '').split(',') if genre.strip()]
    return genres or None


#: The runtime setting (services/common/config_store.py, group `Feeds`) holding the
#: two fixed hardness band edges as "<soft/mid>,<mid/hard>", e.g. "50,75". See
#: `feeds/hardness.py`'s `DEFAULT_BAND_EDGES` for what a listener gets when this is
#: unset or unparsable, and its docstring for why the edges are fixed at all rather
#: than measured per listener.
HARDNESS_EDGES_SETTING = 'feeds_hardness_edges'


def parse_hardness_edges(raw: str | None) -> tuple[tuple[float, float], str]:
    """The two band edges this setting configures, and whether it actually supplied
    them -- `'setting'` or `'default'`.

    Mirrors `parse_starting_genres`'s contract: the router and the dry run must
    resolve the same edges the same way, or a dry run measures a different feed
    than the one shipped. Garbage falls back to `DEFAULT_BAND_EDGES` rather than
    raising -- not exactly two comma-separated numbers, not parseable as floats, not
    ascending, or outside the 0-100 range a curated genre's own `hardness` lives in.
    """
    if raw:
        parts = raw.split(',')
        if len(parts) == 2:
            try:
                lo, hi = float(parts[0].strip()), float(parts[1].strip())
            except ValueError:
                pass
            else:
                if 0 <= lo < hi <= 100:
                    return (lo, hi), 'setting'
    return DEFAULT_BAND_EDGES, 'default'


#: What every daily mix -- spectrum or rotating -- has in common: the 90-day window,
#: unheard-or-loved pools, the daily-stable sample order, no penalty for a track
#: already heard (the whole point of `unheard`/`loved` is to pick the pool, not to
#: additionally punish it). One template instance, `replace()`-d per mix below, so
#: the seven-field agreement between the five mixes is a value every one of them
#: shares rather than five separate dataclass calls that could drift apart.
_DAILY_MIX_BASE = FeedPolicy(
    slug='daily-mix-base',
    release_window_days=90,
    pools=frozenset({'unheard', 'loved'}),
    order='daily_sample',
    heard_rank_penalty=False,
)

POLICIES: dict[str, FeedPolicy] = {
    'release-radar': FeedPolicy(slug='release-radar', release_window_days=7),
    # The classic, unrestricted daily mix -- byte-for-byte the policy this slug has
    # always had, and *not* an alias of daily-mix-mid: the car and the phone already
    # call it, and it must never lose a track to a missing hardness value the way a
    # hardness_band mix deliberately does. A design correction after MR !798's first
    # pipeline: aliasing it to daily-mix-mid meant a library with thin genre coverage
    # (the integration schema's fixtures, and any real one before the tagger catches
    # up) answered 'no_matches' for a slug that used to always find something.
    'daily-mix': replace(_DAILY_MIX_BASE, slug='daily-mix'),
    'daily-mix-soft': replace(_DAILY_MIX_BASE, slug='daily-mix-soft', hardness_band='soft'),
    'daily-mix-mid': replace(_DAILY_MIX_BASE, slug='daily-mix-mid', hardness_band='mid'),
    'daily-mix-hard': replace(_DAILY_MIX_BASE, slug='daily-mix-hard', hardness_band='hard'),
    # Every candidate of an artist mix has the same primary artist, so the usual cap of
    # three per artist would cut the whole mix to three tracks (bug report 110): the cap
    # is lifted to the mix's own size. The label mix keeps it -- many artists share a label.
    'daily-mix-artist': replace(
        _DAILY_MIX_BASE, slug='daily-mix-artist', rotate='artist', max_per_artist=_DAILY_MIX_BASE.size
    ),
    'daily-mix-label': replace(_DAILY_MIX_BASE, slug='daily-mix-label', rotate='label'),
}
