"""What the listener's taste is, derived from what they played."""

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime

from services.music_manager.feeds.hierarchy import ancestors, deepest

CONFIDENCE = {'exact': 1.0, 'normalized': 1.0, 'base_title': 0.5, 'fuzzy': 0.25}
FULL_PLAY_SECONDS = 120
MAX_WEIGHT_PER_TRACK = 3.0
MIN_TRACKS_PER_ENTITY = 2


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


@dataclass
class TasteProfile:
    artists: dict[str, float] = field(default_factory=dict)
    labels: dict[str, float] = field(default_factory=dict)
    genres: dict[str, float] = field(default_factory=dict)
    distinct_tracks: int = 0
    total_weight: float = 0.0
    scope: str = 'empty'


def _normalise(weights: dict[str, float], support: dict[str, set[str]]) -> dict[str, float]:
    kept = {k: v for k, v in weights.items() if len(support[k]) >= MIN_TRACKS_PER_ENTITY and v > 0}
    if not kept:
        return {}
    top = max(kept.values())
    return {k: v / top for k, v in kept.items()}


def build_profile(
    rows: list[dict], parents: dict[str, set[str]], exclusions: dict[str, set[str]], now: datetime
) -> TasteProfile:
    """The listener's taste, as three normalised affinity tables.

    A track's weight is capped before it is spread over its memberships, so a
    track on repeat cannot become the profile, and a track carrying five tags
    cannot outvote one carrying a single accurate tag.
    """
    per_track: dict[str, float] = defaultdict(float)
    meta: dict[str, dict] = {}
    for row in rows:
        uid = row['track_uid']
        age_days = (now - row['listened_at']).total_seconds() / 86400.0
        per_track[uid] += listen_weight(age_days, row.get('match_method') or '', row.get('played_secs'))
        meta.setdefault(uid, row)

    weights = {'artist': defaultdict(float), 'label': defaultdict(float), 'genre': defaultdict(float)}
    support = {'artist': defaultdict(set), 'label': defaultdict(set), 'genre': defaultdict(set)}
    total = 0.0
    for uid, raw in per_track.items():
        weight = min(raw, MAX_WEIGHT_PER_TRACK)
        total += weight
        row = meta[uid]
        genres = deepest({g.lower() for g in (row.get('genres') or []) if g}, parents)
        members = {
            'artist': {row['artist'].lower()} if row.get('artist') else set(),
            'label': {label.lower() for label in (row.get('labels') or []) if label},
            'genre': genres,
        }
        for dimension, names in members.items():
            names = names - exclusions.get(dimension, set())
            if not names:
                continue
            share = weight / len(names)
            for name in names:
                weights[dimension][name] += share
                support[dimension][name].add(uid)

    profile = TasteProfile(
        artists=_normalise(weights['artist'], support['artist']),
        labels=_normalise(weights['label'], support['label']),
        genres=_normalise(weights['genre'], support['genre']),
        distinct_tracks=len(per_track),
        total_weight=total,
        scope='user' if per_track else 'empty',
    )
    return profile


TAIL = '__tail__'
COLD_START_TRACKS = 5


def _mix(a: dict[str, float], b: dict[str, float], weight: float) -> dict[str, float]:
    names = set(a) | set(b)
    mixed = {n: weight * a.get(n, 0.0) + (1 - weight) * b.get(n, 0.0) for n in names}
    return {n: v for n, v in mixed.items() if v > 0}


def blend(user: TasteProfile, server: TasteProfile, ramp_tracks: int = 30) -> TasteProfile:
    """Lean on the server's taste until the listener has one of their own.

    A hard switch would flip somebody's feed overnight; the ramp makes their own
    listening take over gradually. Below COLD_START_TRACKS the profile is the
    server's outright, and that is what the client labels differently.
    """
    if user.distinct_tracks >= ramp_tracks:
        return user
    if server.distinct_tracks == 0:
        has_affinities = bool(user.artists or user.labels or user.genres)
        return replace(user, scope='user' if has_affinities else 'empty')
    if user.distinct_tracks < COLD_START_TRACKS:
        return TasteProfile(
            artists=dict(server.artists),
            labels=dict(server.labels),
            genres=dict(server.genres),
            distinct_tracks=user.distinct_tracks,
            total_weight=user.total_weight,
            scope='server',
        )
    weight = user.distinct_tracks / ramp_tracks
    return TasteProfile(
        artists=_mix(user.artists, server.artists, weight),
        labels=_mix(user.labels, server.labels, weight),
        genres=_mix(user.genres, server.genres, weight),
        distinct_tracks=user.distinct_tracks,
        total_weight=user.total_weight,
        scope='blended',
    )


def genre_shares(profile: TasteProfile, parents: dict[str, set[str]], min_share: float = 0.03) -> dict[str, float]:
    """How the places are divided. Always sums to 1, always has a tail.

    A genre too small for a place of its own rolls up into the nearest ancestor
    that is big enough, so three 2% subgenres of hardcore become one 6% hardcore
    share instead of vanishing into a catch-all -- and without uptempo, which is
    also under hardcore, absorbing them.
    """
    total = sum(profile.genres.values())
    if total <= 0:
        return {TAIL: 1.0}
    raw = {name: value / total for name, value in profile.genres.items()}
    big = {name for name, share in raw.items() if share >= min_share}
    shares: dict[str, float] = dict.fromkeys(big, 0.0)
    tail = 0.0
    for name, share in raw.items():
        if name in big:
            shares[name] += share
            continue
        target = next((a for a in ancestors(name, parents) if a in big), None)
        if target:
            shares[target] += share
        else:
            tail += share
    shares[TAIL] = tail
    return shares
