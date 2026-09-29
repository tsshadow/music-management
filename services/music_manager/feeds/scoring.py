"""How strongly a candidate matches, and the order the daily mix comes out in."""

import hashlib
import math
from datetime import date, datetime

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
    # Only a non-positive weight is floored: `score` never goes below MIN_SCORE on its own,
    # and a weight under it is a score scaled down by `rediscovery_factor` on purpose.
    return -math.log(uniform) / (weight if weight > 0 else MIN_SCORE)


#: The older half of a daily mix prefers songs the listener has not played lately (bug
#: report 131): a song last played today weighs `REDISCOVERY_FLOOR` of its score, rising
#: linearly to its full score once `REDISCOVERY_DAYS` have passed. Never heard is full.
REDISCOVERY_DAYS = 180
REDISCOVERY_FLOOR = 0.2


def rediscovery_factor(last_listened_at: datetime | None, now: datetime) -> float:
    """How much of its score an older song keeps, given when it was last played.

    A multiplier on the daily draw's weight, not a filter: a song played last week can
    still come up, only less often than one untouched for half a year.
    """
    if last_listened_at is None:
        return 1.0
    age_days = max(0.0, (now - last_listened_at).total_seconds() / 86400.0)
    if age_days >= REDISCOVERY_DAYS:
        return 1.0
    return REDISCOVERY_FLOOR + (1.0 - REDISCOVERY_FLOOR) * age_days / REDISCOVERY_DAYS


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
    return ranked_names[_daily_entity_index(username, feed_date, len(ranked_names))]


def _daily_entity_index(username: str, feed_date: date, count: int) -> int:
    """The day-stable index `pick_daily_entity` lands on, out of `count` names."""
    digest = hashlib.md5(f'{username}|{feed_date.isoformat()}|entity'.encode()).hexdigest()
    return int(digest[:8], 16) % count


def pick_playable_entity(
    username: str,
    feed_date: date,
    ranked_names: list[str],
    song_counts: dict[str, tuple[int, ...]],
    windows: tuple[int | None, ...],
    minimum: int,
) -> tuple[str, int | None] | None:
    """Today's rotating-mix name and the release window it is built at, or None.

    Bug report 110: `pick_daily_entity` alone chose a name without asking whether
    it had anything to play, and the artist mix went out with 0 or 2 tracks. This
    starts at the same day-stable index and walks the ranking from there, wrapping
    around, taking the first name that reaches `minimum` songs at *some* window --
    the narrowest one that does, tried in `windows` order. The drawn name at a
    widened window is preferred over the next name at the policy's own window: the
    rotation is what the mix is for, and a mix of the artist drawn today, drawn
    from further back, is still that artist's mix.

    `song_counts` maps a lower-cased name to one song count per entry of
    `windows` (`rotation_counts_query`'s columns); a name missing from it has
    nothing playable at all. None means no name in the top ten qualifies.
    """
    if not ranked_names:
        return None
    start = _daily_entity_index(username, feed_date, len(ranked_names))
    for offset in range(len(ranked_names)):
        name = ranked_names[(start + offset) % len(ranked_names)]
        counts = song_counts.get(name.lower(), ())
        # Not strict: a name missing from the counts has an empty tuple, i.e. nothing.
        for window, count in zip(windows, counts, strict=False):
            if count >= minimum:
                return name, window
    return None
