"""The feeds snapshot: one built feed per listener, per slug, per day, read back as a table row.

docs/designs/feeds/home-load.md, "Step 3". A feed build is seconds of profile, candidate and
hardness work; opening the Home screen used to run four of them, plus a listing that resolved the
profile seven more times. The daily mixes are stable for a day by design (their order is a hash of
username, date and track), so building one more than once a day was pure waste, and the radar only
changes as scans land, which is hourly. So every `GET /api/feeds/{slug}` answer is stored here as the
JSON it was sent as, and a request reads the row when it is fresh and builds only when it is not.

Freshness, per slug:

- a daily mix (any `daily-mix*` policy) and the listing (`LIST_SLUG`): fresh for the whole
  `feed_date` it was built on -- as long as it has something in it;
- `release-radar`: fresh for `RADAR_TTL_SECONDS` after `generated_at`;
- a feed whose `state` is not `'ok'` (`not_enough_data`, `no_matches`): fresh for only
  `NON_OK_TTL_SECONDS`, whatever its slug. An empty mix is an answer about the data at build
  time, and the data changes: a listener who opens Home before their first listen must see
  their mixes fill in once they have listened, not tomorrow (bug report 049);
- any row: stale the moment the key it was built under (`params_key`) differs from the current
  one. The key covers the settings, the curated genre hardness and the listener's exclusions
  (`routers/feeds.py`, `params_key`), so an edit to any of them is seen on the next read rather
  than tomorrow.

`feed_date` is the calendar day in the configured zone (`clock.feed_date`), not the container's
UTC day, so the mixes roll over at local midnight.

A build for a key runs under a per-key lock. A second request for the same key while a build is
running reads the previous row if there is one, and waits for the build if there is not; it never
starts a second build of the same thing. `run_feeds_refresh` walks every active listener's stale
rows in the background so the read path almost never has to build at all.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta

from services.music_manager.database import get_db_connection
from services.music_manager.feeds import clock

logger = logging.getLogger(__name__)

#: The row the listing (`GET /api/feeds`) is stored under. Not a policy slug, and never will be:
#: policies are hyphenated words, and a leading underscore keeps this out of that namespace.
LIST_SLUG = '_list'

#: How long a release-radar row stays fresh. Scans and release_date_sync land hourly, so a
#: radar older than that may be missing a release the library already has.
RADAR_TTL_SECONDS = int(os.getenv('FEEDS_RADAR_TTL_SECONDS', '3600'))

#: How long a feed that came out empty (`state` other than `'ok'`) stays fresh. Short, because
#: the likeliest reason is a listener with no history yet, and that changes with one listen.
NON_OK_TTL_SECONDS = int(os.getenv('FEEDS_NON_OK_TTL_SECONDS', '900'))

#: How often the background loop looks for stale rows to rebuild.
REFRESH_INTERVAL_SECONDS = int(os.getenv('FEEDS_REFRESH_INTERVAL_SECONDS', '900'))

#: Who gets a warm snapshot: anyone with a listen in this many days. A listener outside that
#: window still gets a feed on request; it is just built on the first read of the day.
ACTIVE_LISTENER_DAYS = 30

_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def init_db(cursor) -> None:
    """Create feeds_snapshot if it does not exist yet."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS feeds_snapshot (
            username     VARCHAR(255) NOT NULL,
            slug         VARCHAR(64)  NOT NULL,
            feed_date    DATE         NOT NULL,
            generated_at DATETIME     NOT NULL,
            params_key   VARCHAR(64)  NOT NULL,
            payload      LONGTEXT     NOT NULL,
            PRIMARY KEY (username, slug, feed_date)
        )
        """
    )


def _lock_for(username: str, slug: str) -> threading.Lock:
    """The one lock every build of `(username, slug)` in this process runs under."""
    with _locks_guard:
        return _locks.setdefault((username, slug), threading.Lock())


def is_fresh(
    slug: str,
    generated_at: datetime,
    params_key: str,
    row_params_key: str,
    now: datetime,
    state: str | None = None,
) -> bool:
    """Whether a row built at `generated_at` under `row_params_key` still answers for `now`.

    The caller has already matched the row on `feed_date`, so a daily mix here is by
    definition today's; only the radar, an empty result (`state` other than `'ok'`) and a
    change to the build key can age a row within its day. `state` is the stored payload's
    `state`; None (the listing, which has none) counts as `'ok'`.
    """
    if row_params_key != params_key:
        return False
    if state not in (None, 'ok'):
        return now - generated_at < timedelta(seconds=NON_OK_TTL_SECONDS)
    if slug == 'release-radar':
        return now - generated_at < timedelta(seconds=RADAR_TTL_SECONDS)
    return True


def _row_is_fresh(row: dict | None, slug: str, params_key: str, now: datetime) -> bool:
    """`is_fresh` for a row as `read` returns it; a missing row is never fresh."""
    if not row:
        return False
    payload = row['payload']
    state = payload.get('state') if isinstance(payload, dict) else None
    return is_fresh(slug, row['generated_at'], params_key, row['params_key'], now, state)


def read(conn, username: str, slug: str, feed_date: date) -> dict | None:
    """`{'generated_at', 'params_key', 'payload'}` for the row, or None."""
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT generated_at, params_key, payload FROM feeds_snapshot '
            'WHERE username = %s AND slug = %s AND feed_date = %s',
            (username, slug, feed_date),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        'generated_at': row['generated_at'],
        'params_key': row['params_key'],
        'payload': json.loads(row['payload']),
    }


def write(
    conn, username: str, slug: str, feed_date: date, generated_at: datetime, params_key: str, payload: dict
) -> None:
    """Store one feed's payload for `username`, replacing the one for the same day."""
    with conn.cursor() as cursor:
        cursor.execute(
            'INSERT INTO feeds_snapshot (username, slug, feed_date, generated_at, params_key, payload) '
            'VALUES (%s, %s, %s, %s, %s, %s) '
            'ON DUPLICATE KEY UPDATE generated_at = VALUES(generated_at), '
            'params_key = VALUES(params_key), payload = VALUES(payload)',
            (username, slug, feed_date, generated_at, params_key, json.dumps(payload, default=str)),
        )
    conn.commit()


def delete_user(conn, username: str) -> None:
    """Every row of one listener -- what an exclusion change does, so the next read
    rebuilds with the exclusion applied instead of serving a mix it still influences."""
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM feeds_snapshot WHERE username = %s', (username,))
    conn.commit()


def purge_before(conn, feed_date: date) -> int:
    """Delete every snapshot older than `feed_date`; returns how many went."""
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM feeds_snapshot WHERE feed_date < %s', (feed_date,))
        deleted = int(cursor.rowcount or 0)
    conn.commit()
    return deleted


def serve(
    conn, username: str, slug: str, now: datetime, params_key: str, build: Callable[[], dict]
) -> tuple[dict, str]:
    """The payload for `(username, slug)` at `now`, and where it came from.

    Returns `(payload, source)` with `source` one of `'snapshot'` (a fresh row),
    `'stale'` (an aged row, served because another thread is already rebuilding it)
    or `'live'` (built here, and written for the next reader). `build` runs at most
    once per key at a time across every thread of this process. `params_key` must be
    computed before `build` runs, so whatever changes during the build ages the row.
    """
    feed_date = clock.feed_date(now)
    row = read(conn, username, slug, feed_date)
    if row and _row_is_fresh(row, slug, params_key, now):
        return row['payload'], 'snapshot'

    lock = _lock_for(username, slug)
    if not lock.acquire(blocking=False):
        if row:
            return row['payload'], 'stale'
        lock.acquire()
    try:
        # Whoever held the lock may have written the row we were about to build.
        row = read(conn, username, slug, feed_date)
        if row and _row_is_fresh(row, slug, params_key, now):
            return row['payload'], 'snapshot'
        started = time.monotonic()
        payload = build()
        write(conn, username, slug, feed_date, now, params_key, payload)
        logger.info(
            'feeds.build slug=%s user=%s total_ms=%d source=live',
            slug,
            username,
            int((time.monotonic() - started) * 1000),
        )
        return payload, 'live'
    finally:
        lock.release()


def active_listeners(conn, now: datetime) -> list[str]:
    """The users who listened to anything within ACTIVE_LISTENER_DAYS of `now`."""
    cutoff = now - timedelta(days=ACTIVE_LISTENER_DAYS)
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT DISTINCT username FROM scrobble_listens WHERE listened_at >= %s ORDER BY username',
            (cutoff,),
        )
        return [row['username'] for row in cursor.fetchall()]


def refresh_stale(
    conn,
    now: datetime,
    params_key: Callable[[object, str, str], str],
    slugs: list[str],
    build: Callable[[object, str, str], dict],
) -> int:
    """One pass: rebuild every stale `(listener, slug)` and drop yesterday's rows.

    `params_key(conn, username, slug)` is the key a row for that listener and slug must
    carry to be fresh; it is asked before the build, so a change that lands while the
    build runs leaves the new row stale instead of passing for current. `build(conn,
    username, slug)` produces the payload for one key. Returns how many rows were
    rebuilt. A build that raises is logged and skipped, so one listener whose history
    trips something cannot stop everyone else's mixes from refreshing.

    A listener who opened Home before their first listen holds non-ok rows; once they
    have listened they are an active listener, those rows go stale after
    `NON_OK_TTL_SECONDS`, and this pass fills their mixes in the same day.
    """
    rebuilt = 0
    today = clock.feed_date(now)
    for username in active_listeners(conn, now):
        for slug in slugs:
            try:
                key = params_key(conn, username, slug)
            except Exception:
                logger.exception('feeds.refresh could not compute the key for slug=%s user=%s', slug, username)
                continue
            row = read(conn, username, slug, today)
            if _row_is_fresh(row, slug, key, now):
                continue
            lock = _lock_for(username, slug)
            if not lock.acquire(blocking=False):
                continue  # a request is building this one right now
            try:
                started = time.monotonic()
                payload = build(conn, username, slug)
                write(conn, username, slug, today, now, key, payload)
                rebuilt += 1
                logger.info(
                    'feeds.build slug=%s user=%s total_ms=%d source=refresh',
                    slug,
                    username,
                    int((time.monotonic() - started) * 1000),
                )
            except Exception:
                logger.exception('feeds.refresh failed for slug=%s user=%s', slug, username)
            finally:
                lock.release()
    purge_before(conn, today)
    return rebuilt


def run_feeds_refresh(
    slugs: list[str],
    params_key: Callable[[object, str, str], str],
    build: Callable[[object, str, str], dict],
    sleep_seconds: int = REFRESH_INTERVAL_SECONDS,
    once: bool = False,
) -> None:
    """The `feeds-refresh` thread: a pass on start, then one every `sleep_seconds`.

    `params_key` is called per pass, not once, so a settings change between passes
    ages every row and the next pass rebuilds them. `once=True` is for tests.
    """
    while True:
        conn = get_db_connection()
        if conn:
            try:
                rebuilt = refresh_stale(conn, datetime.now(), params_key, slugs, build)
                if rebuilt:
                    logger.info('feeds.refresh rebuilt %d snapshot(s)', rebuilt)
            except Exception:
                logger.exception('feeds.refresh pass failed')
            finally:
                conn.close()
        if once:
            return
        time.sleep(sleep_seconds)
