"""Prints the feed funnel for one listener, so the policy numbers can be chosen from evidence.

Every number in `feeds/policy.py` -- the seven-day radar window, the thirty places, the ten-minute
song ceiling -- is a proposed default, never measured against the real library (see
docs/designs/feeds/functional.md, Open Questions). This is the tool for measuring it: it shows the
funnel stage by stage, so a window that leaves two candidates or two hundred is visible before it
ships, and it shows the resulting tracks with the bucket and reason each was placed for.

No client is built on top of `build_feed` yet; this and `GET /api/feeds/{slug}` are what exists.

Usage:
    python scripts/feeds_dryrun.py --username user --slug release-radar --window 14
"""

import argparse
import dataclasses
import sys
from collections import defaultdict
from datetime import datetime

from services.music_manager.feeds.build import RAMP_TRACKS, build_feed
from services.music_manager.feeds.policy import POLICIES, FeedPolicy
from services.music_manager.feeds.profile import TasteProfile, blend, build_profile, genre_shares
from services.music_manager.feeds.queries import exclusions_query, hierarchy_query, listens_query

FUNNEL_STAGES = ('candidates', 'bucketed', 'allocated', 'capped', 'emitted')


def policy_for(slug: str, window: int | None, size: int | None, max_seconds: int | None) -> FeedPolicy:
    """The named policy with any of the three tunables overridden.

    `FeedPolicy` is frozen (see policy.py: one number changing must never be a second query), so an
    override is a new instance built with `dataclasses.replace`, not a mutation.
    """
    policy = POLICIES.get(slug)
    if policy is None:
        sys.exit(f"Unknown feed slug {slug!r}. Choose one of: {', '.join(sorted(POLICIES))}.")
    overrides = {}
    if window is not None:
        overrides['release_window_days'] = window
    if size is not None:
        overrides['size'] = size
    if max_seconds is not None:
        overrides['max_track_seconds'] = max_seconds
    return dataclasses.replace(policy, **overrides) if overrides else policy


def print_report(shares: dict, funnel: dict, tracks: list[dict]) -> None:
    print('-- shares --')
    for name, share in sorted(shares.items(), key=lambda item: -item[1]):
        print(f'  {share:6.1%}  {name}')

    print('-- funnel --')
    for stage in FUNNEL_STAGES:
        if stage in funnel:
            print(f'  {stage:>10}: {funnel[stage]}')

    print('-- tracks --')
    for track in tracks:
        print(
            f"  [{track.get('bucket')}] {track.get('artist')} - {track.get('title')} "
            f"({track.get('release_date')}) -- {track.get('reason')}"
        )


# The rest of this file is the same connection-touching plumbing build.py and routers/feeds.py
# each already carry (see build.py: "the only module in `feeds/` that touches a database
# connection" -- scoped to that package, not to a script sitting outside it). It is duplicated
# again here rather than imported from either, because build_feed never returns the shares it
# computed on the way to a feed, and this script's whole point is to show that intermediate step.


def _split(csv: str | None) -> list[str]:
    return [part for part in (csv or '').split(',') if part]


def _rows(conn, sql: str, params=None) -> list[dict]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _hierarchy(conn) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = defaultdict(set)
    for row in _rows(conn, hierarchy_query()):
        parents[row['subgenre'].lower()].add(row['genre'].lower())
    return dict(parents)


def _exclusions(conn, username: str) -> dict[str, set[str]]:
    sql, params = exclusions_query(username)
    exclusions: dict[str, set[str]] = {'artist': set(), 'label': set(), 'genre': set()}
    for row in _rows(conn, sql, params):
        exclusions.setdefault(row['entity_type'], set()).add(row['entity_name'].lower())
    return exclusions


def _listens(conn, username: str | None, window_days: int, now: datetime) -> list[dict]:
    sql, params = listens_query(username, window_days, now)
    return [
        {**row, 'labels': _split(row.get('labels')), 'genres': _split(row.get('genres'))}
        for row in _rows(conn, sql, params)
    ]


def shares_for(conn, username: str, policy: FeedPolicy, now: datetime) -> dict[str, float]:
    """Steps 1-3 of build_feed (see build.py), kept only so the dry run can show *why* the
    funnel looks the way it does."""
    parents = _hierarchy(conn)
    exclusions = _exclusions(conn, username)
    user_rows = _listens(conn, username, policy.profile_window_days, now)
    user_profile = build_profile(user_rows, parents, exclusions, now)
    if user_profile.distinct_tracks < RAMP_TRACKS:
        server_rows = _listens(conn, None, policy.profile_window_days, now)
        server_profile = build_profile(server_rows, parents, exclusions, now)
    else:
        server_profile = TasteProfile()
    profile = blend(user_profile, server_profile, ramp_tracks=RAMP_TRACKS)
    return genre_shares(profile, parents)


def _limited(tracks: list[dict], limit: int | None) -> list[dict]:
    """The first `limit` tracks, or all of them when `limit` is None.

    `0 if limit else tracks` would read `--limit 0` (show nothing) the same as no `--limit` at all
    (show everything), because `0` is falsy -- an `is not None` check is required to tell "not
    given" apart from "given as zero".
    """
    return tracks if limit is None else tracks[:limit]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--username', required=True, help='listener to build the feed for')
    parser.add_argument('--slug', required=True, choices=sorted(POLICIES), help='which feed policy to run')
    parser.add_argument('--window', type=int, default=None, help='override release_window_days')
    parser.add_argument('--size', type=int, default=None, help='override the number of places')
    parser.add_argument('--max-seconds', type=int, default=None, help='override max_track_seconds')
    parser.add_argument('--limit', type=int, default=None, help='only print the first N ranked tracks')
    args = parser.parse_args(argv)

    policy = policy_for(args.slug, args.window, args.size, args.max_seconds)

    # Deferred: get_db_connection's own module does nothing at import time beyond load_dotenv,
    # but every other database-touching entry point in this repo defers the same way (see
    # backfill_release_dates.py), and this is a script the test loader must be able to import
    # with no database reachable at all.
    from services.music_manager.database import get_db_connection

    conn = get_db_connection()
    if not conn:
        sys.exit('Could not open a database connection.')
    try:
        now = datetime.now()
        shares = shares_for(conn, args.username, policy, now)
        feed = build_feed(conn, args.username, policy, now)
    finally:
        conn.close()

    print(f'{feed.slug}  username={args.username}  state={feed.state}  scope={feed.scope}')
    print_report(shares, feed.funnel, _limited(feed.tracks, args.limit))
    return 0


if __name__ == '__main__':
    sys.exit(main())
