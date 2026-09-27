#!/usr/bin/env python3
"""
scripts/migrate_lms_history.py

One-off migration that reads native LMS ratings/stars/listens from a SQLite
*backup* (taken via `sqlite3 .backup`, never the live -wal file) and pushes
them into music-manager via its existing HTTP APIs:

    - ratings:  POST {api-base}/rating/lms-event   (event=rating_changed)
    - listens:  POST {api-base}/scrobble/event

This is part of the production-lms-consolidation plan (Step 2 / Step 4):
before the `lms_alpha` instance (and eventually the native LMS SQLite
databases) is retired, this script preserves whatever rating/listen history
was never exported to music-manager.

Idempotent by design: it relies on music-manager's own unique constraints
(`rating_tracks`: entity_type+entity_id+username; `scrobble_listens`:
username+listened_at+track_id), so re-running the script against the same
source data is a safe no-op for rows already imported.

Starred tracks (`starred_track`): music-manager has no separate "favorite"
concept, only a 1-5 `rating`. Per explicit decision, a star is imported as an
implicit rating=5 *only if the same user has no explicit rating for that
track already in the source LMS database* (so a real rating always wins over
an inferred one). Every starred row is additionally exported to a JSON file
(see --stars-export) with full details, so nothing is silently lost even
where an explicit rating already covers the track.

Usage:
    MUMA_API_KEY=... python3 scripts/migrate_lms_history.py \\
        --source /backups/lms_20260723.db:lms \\
        --source /backups/lms_alpha_20260723.db:lms_alpha \\
        --api-base http://localhost:18000/api \\
        [--lms-music-root /music] [--mm-music-root /mnt/music] \\
        [--stars-export docs/lms-starred-tracks-export.json] \\
        [--dry-run] [--skip-ratings] [--skip-stars] [--skip-listens]
"""
import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="PATH:LABEL",
        help="A LMS SQLite *backup* path and a short label identifying the "
        "instance (used to tag scrobble 'source' and the stars export), "
        "e.g. /backups/lms.db:lms. Repeatable.",
    )
    parser.add_argument("--api-base", required=True, help="music-manager API base URL, e.g. http://localhost:18000/api")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MUMA_API_KEY") or os.environ.get("API_KEY"),
        help="music-manager system API key (X-API-Key header). Prefer MUMA_API_KEY in the "
        "environment: a value given here is visible in `ps` and shell history.",
    )
    parser.add_argument("--lms-music-root", default="/music", help="LMS's mount prefix for absolute_file_path (default: /music)")
    parser.add_argument("--mm-music-root", default="/mnt/music", help="music-manager's mount prefix for the same files (default: /mnt/music)")
    parser.add_argument(
        "--stars-export",
        default="docs/lms-starred-tracks-export.json",
        help="Where to write the full starred-tracks export (default: docs/lms-starred-tracks-export.json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only report what would be sent, do not call the API")
    parser.add_argument("--skip-ratings", action="store_true")
    parser.add_argument("--skip-stars", action="store_true")
    parser.add_argument("--skip-listens", action="store_true")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    if not args.api_key:
        parser.error("no API key: set MUMA_API_KEY (or pass --api-key)")
    return args


@dataclass
class Report:
    label: str
    ratings_total: int = 0
    ratings_sent: int = 0
    ratings_skipped_no_muma_id: int = 0
    ratings_errors: int = 0
    stars_total: int = 0
    stars_sent_as_rating5: int = 0
    stars_kept_explicit_rating: int = 0
    stars_skipped_no_muma_id: int = 0
    stars_errors: int = 0
    listens_total: int = 0
    listens_sent: int = 0
    listens_matched: int = 0
    listens_unmatched: int = 0
    listens_skipped_no_muma_id: int = 0
    listens_errors: int = 0
    skipped_users: set = field(default_factory=set)

    def print_summary(self):
        print(f"\n=== Migration report for '{self.label}' ===")
        print(
            f"Ratings:  total={self.ratings_total} sent={self.ratings_sent} "
            f"skipped(no muma_id)={self.ratings_skipped_no_muma_id} errors={self.ratings_errors}"
        )
        print(
            f"Stars:    total={self.stars_total} sent_as_rating5={self.stars_sent_as_rating5} "
            f"kept_explicit_rating={self.stars_kept_explicit_rating} "
            f"skipped(no muma_id)={self.stars_skipped_no_muma_id} errors={self.stars_errors}"
        )
        print(
            f"Listens:  total={self.listens_total} sent={self.listens_sent} "
            f"matched={self.listens_matched} unmatched={self.listens_unmatched} "
            f"skipped(no muma_id)={self.listens_skipped_no_muma_id} errors={self.listens_errors}"
        )
        if self.skipped_users:
            print(f"Skipped LMS users with no muma_id link: {sorted(self.skipped_users)}")


def open_readonly(db_path):
    """Opens the SQLite backup strictly read-only (never mutates a backup file)."""
    uri = f"file:{Path(db_path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_username_map(api_base, api_key, timeout):
    """Builds a {music-manager user id: username} map via GET {api_base}/users."""
    resp = requests.get(f"{api_base}/users", headers={"X-API-Key": api_key}, timeout=timeout)
    resp.raise_for_status()
    users = resp.json()
    return {int(u["id"]): u["username"] for u in users}


def lms_path_to_mm_path(lms_path, lms_root, mm_root):
    """Rewrites a LMS absolute_file_path (e.g. '/music/EPs/...') to
    music-manager's equivalent mount prefix (e.g. '/mnt/music/EPs/...'), so
    the existing file_path lookup in routers/rating.py can match it.
    """
    if lms_path.startswith(lms_root):
        return mm_root.rstrip("/") + lms_path[len(lms_root):]
    return lms_path


def iso_to_unix(date_time_str):
    """LMS stores date_time as e.g. '2026-02-12T14:51:49.000' (local time, no tz)."""
    return int(datetime.strptime(date_time_str.split(".")[0], "%Y-%m-%dT%H:%M:%S").timestamp())


def resolve_username(muma_id, login_name, username_map, report, counter_attr):
    if muma_id is None:
        setattr(report, counter_attr, getattr(report, counter_attr) + 1)
        report.skipped_users.add(login_name)
        return None
    username = username_map.get(int(muma_id))
    if not username:
        setattr(report, counter_attr, getattr(report, counter_attr) + 1)
        report.skipped_users.add(login_name)
        return None
    return username


def post_rating(args, object_id, username, rating, path):
    payload = {
        "event": "rating_changed",
        "object_type": "track",
        "object_id": str(object_id),
        "username": username,
        "rating": int(rating),
        "path": path,
    }
    if args.dry_run:
        return True
    resp = requests.post(
        f"{args.api_base}/rating/lms-event", json=payload, headers={"X-API-Key": args.api_key}, timeout=args.timeout
    )
    resp.raise_for_status()
    return True


def migrate_ratings(conn, username_map, args, report):
    rows = conn.execute(
        """
        SELECT rt.rating, rt.track_id, t.absolute_file_path,
               u.id AS user_id, u.muma_id, u.login_name
        FROM rated_track rt
        JOIN track t ON t.id = rt.track_id
        JOIN user u ON u.id = rt.user_id
        """
    ).fetchall()

    for row in rows:
        report.ratings_total += 1
        username = resolve_username(row["muma_id"], row["login_name"], username_map, report, "ratings_skipped_no_muma_id")
        if not username:
            continue
        path = lms_path_to_mm_path(row["absolute_file_path"], args.lms_music_root, args.mm_music_root)
        try:
            post_rating(args, row["track_id"], username, row["rating"], path)
            report.ratings_sent += 1
        except requests.RequestException as e:
            report.ratings_errors += 1
            print(f"  [rating error] track_id={row['track_id']} user={username}: {e}", file=sys.stderr)


def migrate_stars(conn, username_map, args, report, stars_export):
    # An explicit rating always wins: only starred (track_id, user_id) pairs
    # that have NO row in rated_track are imported as an implicit rating=5.
    explicit_pairs = {
        (r["track_id"], r["user_id"])
        for r in conn.execute("SELECT track_id, user_id FROM rated_track").fetchall()
    }
    rows = conn.execute(
        """
        SELECT st.track_id, st.date_time, t.absolute_file_path, t.name, t.artist_display_name,
               u.id AS user_id, u.muma_id, u.login_name
        FROM starred_track st
        JOIN track t ON t.id = st.track_id
        JOIN user u ON u.id = st.user_id
        """
    ).fetchall()

    for row in rows:
        report.stars_total += 1
        username = resolve_username(row["muma_id"], row["login_name"], username_map, report, "stars_skipped_no_muma_id")
        has_explicit_rating = (row["track_id"], row["user_id"]) in explicit_pairs
        stars_export.append(
            {
                "label": report.label,
                "lms_login_name": row["login_name"],
                "muma_username": username,
                "track_id": row["track_id"],
                "path": row["absolute_file_path"],
                "title": row["name"],
                "artist": row["artist_display_name"],
                "starred_at": row["date_time"],
                "had_explicit_rating": has_explicit_rating,
                "imported_as_rating5": bool(username) and (not has_explicit_rating),
            }
        )
        if not username:
            continue
        if has_explicit_rating:
            report.stars_kept_explicit_rating += 1
            continue
        path = lms_path_to_mm_path(row["absolute_file_path"], args.lms_music_root, args.mm_music_root)
        try:
            post_rating(args, row["track_id"], username, 5, path)
            report.stars_sent_as_rating5 += 1
        except requests.RequestException as e:
            report.stars_errors += 1
            print(f"  [star error] track_id={row['track_id']} user={username}: {e}", file=sys.stderr)


def migrate_listens(conn, username_map, args, report):
    rows = conn.execute(
        """
        SELECT l.date_time, l.track_id, t.name, t.artist_display_name,
               u.id AS user_id, u.muma_id, u.login_name
        FROM listen l
        JOIN track t ON t.id = l.track_id
        JOIN user u ON u.id = l.user_id
        """
    ).fetchall()

    for row in rows:
        report.listens_total += 1
        username = resolve_username(row["muma_id"], row["login_name"], username_map, report, "listens_skipped_no_muma_id")
        if not username:
            continue
        listened_at = iso_to_unix(row["date_time"])
        payload = {
            "artist_name": row["artist_display_name"],
            "track_title": row["name"],
            "listened_at": listened_at,
            "username": username,
            "source": f"lms-history-import-{report.label}",
        }
        if args.dry_run:
            report.listens_sent += 1
            continue
        try:
            resp = requests.post(
                f"{args.api_base}/scrobble/event", json=payload, headers={"X-API-Key": args.api_key}, timeout=args.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            report.listens_sent += 1
            if data.get("matched"):
                report.listens_matched += 1
            else:
                report.listens_unmatched += 1
        except requests.RequestException as e:
            report.listens_errors += 1
            print(f"  [listen error] track_id={row['track_id']} user={username}: {e}", file=sys.stderr)


def parse_sources(raw_sources):
    sources = []
    for raw in raw_sources:
        if ":" not in raw:
            raise ValueError(f"Invalid --source '{raw}', expected PATH:LABEL")
        path, label = raw.rsplit(":", 1)
        sources.append((path, label))
    return sources


def main():
    args = parse_args()
    sources = parse_sources(args.source)

    if args.dry_run:
        print("*** DRY RUN: no data will be sent to music-manager ***")

    print(f"Fetching music-manager user map from {args.api_base}/users ...")
    username_map = fetch_username_map(args.api_base, args.api_key, args.timeout)
    print(f"Resolved {len(username_map)} music-manager users.")

    reports = []
    stars_export = []

    for db_path, label in sources:
        print(f"\n--- Migrating LMS history from '{db_path}' (label: {label}) ---")
        conn = open_readonly(db_path)
        report = Report(label=label)

        if not args.skip_ratings:
            migrate_ratings(conn, username_map, args, report)
        if not args.skip_stars:
            migrate_stars(conn, username_map, args, report, stars_export)
        if not args.skip_listens:
            migrate_listens(conn, username_map, args, report)

        conn.close()
        report.print_summary()
        reports.append(report)

    if stars_export:
        export_path = Path(args.stars_export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w") as f:
            json.dump(stars_export, f, indent=2, default=str)
        print(f"\nWrote {len(stars_export)} starred-track entries to {export_path}")

    total_errors = sum(r.ratings_errors + r.stars_errors + r.listens_errors for r in reports)
    if total_errors:
        print(f"\n{total_errors} error(s) occurred during migration, see above.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
