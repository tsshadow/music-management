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
    value = taste_score(candidate, profile)
    if candidate.get('has_label'):
        value += policy.label_bonus
    if candidate.get('is_soundcloud'):
        value -= policy.soundcloud_penalty
    # An out-of-range rating is somebody else's writer, not a signal to rescale.
    value += RATING_ADJUSTMENT.get(candidate.get('rating'), 0.0)
    return max(MIN_SCORE, value)


def daily_sample_key(username: str, feed_date: date, track_uid: str, weight: float) -> float:
    """A weighted draw that is stable for one day.

    ORDER BY RAND() reshuffles on every refresh; storing a snapshot to avoid that
    would be a table and a job for something a hash already gives us.
    """
    digest = hashlib.md5(f'{username}|{feed_date.isoformat()}|{track_uid}'.encode()).hexdigest()
    uniform = (int(digest[:16], 16) + 1) / (16**16 + 1)
    return -math.log(uniform) / max(weight, MIN_SCORE)
