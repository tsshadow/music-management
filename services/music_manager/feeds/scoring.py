"""How strongly a candidate matches, and the order the daily mix comes out in."""

import hashlib
import math
from datetime import date

from services.music_manager.feeds.policy import FeedPolicy
from services.music_manager.feeds.profile import TasteProfile

RATING_ADJUSTMENT = {1: -0.10, 2: -0.05, 3: 0.0, 4: 0.05, 5: 0.10}
MIN_SCORE = 0.01


def taste_score(candidate: dict, profile: TasteProfile) -> float:
    """The strongest of the three signals, never their sum.

    Summing rewards a track for being tagged a lot rather than for being a good
    match, and punishes a strong artist match that happens to carry no genre.
    """
    artist = profile.artists.get((candidate.get('artist') or '').lower(), 0.0)
    labels = [profile.labels.get(name.lower(), 0.0) for name in (candidate.get('labels') or [])]
    genres = [profile.genres.get(name.lower(), 0.0) for name in (candidate.get('genres') or [])]
    return max([artist, *labels, *genres, 0.0])


def score(candidate: dict, profile: TasteProfile, policy: FeedPolicy) -> float:
    """How well `candidate` fits the listener's taste under `policy`."""
    value = taste_score(candidate, profile)
    if candidate.get('has_label'):
        value += policy.label_bonus
    if candidate.get('is_soundcloud'):
        value -= policy.soundcloud_penalty
    # An out-of-range rating is somebody else's writer, not a signal to rescale.
    rating = candidate.get('rating')
    if rating is not None:
        value += RATING_ADJUSTMENT.get(rating, 0.0)
    return max(MIN_SCORE, value)


def daily_sample_key(username: str, feed_date: date, track_uid: str, weight: float) -> float:
    """A weighted draw that is stable for one day.

    ORDER BY RAND() reshuffles on every refresh; storing a snapshot to avoid that
    would be a table and a job for something a hash already gives us.
    """
    digest = hashlib.md5(f'{username}|{feed_date.isoformat()}|{track_uid}'.encode()).hexdigest()
    uniform = (int(digest[:16], 16) + 1) / (16**16 + 1)
    return -math.log(uniform) / max(weight, MIN_SCORE)


def pick_daily_entity(username: str, feed_date: date, ranked_names: list[str]) -> str | None:
    """Which of the listener's top artists (or labels) `daily-mix-artist` (or
    `-label`) rotates to today.

    The same trick as `daily_sample_key`: a hash of `(username, date)`, not a stored
    index, so the rotation needs no scheduling to change at midnight and no state to
    keep consistent across app servers. `ranked_names` is expected to already be the
    listener's top ten, most affine first (`build._ranked_names`) -- this only picks
    which one, it does not rank them.
    """
    if not ranked_names:
        return None
    digest = hashlib.md5(f'{username}|{feed_date.isoformat()}|entity'.encode()).hexdigest()
    index = int(digest[:8], 16) % len(ranked_names)
    return ranked_names[index]
