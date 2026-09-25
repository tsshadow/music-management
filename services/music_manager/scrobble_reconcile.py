"""Reconcile muma's listening history against the listen table LMS keeps for itself.

Bug report 039: until migrate_v33, `scrobble_listens.listened_at` carried an implicit
`ON UPDATE CURRENT_TIMESTAMP`, so every UPDATE that touched a listen -- a played_secs top-up, a
re-match, an account merge -- moved it to the moment of that UPDATE. The fix stopped further
damage; it could not say what the destroyed values had been. For every listen that was played
through LMS, LMS itself still knows: its `listen` table records `date_time` at the same moment
it relays the scrobble to muma, and nothing in LMS ever rewrites it. This module compares the
two and, on request, puts LMS's time back.

**How an LMS listen reaches a muma track.** The two id spaces are unrelated, so the bridge is
the file path, exactly as for ratings and song versions: LMS `listen.track_id` ->
`track.absolute_file_path` -> every spelling `library_paths.candidate_paths()` knows ->
`library_media_files.file_path` -> `library_media_files.track_id`. The user is joined by name:
LMS relays `user.login_name` as the scrobble's `username`.

**Time.** LMS stores `date_time` as ISO 8601 text in UTC (Wt::Dbo's SQLite default, milliseconds,
no zone suffix); muma's relay received `toTime_t()` of a moment a few milliseconds away, so both
sides are compared as whole Unix seconds, LMS's floored. muma's side is read with
`UNIX_TIMESTAMP()` and written with `FROM_UNIXTIME()` on a session pinned to `+00:00`, so no local
zone and no daylight-saving fold ever enters the comparison or the write. That is only sound if
the relay stored the right instant in the first place: `routers/scrobbler.py` turns the Unix time
into a naive `datetime.fromtimestamp()` (the process's zone) and MariaDB reads that naive value in
the session's zone. `zone_check()` compares the two offsets; when they differ every stored listen
is off by a constant, the comparison means nothing, and `apply()` refuses to write.

**The classes**, decided per user and per muma track by `classify()`:

- `exact` -- a muma listen and an LMS listen of the same track at most `EXACT_WINDOW_SECONDS`
  apart. Paired first, globally by smallest gap, so an exact pair is never broken up to serve a
  shifted one.
- `shifted` -- the bug-039 signature, paired from what is left: same track, the muma listen is
  *later* than the LMS listen by more than the window (the bug only ever moved a time forward, to
  NOW()), the muma row shows that it was rewritten or re-matched (its `listened_at` and
  `created_at` differ by more than the window: a row the relay inserted and nobody touched since
  has the two within a second, and `created_at` itself never carried an ON UPDATE), and it is a
  live source rather than an import. Pairs are again taken smallest gap first, so each LMS listen
  repairs at most one muma listen, the nearest. Deliberately stricter than "nearest LMS listen
  more than five seconds away": an untouched row is a second play, never a moved one.
- `muma_only` -- a muma listen with no LMS counterpart: ListenBrainz imports, manual scrobbles,
  plays shorter than the five seconds LMS itself records, history from before LMS or from a
  library LMS has since rebuilt. Left alone.
- `lms_only` -- an LMS listen no muma listen claimed: a scrobble muma lost. Reported; inserted
  only on request and only when it is `insertable` -- no muma listen of that track is left
  unclaimed (which could be its counterpart under some drift this module does not model), and
  no muma listen or unmatched listen of the same user sits within `SAME_PLAY_WINDOW_SECONDS` of
  it (the same play, matched to a different track or not matched at all). "Within" is checked
  against both `listened_at` and `created_at`: an unmatched listen's `listened_at` may itself have
  been moved by bug 039, its `created_at` -- the moment the relay delivered it -- was not.

  **Why that guard has its own, wide window** (bug report 070). Pairing a listen with its own
  track uses `EXACT_WINDOW_SECONDS`, because a relayed scrobble carries LMS's timestamp. The
  same-play guard cannot: LMS records a listen when playback *starts*, while the app scrobbles
  to muma about a minute later with its own clock (production, 2026-09-25: LMS listen 37787 at
  06:08:56 UTC, the app's muma listen of the same play at 06:09:51, 55 s later). Against a
  5-second window a play the app recorded under a different track id, or left unmatched, was
  invisible, and `insert_lms_only` would have counted it a second time. The guard is a single
  symmetric window rather than one sized per track from its duration: the loader does not read
  durations, and a fixed bound is easier to reason about. The price is deliberate: an LMS listen
  within ten minutes of any other listen of the same user is never inserted, so a genuinely lost
  scrobble in the middle of a listening session stays reported-only. Losing an insert costs
  nothing that was not already lost; a double count corrupts every statistic built on top.

LMS listens whose file muma does not know are counted as `lms_unmapped` and otherwise ignored.

**Usernames are compared case-insensitively** (bug report 070). LMS's `login_name` and muma's
`users.username` are the same account, but not always the same spelling: since a login-case bug
(bug report 074) production has one person as both `user` and `Teun`, in LMS and in muma's
listens, and a case-sensitive comparison split that person into two users whose plays could
never pair. `classify()` therefore groups, pairs and applies the same-play guard on
`str.casefold()`, and `_analyse()` rewrites every name -- LMS's, muma's listens', unmatched
listens' -- to muma's canonical `users.username` (the oldest account when two spellings exist)
before classifying. An insert therefore always carries muma's spelling, never LMS's; an LMS
listen whose user muma does not know under any spelling is never insertable.

Every ordering is total (gap, then muma id, then LMS server and id), so two runs over the same
data decide the same way. After an apply the repaired rows are `exact`, which is what makes a
second run a no-op.
"""

from __future__ import annotations

import bisect
import logging
import os
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from services.music_manager.library_paths import candidate_paths

logger = logging.getLogger('music-manager.scrobble-reconcile')

#: Two listens of the same track this close together are the same play.
EXACT_WINDOW_SECONDS = 5
#: An LMS listen this close to *any* muma or unmatched listen of the same user may be that play,
#: so it is never inserted. Covers the start-versus-scrobble offset (LMS records the start, the
#: app scrobbles about a minute in; 55 s observed on production) plus clock skew between phone and
#: server, with a wide margin. The cost: a lost scrobble within ten minutes of another listen --
#: for instance a short track played twice back to back -- is reported but never inserted.
SAME_PLAY_WINDOW_SECONDS = 600
#: `scrobble_listens.source` of a listen this module inserted.
RECONCILE_SOURCE = 'lms-reconcile'
#: Sources whose time did not come from a live relay; never repaired from LMS.
IMPORTED_SOURCES = frozenset({'listenbrainz', 'listenbrainz_import'})
#: LMS `ScrobblingBackend::Internal`: the listens LMS recorded itself, at play time.
LMS_BACKEND_INTERNAL = 0
#: LMS `SyncState::PendingRemove`: a listen on its way out.
LMS_SYNC_PENDING_REMOVE = 2
#: How many rows of each class the dry run shows.
SAMPLE_LIMIT = 20
#: MariaDB's error code for a UNIQUE key collision.
DUPLICATE_ENTRY = 1062
#: Paths per `IN (...)` lookup against library_media_files.
PATH_CHUNK = 200

CLASSES = ('exact', 'shifted', 'muma_only', 'lms_only')

LMS_LISTENS_SQL = (
    'SELECT l.id AS id, l.date_time AS date_time, u.login_name AS username, '
    't.absolute_file_path AS path '
    'FROM listen l '
    'JOIN user u ON u.id = l.user_id '
    'JOIN track t ON t.id = l.track_id '
    'WHERE l.backend = ? AND (l.sync_state IS NULL OR l.sync_state != ?)'
)


@dataclass(frozen=True)
class LmsListen:
    """One listen from an LMS database, with the muma track its file resolved to (or None)."""

    server: str
    id: int
    username: str
    track_id: int | None
    at: int
    path: str = ''

    @property
    def key(self) -> tuple[str, int]:
        """The listen's identity across servers, and the last tie-breaker of every ordering."""
        return (self.server, self.id)


@dataclass(frozen=True)
class MumaListen:
    """One `scrobble_listens` row, its times as Unix seconds."""

    id: int
    username: str
    track_id: int
    at: int
    created_at: int | None
    source: str | None


@dataclass
class Classification:
    """What `classify()` decided: pairs for the two matched classes, single rows for the rest."""

    exact: list[tuple[MumaListen, LmsListen]] = field(default_factory=list)
    shifted: list[tuple[MumaListen, LmsListen]] = field(default_factory=list)
    muma_only: list[MumaListen] = field(default_factory=list)
    lms_only: list[tuple[LmsListen, bool]] = field(default_factory=list)
    lms_unmapped: list[LmsListen] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """How many rows landed in each class."""
        return {
            'exact': len(self.exact),
            'shifted': len(self.shifted),
            'muma_only': len(self.muma_only),
            'lms_only': len(self.lms_only),
            'lms_only_insertable': sum(1 for _, insertable in self.lms_only if insertable),
            'lms_unmapped': len(self.lms_unmapped),
        }


def parse_lms_datetime(value: Any) -> int:
    """An LMS `date_time` as whole Unix seconds (floored), always read as UTC.

    Wt::Dbo writes `YYYY-MM-DDTHH:MM:SS.mmm`; a space for the `T`, a missing fraction or a
    trailing `Z` are accepted too, and a number is taken as Unix seconds already. A value
    carrying an explicit offset is honoured; one without is UTC, never the local zone.
    """
    if isinstance(value, int | float):
        return int(value // 1)
    text = str(value).strip().replace(' ', 'T', 1)
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() // 1)


def _is_rewritten(listen: MumaListen) -> bool:
    """Whether the row shows a later write: `listened_at` and `created_at` differ beyond the window."""
    if listen.created_at is None:
        return True
    return abs(listen.at - listen.created_at) > EXACT_WINDOW_SECONDS


def _may_be_shifted(listen: MumaListen) -> bool:
    """A live, rewritten row: the only kind bug 039 moved and LMS can repair."""
    return (listen.source or '') not in IMPORTED_SOURCES and _is_rewritten(listen)


def _pair_greedily(
    pairs: list[tuple[int, int, tuple[str, int], MumaListen, LmsListen]],
    claimed_m: set[int],
    claimed_l: set[tuple[str, int]],
) -> list[tuple[MumaListen, LmsListen]]:
    """Take pairs smallest gap first (ties: muma id, then LMS key) while both sides are free."""
    taken: list[tuple[MumaListen, LmsListen]] = []
    for _gap, _mid, _lkey, muma, lms in sorted(pairs, key=lambda p: (p[0], p[1], p[2])):
        if muma.id in claimed_m or lms.key in claimed_l:
            continue
        claimed_m.add(muma.id)
        claimed_l.add(lms.key)
        taken.append((muma, lms))
    return taken


def _user_key(username: str) -> str:
    """The form two usernames are compared in: `user` and `Teun` are one account."""
    return username.casefold()


def _near(sorted_times: list[int], at: int, window: int) -> bool:
    """Whether any time in `sorted_times` lies within `window` seconds of `at`."""
    index = bisect.bisect_left(sorted_times, at - window)
    return index < len(sorted_times) and sorted_times[index] <= at + window


def classify(
    muma: list[MumaListen],
    lms: list[LmsListen],
    unmatched_times: dict[str, list[int]] | None = None,
) -> Classification:
    """Sort every muma and LMS listen into exactly one class (see the module docstring).

    `unmatched_times` holds, per username, the `listened_at` and `created_at` of every
    `scrobble_unmatched_listens` row as Unix seconds: an LMS listen next to one of those is a play
    muma has, just not matched, and must not be inserted a second time.
    """
    result = Classification()
    unmatched_times = unmatched_times or {}

    lms_by_group: dict[tuple[str, int], list[LmsListen]] = {}
    for heard in lms:
        if heard.track_id is None:
            result.lms_unmapped.append(heard)
            continue
        lms_by_group.setdefault((_user_key(heard.username), heard.track_id), []).append(heard)
    muma_by_group: dict[tuple[str, int], list[MumaListen]] = {}
    for kept in muma:
        muma_by_group.setdefault((_user_key(kept.username), kept.track_id), []).append(kept)

    claimed_m: set[int] = set()
    claimed_l: set[tuple[str, int]] = set()

    groups = sorted(set(lms_by_group) | set(muma_by_group))
    for group in groups:
        group_muma = muma_by_group.get(group, [])
        group_lms = lms_by_group.get(group, [])
        exact_pairs = [
            (abs(m.at - listen.at), m.id, listen.key, m, listen)
            for m in group_muma
            for listen in group_lms
            if abs(m.at - listen.at) <= EXACT_WINDOW_SECONDS
        ]
        result.exact.extend(_pair_greedily(exact_pairs, claimed_m, claimed_l))

    for group in groups:
        group_muma = [m for m in muma_by_group.get(group, []) if m.id not in claimed_m and _may_be_shifted(m)]
        group_lms = [listen for listen in lms_by_group.get(group, []) if listen.key not in claimed_l]
        shifted_pairs = [
            (m.at - listen.at, m.id, listen.key, m, listen)
            for m in group_muma
            for listen in group_lms
            if m.at - listen.at > EXACT_WINDOW_SECONDS
        ]
        result.shifted.extend(_pair_greedily(shifted_pairs, claimed_m, claimed_l))

    result.muma_only = sorted((m for m in muma if m.id not in claimed_m), key=lambda m: m.id)

    # For the insert guard: every muma listen time per user, and which (user, track) still
    # has a muma listen nobody claimed.
    muma_times: dict[str, list[int]] = {}
    for m in muma:
        bucket = muma_times.setdefault(_user_key(m.username), [])
        bucket.append(m.at)
        if m.created_at is not None:
            bucket.append(m.created_at)
    for times in muma_times.values():
        times.sort()
    sorted_unmatched: dict[str, list[int]] = {}
    for user, times in unmatched_times.items():
        sorted_unmatched.setdefault(_user_key(user), []).extend(times)
    for times in sorted_unmatched.values():
        times.sort()
    open_groups = {(_user_key(m.username), m.track_id) for m in result.muma_only}

    for group in groups:
        for listen in sorted(lms_by_group.get(group, []), key=lambda item: (item.at, item.key)):
            if listen.key in claimed_l:
                continue
            insertable = (
                group not in open_groups
                and not _near(muma_times.get(group[0], []), listen.at, SAME_PLAY_WINDOW_SECONDS)
                and not _near(sorted_unmatched.get(group[0], []), listen.at, SAME_PLAY_WINDOW_SECONDS)
            )
            result.lms_only.append((listen, insertable))
    result.shifted.sort(key=lambda pair: pair[0].id)
    result.exact.sort(key=lambda pair: pair[0].id)
    return result


def _iso(seconds: int | None) -> str | None:
    """Unix seconds as an ISO 8601 UTC string, for the report."""
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat().replace('+00:00', 'Z')


def sample(result: Classification, limit: int = SAMPLE_LIMIT) -> dict[str, list[dict]]:
    """A bounded, deterministic excerpt of each class to eyeball before applying."""
    shifted = [
        {
            'id': m.id,
            'username': m.username,
            'track_id': m.track_id,
            'source': m.source,
            'listened_at': _iso(m.at),
            'created_at': _iso(m.created_at),
            'lms_listened_at': _iso(listen.at),
            'delta_seconds': m.at - listen.at,
        }
        for m, listen in result.shifted[:limit]
    ]
    muma_only = [
        {'id': m.id, 'username': m.username, 'track_id': m.track_id, 'source': m.source, 'listened_at': _iso(m.at)}
        for m in result.muma_only[:limit]
    ]
    lms_only = [
        {
            'server': listen.server,
            'lms_listen_id': listen.id,
            'username': listen.username,
            'track_id': listen.track_id,
            'listened_at': _iso(listen.at),
            'insertable': insertable,
        }
        for listen, insertable in result.lms_only[:limit]
    ]
    lms_unmapped = [
        {'server': listen.server, 'lms_listen_id': listen.id, 'username': listen.username, 'path': listen.path}
        for listen in result.lms_unmapped[:limit]
    ]
    return {'shifted': shifted, 'muma_only': muma_only, 'lms_only': lms_only, 'lms_unmapped': lms_unmapped}


# --- loading ---------------------------------------------------------------------------------


def read_lms_listens(server_conn: sqlite3.Connection, server: str, username: str | None = None) -> list[dict]:
    """The listens LMS recorded itself (Internal backend, not pending removal), with login and path."""
    sql = LMS_LISTENS_SQL
    params: list[Any] = [LMS_BACKEND_INTERNAL, LMS_SYNC_PENDING_REMOVE]
    if username is not None:
        sql += ' AND u.login_name = ? COLLATE NOCASE'
        params.append(username)
    rows = []
    for listen_id, date_time, login, path in server_conn.execute(sql, params):
        rows.append({'server': server, 'id': int(listen_id), 'date_time': date_time, 'username': login, 'path': path})
    return rows


def resolve_paths(cursor, paths: list[str]) -> dict[str, int]:
    """LMS file path -> muma track id, via every spelling `candidate_paths` knows.

    The first spelling that muma has wins, in `candidate_paths` order; a path muma knows under
    no spelling is absent from the result.
    """
    resolved: dict[str, int] = {}
    unique = sorted({p for p in paths if p})
    for start in range(0, len(unique), PATH_CHUNK):
        chunk = unique[start : start + PATH_CHUNK]
        spellings = {path: candidate_paths(path) for path in chunk}
        wanted = sorted({s for options in spellings.values() for s in options})
        placeholders = ', '.join(['%s'] * len(wanted))
        cursor.execute(
            'SELECT file_path, track_id FROM library_media_files '  # nosec B608 - placeholders only
            f'WHERE track_id IS NOT NULL AND file_path IN ({placeholders})',
            wanted,
        )
        known = {row['file_path']: int(row['track_id']) for row in cursor.fetchall()}
        for path, options in spellings.items():
            for spelling in options:
                if spelling in known:
                    resolved[path] = known[spelling]
                    break
    return resolved


def load_lms_listens(cursor, servers: list[tuple[sqlite3.Connection, str]], username: str | None) -> list[LmsListen]:
    """Every server's own listens, resolved to muma tracks, one row per (user, track, second)."""
    raw = []
    for server_conn, server in servers:
        raw.extend(read_lms_listens(server_conn, server, username))
    mapping = resolve_paths(cursor, [row['path'] for row in raw])
    seen: set[tuple[str, int | None, int]] = set()
    listens = []
    for row in sorted(raw, key=lambda r: (r['server'], r['id'])):
        at = parse_lms_datetime(row['date_time'])
        track_id = mapping.get(row['path'])
        identity = (_user_key(row['username']), track_id, at)
        if track_id is not None and identity in seen:
            continue  # the same play on two servers, or twice in one
        seen.add(identity)
        listens.append(LmsListen(row['server'], row['id'], row['username'], track_id, at, row['path'] or ''))
    return listens


def load_muma_listens(cursor, username: str | None) -> list[MumaListen]:
    """`scrobble_listens` rows with a track, as Unix seconds (session must be on +00:00)."""
    sql = (
        'SELECT id, username, track_id, UNIX_TIMESTAMP(listened_at) AS at, '
        'UNIX_TIMESTAMP(created_at) AS created, source '
        'FROM scrobble_listens WHERE track_id IS NOT NULL'
    )
    params: tuple = ()
    if username is not None:
        sql += ' AND username = %s'
        params = (username,)
    cursor.execute(sql, params)
    return [
        MumaListen(
            id=int(row['id']),
            username=row['username'],
            track_id=int(row['track_id']),
            at=int(row['at']),
            created_at=int(row['created']) if row['created'] is not None else None,
            source=row['source'],
        )
        for row in cursor.fetchall()
    ]


def load_unmatched_times(cursor, username: str | None) -> dict[str, list[int]]:
    """Per user, the Unix-second `listened_at` and `created_at` of every unmatched listen."""
    sql = (
        'SELECT username, UNIX_TIMESTAMP(listened_at) AS at, UNIX_TIMESTAMP(created_at) AS created '
        'FROM scrobble_unmatched_listens'
    )
    params: tuple = ()
    if username is not None:
        sql += ' WHERE username = %s'
        params = (username,)
    cursor.execute(sql, params)
    times: dict[str, list[int]] = {}
    for row in cursor.fetchall():
        bucket = times.setdefault(row['username'], [])
        bucket.append(int(row['at']))
        if row['created'] is not None:
            bucket.append(int(row['created']))
    return times


# --- running ---------------------------------------------------------------------------------


class ZoneMismatchError(RuntimeError):
    """The process and the database session disagree about the local zone; see `zone_check()`."""


def zone_check(conn) -> dict[str, Any]:
    """Whether the relay's naive `listened_at` values were stored as the instant they named.

    `routers/scrobbler.py` writes `datetime.fromtimestamp(ts)` -- local time of this process --
    and MariaDB interprets that naive value in the session's zone. Both are UTC in the shipped
    containers. When the two offsets differ, every stored listen is off by the difference and a
    comparison against LMS's UTC is meaningless. Must run on a session that has not been pinned.
    """
    now = datetime.now().astimezone().utcoffset()
    process_offset = int(now.total_seconds()) if now is not None else 0
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW()) AS offset_seconds, @@session.time_zone AS zone'
        )
        row = cursor.fetchone() or {}
    database_offset = int(row.get('offset_seconds') or 0)
    # The two clocks are read a moment apart; zones differ by whole quarter hours at least.
    database_offset = round(database_offset / 60) * 60
    return {
        'process_offset_seconds': process_offset,
        'database_offset_seconds': database_offset,
        'database_zone': row.get('zone'),
        'consistent': process_offset == database_offset,
    }


def _pin_utc(cursor) -> str:
    """Put the session on +00:00 and return the zone it had, for `_restore_zone`."""
    cursor.execute('SELECT @@session.time_zone AS zone')
    row = cursor.fetchone()
    previous = row['zone'] if row else 'SYSTEM'
    cursor.execute("SET time_zone = '+00:00'")
    return previous


def _restore_zone(conn, previous: str) -> None:
    """Give a pooled connection back with the zone it came with."""
    try:
        with conn.cursor() as cursor:
            cursor.execute('SET time_zone = %s', (previous,))
    except Exception as exc:  # pragma: no cover - a dead connection is dropped by the pool anyway
        logger.warning('Could not restore the session time zone: %s', exc)


def open_servers(targets: list[tuple[str, str]]) -> list[tuple[sqlite3.Connection, str]]:
    """Open each server database read-only; the same file reached twice is opened once.

    `targets` comes from `lms_db_targets()`, which has already dropped every file without the
    core LMS schema (production's stale `alpha/lms.db`, bug reports 069 and 070), so nothing is
    re-checked here.
    """
    seen: set[str] = set()
    opened = []
    for path, server in targets:
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        try:
            server_conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        except sqlite3.Error as exc:
            logger.warning('scrobble reconcile: could not open %s (%s): %s', path, server, exc)
            continue
        opened.append((server_conn, server))
    return opened


def load_canonical_usernames(cursor) -> dict[str, str]:
    """Case-folded name -> muma's `users.username`; the oldest account wins a spelling clash."""
    cursor.execute('SELECT username FROM users ORDER BY id')
    canonical: dict[str, str] = {}
    for row in cursor.fetchall():
        canonical.setdefault(_user_key(row['username']), row['username'])
    return canonical


def canonicalize(
    canonical: dict[str, str],
    muma: list[MumaListen],
    lms: list[LmsListen],
    unmatched: dict[str, list[int]],
) -> tuple[list[MumaListen], list[LmsListen], dict[str, list[int]]]:
    """Every username rewritten to muma's spelling, so per-user totals and inserts agree.

    A name muma's `users` table lacks keeps the spelling muma's own listens use for it, and
    `canonical` learns that spelling (so an LMS listen of the same person follows it). A name
    only LMS knows is left as LMS spells it; `_analyse` never inserts those.
    """
    for kept in muma:
        canonical.setdefault(_user_key(kept.username), kept.username)
    for user in sorted(unmatched):
        canonical.setdefault(_user_key(user), user)

    def spell(name: str) -> str:
        return canonical.get(_user_key(name), name)

    muma = [replace(m, username=spell(m.username)) for m in muma]
    lms = [replace(listen, username=spell(listen.username)) for listen in lms]
    merged: dict[str, list[int]] = {}
    for user, times in unmatched.items():
        merged.setdefault(spell(user), []).extend(times)
    return muma, lms, merged


def _analyse(cursor, servers, username: str | None) -> Classification:
    """Load both sides for `username` (or everyone), unify the spellings and classify them."""
    lms = load_lms_listens(cursor, servers, username)
    muma = load_muma_listens(cursor, username)
    unmatched = load_unmatched_times(cursor, username)
    canonical = load_canonical_usernames(cursor)
    muma, lms, unmatched = canonicalize(canonical, muma, lms, unmatched)
    result = classify(muma, lms, unmatched)
    # A user muma has never heard of under any spelling gets no listens inserted in their name.
    result.lms_only = [
        (listen, insertable and _user_key(listen.username) in canonical) for listen, insertable in result.lms_only
    ]
    return result


def _per_user(result: Classification) -> dict[str, dict[str, int]]:
    """The class counts split by username."""
    users: dict[str, Classification] = {}
    for pair in result.exact:
        users.setdefault(pair[0].username, Classification()).exact.append(pair)
    for pair in result.shifted:
        users.setdefault(pair[0].username, Classification()).shifted.append(pair)
    for m in result.muma_only:
        users.setdefault(m.username, Classification()).muma_only.append(m)
    for item in result.lms_only:
        users.setdefault(item[0].username, Classification()).lms_only.append(item)
    for listen in result.lms_unmapped:
        users.setdefault(listen.username, Classification()).lms_unmapped.append(listen)
    return {user: users[user].counts() for user in sorted(users)}


def dry_run(conn, servers, username: str | None = None, limit: int = SAMPLE_LIMIT) -> dict:
    """Classify without writing anything: totals, per-user counts and a sample of each class."""
    zones = zone_check(conn)
    with conn.cursor() as cursor:
        previous = _pin_utc(cursor)
    try:
        with conn.cursor() as cursor:
            result = _analyse(cursor, servers, username)
    finally:
        _restore_zone(conn, previous)
    return {
        'username': username,
        'servers': [server for _, server in servers],
        'zones': zones,
        'totals': result.counts(),
        'users': _per_user(result),
        'sample': sample(result, limit),
    }


def _is_duplicate(exc: Exception) -> bool:
    """Whether `exc` is MariaDB's 1062, a UNIQUE key collision (checked by code, not by class)."""
    args: tuple[Any, ...] = tuple(getattr(exc, 'args', ()))
    return len(args) > 0 and args[0] == DUPLICATE_ENTRY


def _apply_user(conn, result: Classification, apply_shifted: bool, insert_lms_only: bool) -> dict[str, int]:
    """Write one user's repairs in one transaction; a UNIQUE collision is skipped and counted."""
    totals = {'shifted_fixed': 0, 'lms_only_inserted': 0, 'collisions': 0, 'changed_since_read': 0}
    conn.begin()
    try:
        with conn.cursor() as cursor:
            if apply_shifted:
                for muma, listen in result.shifted:
                    try:
                        # The old value in the WHERE: a row that changed since it was read is left alone.
                        changed = cursor.execute(
                            'UPDATE scrobble_listens SET listened_at = FROM_UNIXTIME(%s) '
                            'WHERE id = %s AND listened_at = FROM_UNIXTIME(%s)',
                            (listen.at, muma.id, muma.at),
                        )
                    except Exception as exc:
                        if not _is_duplicate(exc):
                            raise
                        totals['collisions'] += 1
                        continue
                    totals['shifted_fixed' if changed else 'changed_since_read'] += 1
            if insert_lms_only:
                for listen, insertable in result.lms_only:
                    if not insertable:
                        continue
                    try:
                        cursor.execute(
                            'INSERT INTO scrobble_listens (track_id, listened_at, username, source, match_method) '
                            "VALUES (%s, FROM_UNIXTIME(%s), %s, %s, 'exact')",
                            (listen.track_id, listen.at, listen.username, RECONCILE_SOURCE),
                        )
                    except Exception as exc:
                        if not _is_duplicate(exc):
                            raise
                        totals['collisions'] += 1
                        continue
                    totals['lms_only_inserted'] += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return totals


def _split_by_user(result: Classification) -> dict[str, Classification]:
    """One Classification per username, holding only what that user's transaction writes."""
    users: dict[str, Classification] = {}
    for pair in result.shifted:
        users.setdefault(pair[0].username, Classification()).shifted.append(pair)
    for item in result.lms_only:
        users.setdefault(item[0].username, Classification()).lms_only.append(item)
    return users


def apply(conn, servers, username: str | None, apply_shifted: bool, insert_lms_only: bool) -> dict:
    """Classify, then write the chosen repairs, one transaction per user. Returns the totals.

    Raises `ZoneMismatchError` before touching anything when `zone_check()` fails.
    """
    zones = zone_check(conn)
    if not zones['consistent']:
        raise ZoneMismatchError(
            f"process offset {zones['process_offset_seconds']}s != database offset "
            f"{zones['database_offset_seconds']}s; stored listen times cannot be compared with LMS"
        )
    with conn.cursor() as cursor:
        previous = _pin_utc(cursor)
    try:
        with conn.cursor() as cursor:
            result = _analyse(cursor, servers, username)
        written = {'shifted_fixed': 0, 'lms_only_inserted': 0, 'collisions': 0, 'changed_since_read': 0}
        per_user: dict[str, dict[str, int]] = {}
        for user, part in sorted(_split_by_user(result).items()):
            totals = _apply_user(conn, part, apply_shifted, insert_lms_only)
            per_user[user] = totals
            for key, value in totals.items():
                written[key] += value
    finally:
        _restore_zone(conn, previous)
    return {
        'username': username,
        'servers': [server for _, server in servers],
        'apply_shifted': apply_shifted,
        'insert_lms_only': insert_lms_only,
        'zones': zones,
        'found': result.counts(),
        'written': written,
        'users': per_user,
    }
