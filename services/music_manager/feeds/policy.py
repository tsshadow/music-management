"""What separates one feed from another.

Every number here is a proposed default, not a measured one (see
docs/designs/feeds/functional.md, Open Questions). They live in one frozen
dataclass so that trying a different window is a value change and never a second
query: the radar and the daily mix are the same ranker with different parameters.
"""

from dataclasses import dataclass


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


POLICIES: dict[str, FeedPolicy] = {
    'release-radar': FeedPolicy(slug='release-radar', release_window_days=7),
    'daily-mix': FeedPolicy(
        slug='daily-mix',
        release_window_days=90,
        pools=frozenset({'unheard', 'loved'}),
        order='daily_sample',
        heard_rank_penalty=False,
    ),
}
