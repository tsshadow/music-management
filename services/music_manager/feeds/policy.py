"""What separates one feed from another.

Every number here is a proposed default, not a measured one (see
docs/designs/feeds/functional.md, Open Questions). They live in one frozen
dataclass so that trying a different window is a value change and never a second
query: the radar and the daily mix are the same ranker with different parameters.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class FeedPolicy:
    slug: str
    size: int = 30
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
    # (username, date) over the listener's own top ten -- see
    # scoring.pick_daily_entity and build._ranked_names.
    rotate: str | None = None


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
    'daily-mix-artist': replace(_DAILY_MIX_BASE, slug='daily-mix-artist', rotate='artist'),
    'daily-mix-label': replace(_DAILY_MIX_BASE, slug='daily-mix-label', rotate='label'),
}
