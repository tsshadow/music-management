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
    pools: frozenset = frozenset({'any'})
    loved_min_rating: int = 4
    heard_rank_penalty: bool = True
    order: str = 'release'  # 'release' | 'daily_sample'
    max_per_artist: int = 3
    label_bonus: float = 0.10
    soundcloud_penalty: float = 0.10


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
