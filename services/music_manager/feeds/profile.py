"""What the listener's taste is, derived from what they played."""

CONFIDENCE = {'exact': 1.0, 'normalized': 1.0, 'base_title': 0.5, 'fuzzy': 0.25}
FULL_PLAY_SECONDS = 120


def listen_weight(age_days: float, match_method: str, played_secs: int | None, half_life_days: float = 30.0) -> float:
    """One listen's contribution: how recent, how certain, how far played.

    `played_secs IS NULL` means unknown, not zero -- it is what imported history
    and every older listen carry. Reading it as a skip would drop most of the
    history the profile exists to read.
    """
    recency = 0.5 ** (max(age_days, 0.0) / half_life_days)
    confidence = CONFIDENCE.get(match_method, 0.25)
    engagement = 1.0 if played_secs is None else min(1.0, max(0, played_secs) / FULL_PLAY_SECONDS)
    return recency * confidence * engagement
