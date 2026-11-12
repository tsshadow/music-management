"""The listens of one period, read once, and what the cards need to know about their tracks.

A year holds at most about 50.000 listens (20.532 linked and 29.360 unlinked in 2026), so
reading them all and counting in Python is cheaper and easier to test than one query per card.
The track facts (genres, labels, channels, BPM, remixers) are read in one query each, limited
to the tracks the period played.

The where-clause and the UTC bounds come from `ListeningScope` in routers/listening.py, so a
day starts at local midnight in the reader's zone, the same as on the Listening stats page.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from services.common.Helpers.FestivalHelper import Festival, FestivalHelper
from services.common.Helpers.PodcastHelper import PodcastHelper, Show
from services.music_manager.routers.listening import ListeningScope, release_year_sql


@dataclass(frozen=True, slots=True)
class Listen:
    """One listen, linked to a library track or not, with its time in the reader's zone."""

    at: datetime
    local: datetime
    username: str
    source: str | None
    played_secs: float | None
    track_id: int | None = None
    title: str | None = None
    artist: str | None = None
    artist_id: int | None = None
    duration_secs: float | None = None
    form: str | None = None
    performance_date: str | None = None
    track_uid: str | None = None
    release_year: int | None = None
    arrived_at: datetime | None = None

    @property
    def tid(self) -> int:
        """The track id as a key into the per-track facts: 0, which no track has, when unmatched."""
        return self.track_id or 0

    @property
    def linked(self) -> bool:
        """Whether the listen found its library track."""
        return self.track_id is not None

    @property
    def length(self) -> float | None:
        """How long it played: measured when known, else the track's length, else unknown."""
        if self.played_secs is not None:
            return float(self.played_secs)
        if self.duration_secs is not None:
            return float(self.duration_secs)
        return None


@dataclass
class PeriodData:
    """Everything the listening cards read: the listens and the facts about their tracks."""

    scope: ListeningScope
    listens: list[Listen]
    genres: dict[int, list[str]] = field(default_factory=dict)
    labels: dict[int, list[tuple[int, str]]] = field(default_factory=dict)
    channels: dict[int, list[dict]] = field(default_factory=dict)
    bpm: dict[int, tuple[float, str]] = field(default_factory=dict)
    remixers: dict[int, list[str]] = field(default_factory=dict)
    remixer_credits: bool = False
    library_scope: bool = False

    @property
    def linked(self) -> list[Listen]:
        """The listens that found their track, in time order."""
        return [listen for listen in self.listens if listen.linked]

    @property
    def date_from(self) -> date:
        """The first day of the period, in the scope's zone."""
        if self.scope.date_from is None:
            raise ValueError('A Wrapped period always has a first day')
        return self.scope.date_from

    @property
    def date_to(self) -> date:
        """The last day of the period, in the scope's zone."""
        if self.scope.date_to is None:
            raise ValueError('A Wrapped period always has a last day')
        return self.scope.date_to

    @property
    def unmatched(self) -> int:
        """How many listens did not find their track: the disclosure on every linked-only card."""
        return sum(1 for listen in self.listens if not listen.linked)


def utc_bounds(scope: ListeningScope) -> tuple[datetime, datetime]:
    """The period as a half-open UTC interval, naive, as the database stores `listened_at`."""
    assert scope.date_from is not None and scope.date_to is not None
    return scope._as_utc(scope.date_from), scope._as_utc(scope.date_to, days_after=1)


def to_local(moment: datetime, scope: ListeningScope) -> datetime:
    """A naive UTC moment from the database, in the scope's zone."""
    return moment.replace(tzinfo=UTC).astimezone(scope.zone)


_PLAYED = 'SELECT track_id FROM scrobble_listens WHERE {where} AND track_id IS NOT NULL'

LINKED_SQL = (
    """
    SELECT l.listened_at, l.username, l.source, l.played_secs, l.track_id,
           t.title, COALESCE(a.name, t.display_artist) AS artist, t.primary_artist_id AS artist_id,
           t.duration_secs, t.form, t.performance_date, t.track_uid, t.arrived_at,
           """
    + release_year_sql('t')
    + """ AS release_year
    FROM scrobble_listens l
    JOIN library_tracks t ON t.id = l.track_id
    LEFT JOIN library_artists a ON a.id = t.primary_artist_id
    WHERE {where}
    """
)

UNMATCHED_SQL = """
    SELECT listened_at, username, source, played_secs, artist_name, track_title
    FROM scrobble_unmatched_listens
    WHERE {where}
"""

GENRES_SQL = (
    """
    SELECT tg.track_id, rg.name
    FROM library_track_genres tg
    JOIN rules_genres rg ON rg.id = tg.genre_id AND rg.state <> 'black'
    WHERE tg.track_id IN ("""
    + _PLAYED
    + ')'
)

# A track's real labels: its own label links, and the label of a channel it came from.
LABELS_SQL = (
    """
    SELECT tl.track_id, lb.id AS label_id, lb.name
    FROM library_track_labels tl
    JOIN library_labels lb ON lb.id = tl.label_id
    WHERE tl.track_id IN ("""
    + _PLAYED
    + """)
    UNION
    SELECT tc.track_id, lb.id AS label_id, lb.name
    FROM library_track_channels tc
    JOIN channels c ON c.id = tc.channel_id
    JOIN library_labels lb ON lb.id = c.label_id
    WHERE tc.track_id IN ("""
    + _PLAYED
    + ')'
)

CHANNELS_SQL = (
    """
    SELECT tc.track_id, c.id AS channel_id, c.platform, c.name,
           lb.name AS label_name, ar.name AS artist_name
    FROM library_track_channels tc
    JOIN channels c ON c.id = tc.channel_id
    LEFT JOIN library_labels lb ON lb.id = c.label_id
    LEFT JOIN library_artists ar ON ar.id = c.artist_id
    WHERE tc.track_id IN ("""
    + _PLAYED
    + ')'
)

BPM_SQL = (
    """
    SELECT b.track_id, b.bpm, b.confidence
    FROM library_track_effective_bpm b
    WHERE b.confidence <> 'low' AND b.track_id IN ("""
    + _PLAYED
    + ')'
)

REMIXERS_SQL = (
    """
    SELECT ta.track_id, a.name
    FROM library_track_artists ta
    JOIN library_artists a ON a.id = ta.artist_id
    WHERE ta.role = 'remixer' AND ta.track_id IN ("""
    + _PLAYED
    + ')'
)

REMIXER_CREDITS_SQL = "SELECT EXISTS (SELECT 1 FROM library_track_artists WHERE role = 'remixer') AS present"

FESTIVALS_SQL = 'SELECT id, name FROM rules_festivals WHERE active = 1'
FESTIVAL_ALIASES_SQL = 'SELECT festival_id, alias FROM rules_festival_aliases'
FESTIVAL_EDITIONS_SQL = 'SELECT festival_id, year, date FROM rules_festival_editions'
SHOWS_SQL = """
    SELECT p.id, p.name, a.alias
    FROM rules_podcasts p
    LEFT JOIN rules_podcast_aliases a ON a.podcast_id = p.id
    WHERE p.state = 'white'
"""


def _fetch(cursor, sql: str, params) -> list[dict]:
    cursor.execute(sql, tuple(params))
    return list(cursor.fetchall() or [])


def _float(value) -> float | None:
    return float(value) if value is not None else None


def load_period(cursor, scope: ListeningScope, library_scope: bool = False) -> PeriodData:
    """Read the period's listens, oldest first, and the facts about the tracks they played."""
    where, params = scope.where()
    listens: list[Listen] = []
    for row in _fetch(cursor, LINKED_SQL.replace('{where}', where), params):
        listens.append(
            Listen(
                at=row['listened_at'],
                local=to_local(row['listened_at'], scope),
                username=row['username'],
                source=row.get('source'),
                played_secs=_float(row.get('played_secs')),
                track_id=row['track_id'],
                title=row.get('title'),
                artist=row.get('artist'),
                artist_id=row.get('artist_id'),
                duration_secs=_float(row.get('duration_secs')),
                form=row.get('form'),
                performance_date=row.get('performance_date'),
                track_uid=row.get('track_uid'),
                release_year=int(row['release_year']) if row.get('release_year') is not None else None,
                arrived_at=row.get('arrived_at'),
            )
        )
    for row in _fetch(cursor, UNMATCHED_SQL.replace('{where}', where), params):
        listens.append(
            Listen(
                at=row['listened_at'],
                local=to_local(row['listened_at'], scope),
                username=row['username'],
                source=row.get('source'),
                played_secs=_float(row.get('played_secs')),
                title=row.get('track_title'),
                artist=row.get('artist_name'),
            )
        )
    listens.sort(key=lambda listen: (listen.at, listen.track_id or 0))
    data = PeriodData(scope=scope, listens=listens, library_scope=library_scope)
    if not any(listen.linked for listen in listens):
        return data

    for row in _fetch(cursor, GENRES_SQL.replace('{where}', where), params):
        data.genres.setdefault(row['track_id'], []).append(row['name'])
    for row in _fetch(cursor, LABELS_SQL.replace('{where}', where), [*params, *params]):
        data.labels.setdefault(row['track_id'], []).append((row['label_id'], row['name']))
    for row in _fetch(cursor, CHANNELS_SQL.replace('{where}', where), params):
        data.channels.setdefault(row['track_id'], []).append(
            {
                'channel_id': row['channel_id'],
                'platform': row['platform'],
                'name': row['name'],
                'label': row.get('label_name'),
                'artist': row.get('artist_name'),
            }
        )
    for row in _fetch(cursor, BPM_SQL.replace('{where}', where), params):
        data.bpm[row['track_id']] = (float(row['bpm']), row['confidence'])
    present = _fetch(cursor, REMIXER_CREDITS_SQL, [])
    data.remixer_credits = bool(present and present[0].get('present'))
    if data.remixer_credits:
        for row in _fetch(cursor, REMIXERS_SQL.replace('{where}', where), params):
            data.remixers.setdefault(row['track_id'], []).append(row['name'])
    return data


@dataclass
class UserHistory:
    """What the User tab compares a period with: the reader's own past and the other listeners."""

    prior_genres: set[str] = field(default_factory=set)
    prior_artists: set[int] = field(default_factory=set)
    others_tracks: set[int] = field(default_factory=set)
    ratings: list[dict] = field(default_factory=list)


PRIOR_GENRES_SQL = """
    SELECT DISTINCT rg.name
    FROM scrobble_listens l
    JOIN library_track_genres tg ON tg.track_id = l.track_id
    JOIN rules_genres rg ON rg.id = tg.genre_id AND rg.state <> 'black'
    WHERE l.username = %s AND l.listened_at < %s
"""

PRIOR_ARTISTS_SQL = """
    SELECT DISTINCT t.primary_artist_id AS artist_id
    FROM scrobble_listens l
    JOIN library_tracks t ON t.id = l.track_id
    WHERE l.username = %s AND l.listened_at < %s AND t.primary_artist_id IS NOT NULL
"""

# Tracks another account played in the period. Only the ids leave the database: the User tab
# may say "nobody else played this", never who did (decision 7).
OTHERS_TRACKS_SQL = """
    SELECT DISTINCT track_id
    FROM scrobble_listens
    WHERE listened_at >= %s AND listened_at < %s AND username <> %s AND track_id IS NOT NULL
"""

RATINGS_SQL = """
    SELECT entity_id, rating, updated_at
    FROM rating_tracks
    WHERE username = %s AND entity_type = 'track'
"""


def load_user_history(cursor, scope: ListeningScope) -> UserHistory:
    """The reader's listening before the period, the tracks others played in it, and their ratings."""
    start, end = utc_bounds(scope)
    username = scope.username
    history = UserHistory()
    history.prior_genres = {row['name'] for row in _fetch(cursor, PRIOR_GENRES_SQL, [username, start])}
    history.prior_artists = {row['artist_id'] for row in _fetch(cursor, PRIOR_ARTISTS_SQL, [username, start])}
    history.others_tracks = {row['track_id'] for row in _fetch(cursor, OTHERS_TRACKS_SQL, [start, end, username])}
    history.ratings = _fetch(cursor, RATINGS_SQL, [username])
    return history


def load_festival_helper(cursor) -> FestivalHelper:
    """A FestivalHelper filled from this cursor, so it reads the same database as the rest."""
    by_id = {row['id']: Festival(name=row['name']) for row in _fetch(cursor, FESTIVALS_SQL, [])}
    for row in _fetch(cursor, FESTIVAL_ALIASES_SQL, []):
        if row['festival_id'] in by_id and row['alias']:
            by_id[row['festival_id']].aliases.append(row['alias'])
    for row in _fetch(cursor, FESTIVAL_EDITIONS_SQL, []):
        if row['festival_id'] in by_id and row['year'] and row['date']:
            edition = row['date']
            if isinstance(edition, str):
                edition = date.fromisoformat(edition[:10])
            by_id[row['festival_id']].editions[int(row['year'])] = edition
    for festival in by_id.values():
        if not festival.aliases:
            festival.aliases = [festival.name]
    helper = FestivalHelper(preload=False)
    helper.set_festivals(list(by_id.values()))
    return helper


def load_podcast_helper(cursor) -> PodcastHelper:
    """A PodcastHelper with the approved shows, read through this cursor."""
    shows: dict[int, Show] = {}
    for row in _fetch(cursor, SHOWS_SQL, []):
        show = shows.setdefault(row['id'], Show(name=row['name'], aliases=[row['name']]))
        if row.get('alias') and row['alias'] not in show.aliases:
            show.aliases.append(row['alias'])
    helper = PodcastHelper(preload=False)
    helper.set_shows(list(shows.values()))
    return helper


def group_by(items, key) -> dict:
    """A dict of lists, in the order the items came."""
    out: dict = defaultdict(list)
    for item in items:
        out[key(item)].append(item)
    return out
