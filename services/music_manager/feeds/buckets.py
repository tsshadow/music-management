"""Which share a candidate competes in.

New releases are exactly the tracks the tagger has seen least, so a radar that
insists on a genre tag drops the newest music first. The label is the way around
it: a label in this collection releases one style, and that style is readable
from the tracks of that label that *were* tagged.
"""

from services.music_manager.feeds.hierarchy import deepest
from services.music_manager.feeds.profile import TAIL


def dominant_genre(counts: dict[str, int], min_share: float = 0.6) -> str | None:
    """The one genre a label or artist is, or None when it is several things.

    When counts tie, alphabetically first wins.
    """
    total = sum(counts.values())
    if not total:
        return None
    max_count = max(counts.values())
    if max_count / total < min_share:
        return None
    return min(name for name, count in counts.items() if count == max_count)


def bucket_of(
    candidate: dict,
    shares: dict[str, float],
    label_genre: dict[str, str],
    artist_genre: dict[str, str],
    parents: dict[str, set[str]],
) -> tuple[str, str]:
    """The share bucket `candidate` falls into, and whether its genre, label or artist decided it."""
    own = deepest({g.lower() for g in (candidate.get('genres') or []) if g}, parents)
    for genre in sorted(own):
        if genre in shares and genre != TAIL:
            return genre, 'genre'
    label = (candidate.get('label') or '').lower()
    if label and label_genre.get(label) in shares:
        return label_genre[label], f'label:{label}'
    artist = (candidate.get('artist') or '').lower()
    if artist and artist_genre.get(artist) in shares:
        return artist_genre[artist], f'artist:{artist}'
    return TAIL, 'tail'
