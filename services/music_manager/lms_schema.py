"""Which of the `lms.db` files music-manager can see are real LMS databases.

`routers.users.lms_db_targets()` finds every `<root>/*/lms.db`. On production one of them,
`/app/data/alpha/lms.db`, is a leftover at LMS schema 114: no `user` table, no server behind
it. Every consumer used to meet it on its own -- the reconcile answered 500 (bug report 069),
the song-version sync decided it was "still migrating" and logged that at INFO every one to two
minutes (bug report 070). The check lives here, once, and `lms_db_targets()` applies it before
any consumer sees the list, so no consumer has to re-check.

A file that fails the check is dropped with one WARNING per process per path: the list is
rebuilt every sync pass and every retry, and a warning each time would be the same noise under a
louder level. Only the warning is remembered, never the verdict -- a file that becomes a real
database later (a server finishing its first start) is picked up on the next call.
"""

from __future__ import annotations

import logging
import sqlite3
import threading

logger = logging.getLogger('music-manager.lms-schema')

#: The tables every consumer relies on: users and playlists sync into `user`, song versions and
#: release dates live on `track`, the reconcile reads `listen` joined to both.
LMS_REQUIRED_TABLES = frozenset({'listen', 'user', 'track'})

_warned_paths: set[str] = set()
_warned_lock = threading.Lock()


def missing_lms_tables(server_conn: sqlite3.Connection) -> set[str]:
    """The required LMS tables this database does not have."""
    rows = server_conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return set(LMS_REQUIRED_TABLES) - {row[0] for row in rows}


def _missing_in_file(path: str) -> set[str] | None:
    """The required tables absent from the file at `path`, or None when it could not be read.

    Opened read-only, so the check can never create a file or take a write lock on a live
    server's database.
    """
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        return missing_lms_tables(conn)
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def usable_lms_targets(targets: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """`targets` without the databases that lack the core LMS schema.

    A file that cannot be read at all (locked, unreadable) is kept: that is a transient
    condition every consumer already handles best-effort, and dropping it would make a live
    server vanish from a pass for no lasting reason. Only a file that answers and is missing a
    table is dropped.
    """
    usable = []
    for path, source in targets:
        missing = _missing_in_file(path)
        if not missing:
            usable.append((path, source))
            continue
        with _warned_lock:
            first = path not in _warned_paths
            _warned_paths.add(path)
        if first:
            logger.warning(
                'Ignoring %s (%s): it has no %s table(s), so it is not a live LMS database. '
                'Every LMS sync and the listen reconcile skip it; delete the file if no server '
                'uses it any more.',
                path,
                source,
                ', '.join(sorted(missing)),
            )
    return usable
