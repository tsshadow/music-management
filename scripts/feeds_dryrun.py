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
from datetime import datetime

from services.music_manager.feeds.build import build_feed, resolve_profile
from services.music_manager.feeds.policy import POLICIES, STARTING_GENRES_SETTING, FeedPolicy, parse_starting_genres

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


def print_hardness(feed) -> None:
    """The numbers only a hardness-band feed (`daily-mix-soft`/`-mid`/`-hard`)

    carries: the listener's own (soft/mid, mid/hard) edges, how many of their
    heard tracks resolved a hardness from each source in `track_hardness`'s
    fallback chain, and whether the release window had to be widened to reach
    `MIN_BAND_CANDIDATES`. Silent for every other slug -- `feed.hardness_band`
    is None there, exactly as build.py leaves it.
    """
    if feed.hardness_band is None:
        return
    lo, hi = feed.hardness_band
    print(f'-- hardness band ({feed.title}) --')
    print(f'  edges: {lo:.1f} / {hi:.1f}')
    if feed.hardness_source_counts:
        for source, count in sorted(feed.hardness_source_counts.items(), key=lambda item: -item[1]):
            print(f'  {source:>8}: {count}')
    if feed.relaxed_to is not None:
        print(f'  relaxed release window to: {feed.relaxed_to}')
    if feed.filled_from_unknown:
        print(f'  filled from unknown-hardness candidates: {feed.filled_from_unknown}')


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
    parser.add_argument(
        '--starting-genres',
        default=None,
        help=(
            'override the configured fallback genres (comma-separated). Only reached when neither '
            f'the listener nor the server has any history; defaults to the {STARTING_GENRES_SETTING} setting.'
        ),
    )
    args = parser.parse_args(argv)

    policy = policy_for(args.slug, args.window, args.size, args.max_seconds)

    # Deferred: get_db_connection's own module does nothing at import time beyond load_dotenv,
    # but every other database-touching entry point in this repo defers the same way (see
    # backfill_release_dates.py), and this is a script the test loader must be able to import
    # with no database reachable at all. ConfigStore is deferred for the same reason: it creates
    # its config directory on construction.
    from services.common.config_store import ConfigStore
    from services.music_manager.database import get_db_connection

    if args.starting_genres is not None:
        starting_genres = parse_starting_genres(args.starting_genres)
    else:
        starting_genres = parse_starting_genres(ConfigStore().get(STARTING_GENRES_SETTING))

    conn = get_db_connection()
    if not conn:
        sys.exit('Could not open a database connection.')
    try:
        now = datetime.now()
        # The same resolution build_feed runs -- including the configured fallback, which the
        # old hand copy of these steps silently left out, so the one path this tool exists to
        # measure was the one it could not show.
        resolution = resolve_profile(conn, args.username, policy.profile_window_days, now, starting_genres)
        feed = build_feed(conn, args.username, policy, now, starting_genres=starting_genres)
    finally:
        conn.close()

    title = f'  title={feed.title!r}' if feed.title else ''
    print(f'{feed.slug}  username={args.username}  state={feed.state}  scope={feed.scope}{title}')
    print_hardness(feed)
    print_report(resolution.shares, feed.funnel, _limited(feed.tracks, args.limit))
    return 0


if __name__ == '__main__':
    sys.exit(main())
