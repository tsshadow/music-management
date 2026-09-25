#!/usr/bin/env python3
"""Puts ratings back into LMS's rated_track from the two copies that survived.

Removing a media library deletes every `track` row, and `rated_track.track_id` carries
`on delete cascade`, so re-adding the library takes the ratings with it. That happened on
this library: `rated_track` holds 3 rows against an autoincrement sequence of 303.

Two copies of the lost data are still around, and neither is reachable through the
running system, because the sync only ever ran one way -- LMS pushes a `rating_changed`
event to music-management and nothing ever reads it back:

  * The `RATING` tags in the files, which LMS imports as clusters (cluster type `RATING`,
    values 20/40/60/80/100 for 1..5 stars). This is the older, larger set.
  * music-management's `rating_tracks` mirror, keyed on `track_uid`. This is the smaller,
    newer set, and it is the one that records ratings actually given in the interface.

Both are matched to tracks by file path, which is why the roots have to be bridged: LMS
reports paths under its media-library root (`/music`), music-management stores them under
the mount it scans (`/mnt/music`).

Precedence, strongest first:

  1. A row already in `rated_track` is never touched. It is by definition the most recent
     thing the user did, and it is the only source that cannot be stale.
  2. The music-management mirror, because it records a deliberate rating in the app.
  3. The `RATING` tag, which is collection metadata that predates the app.

Nothing is deleted and nothing is overwritten; the script only inserts rows for
(user, track) pairs that have none. Re-running it therefore changes nothing. The whole
prior contents of `rated_track` is written to a JSON export before any write.

Usage:
    # where the music-management database is reachable (inside the music-manager container)
    python3 scripts/restore_lms_ratings.py export-muma --out muma-ratings.json

    # where lms.db is reachable; stop LMS first so it does not hold a write lock
    python3 scripts/restore_lms_ratings.py restore \\
        --database /var/lms/lms.db \\
        --muma-json muma-ratings.json \\
        --user user \\
        [--also-user lms_user] [--no-tags] [--export rated-track-before.json] [--apply]

The mirror is also what the dynamic playlists read, so after a restore it is behind by
exactly the rows that were just recovered. The other direction closes that gap:

    python3 scripts/restore_lms_ratings.py export-lms \\
        --database /var/lms/lms.db --user user --out lms-ratings.json
    python3 scripts/restore_lms_ratings.py import-muma --json lms-ratings.json --apply
"""
import argparse
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Run as a file (`python3 scripts/restore_lms_ratings.py`), so the repository root is not on
# the path by itself. The path spellings come from the one shared copy: the rating webhook,
# the version sync and this script must agree on them (LMS_MUSIC_ROOT / MUMA_MUSIC_ROOT
# override the /music and /mnt/music defaults there, as they do in the running service).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.music_manager.library_paths import candidate_paths  # noqa: E402

# LMS stores the file's RATING tag verbatim as a cluster name. Anything outside this
# mapping (the library has two tracks tagged "Clean") is not a rating and is skipped.
TAG_TO_RATING = {"20": 1, "40": 2, "60": 3, "80": 4, "100": 5}

SOURCE_EXISTING = "existing"
SOURCE_MUMA = "muma"
SOURCE_TAG = "tag"


class SchemaError(RuntimeError):
    """The database does not look like an LMS database we can restore into."""


@dataclass
class Report:
    user: str = ""
    user_id: int = 0
    existing: int = 0
    from_muma: int = 0
    from_tags: int = 0
    muma_rows_read: int = 0
    muma_unmatched_paths: int = 0
    tag_rows_read: int = 0
    tag_values_skipped: Counter = field(default_factory=Counter)
    kept_existing: int = 0
    conflicts: list = field(default_factory=list)

    @property
    def inserted(self):
        return self.from_muma + self.from_tags

    def render(self):
        lines = [
            f"user                  {self.user} (id {self.user_id})",
            f"already rated         {self.existing} (left untouched)",
            f"music-management rows {self.muma_rows_read} read, {self.muma_unmatched_paths} without a matching track",
            f"RATING tag rows       {self.tag_rows_read} read",
        ]
        if self.tag_values_skipped:
            skipped = ", ".join(f"{v}x{k!r}" for k, v in sorted(self.tag_values_skipped.items()))
            lines.append(f"  tag values skipped  {skipped}")
        lines += [
            f"to insert from muma   {self.from_muma}",
            f"to insert from tags   {self.from_tags}",
            f"kept existing rating  {self.kept_existing} (source had one too)",
            f"TOTAL to insert       {self.inserted}",
        ]
        if self.conflicts:
            lines.append(f"disagreements         {len(self.conflicts)} (strongest source used)")
            for conflict in self.conflicts[:20]:
                lines.append(f"  {conflict}")
        return "\n".join(lines)


def check_schema(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    missing = {"rated_track", "track", "user", "cluster", "cluster_type", "track_cluster"} - tables
    if missing:
        raise SchemaError(f"missing tables: {', '.join(sorted(missing))}")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(rated_track)")}
    for required in ("version", "rating", "last_updated", "track_id", "user_id"):
        if required not in columns:
            raise SchemaError(f"rated_track has no {required} column")


def resolve_user(conn, login_name):
    row = conn.execute("SELECT id FROM user WHERE login_name = ?", (login_name,)).fetchone()
    if row is None:
        raise SchemaError(f"no LMS user named {login_name!r}")
    return row[0]


def track_ids_by_path(conn):
    return {path: track_id for track_id, path in conn.execute("SELECT id, absolute_file_path FROM track")}


def existing_ratings(conn, user_id):
    return {row[0] for row in conn.execute("SELECT track_id FROM rated_track WHERE user_id = ?", (user_id,))}


def tag_ratings(conn, report):
    """(track_id, rating) for every track whose RATING tag LMS imported as a cluster."""
    rows = conn.execute(
        "SELECT tc.track_id, c.name FROM track_cluster tc"
        " JOIN cluster c ON c.id = tc.cluster_id"
        " JOIN cluster_type ct ON ct.id = c.cluster_type_id"
        " WHERE ct.name = 'RATING'"
    ).fetchall()
    resolved = {}
    for track_id, name in rows:
        report.tag_rows_read += 1
        rating = TAG_TO_RATING.get(str(name))
        if rating is None:
            report.tag_values_skipped[str(name)] += 1
            continue
        resolved[track_id] = max(rating, resolved.get(track_id, 0))
    return resolved


def muma_ratings(entries, usernames, by_path, report):
    """(track_id, (rating, when)) for mirror rows we can still tie to a track.

    `usernames` is ordered: the first name that rated a track wins, so ratings made under
    an older login only fill in tracks the primary user never rated.
    """
    priority = {name: index for index, name in enumerate(usernames)}
    best = {}
    for entry in entries:
        report.muma_rows_read += 1
        if entry.get("username") not in priority:
            continue
        track_id = None
        for path in candidate_paths(entry["path"]):
            track_id = by_path.get(path)
            if track_id is not None:
                break
        if track_id is None:
            report.muma_unmatched_paths += 1
            continue
        rank = priority[entry["username"]]
        current = best.get(track_id)
        if current is None or rank < current[0]:
            best[track_id] = (rank, int(entry["rating"]), entry.get("updated_at"))
        elif rank == current[0] and int(entry["rating"]) != current[1]:
            report.conflicts.append(
                f"track {track_id}: {entry['username']} has both {current[1]} and {entry['rating']}, kept {current[1]}"
            )
    return {track_id: (rating, when) for track_id, (_, rating, when) in best.items()}


def build_plan(conn, entries, usernames, use_tags, report):
    by_path = track_ids_by_path(conn)
    already = existing_ratings(conn, report.user_id)
    report.existing = len(already)

    from_muma = muma_ratings(entries, usernames, by_path, report)
    from_tags = tag_ratings(conn, report) if use_tags else {}

    plan = []
    for track_id, (rating, when) in sorted(from_muma.items()):
        if track_id in already:
            report.kept_existing += 1
            continue
        if track_id in from_tags and from_tags[track_id] != rating:
            report.conflicts.append(
                f"track {track_id}: tag says {from_tags[track_id]}, music-management says {rating}, used {rating}"
            )
        plan.append((track_id, rating, when, SOURCE_MUMA))
        report.from_muma += 1
    for track_id, rating in sorted(from_tags.items()):
        if track_id in already:
            report.kept_existing += 1
            continue
        if track_id in from_muma:
            continue
        plan.append((track_id, rating, None, SOURCE_TAG))
        report.from_tags += 1
    return plan


def export_current(conn, path):
    rows = [
        dict(zip(("id", "version", "rating", "last_updated", "track_id", "user_id"), row, strict=True))
        for row in conn.execute("SELECT id, version, rating, last_updated, track_id, user_id FROM rated_track")
    ]
    Path(path).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return len(rows)


def apply_plan(conn, plan, user_id):
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000")
    conn.executemany(
        "INSERT INTO rated_track (version, rating, last_updated, track_id, user_id) VALUES (0, ?, ?, ?, ?)",
        [(rating, when or now, track_id, user_id) for track_id, rating, when, _ in plan],
    )
    conn.commit()


def command_export_lms(args):
    """The other direction: what LMS holds, ready to be pushed back into the mirror."""
    conn = sqlite3.connect(args.database)
    try:
        check_schema(conn)
        user_id = resolve_user(conn, args.user)
        rows = conn.execute(
            "SELECT t.absolute_file_path, r.rating, r.last_updated FROM rated_track r"
            " JOIN track t ON t.id = r.track_id WHERE r.user_id = ?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    entries = [
        {"username": args.user, "rating": rating, "path": path, "updated_at": last_updated}
        for path, rating, last_updated in rows
    ]
    Path(args.out).write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"wrote {len(entries)} ratings for {args.user} to {args.out}")
    return 0


def command_import_muma(args):
    """Upsert LMS's ratings into music-management's mirror, keyed on track_uid.

    The mirror is what the dynamic playlists read, so a rating that only exists in LMS is
    invisible to them. Rows are matched by path across both library roots; anything that
    does not resolve is reported and skipped rather than stored under a meaningless id.
    """
    from services.music_manager.database import get_db_connection

    entries = json.loads(Path(args.json).read_text(encoding="utf-8"))
    conn = get_db_connection()
    if conn is None:
        print("cannot reach the music-management database", file=sys.stderr)
        return 1
    resolved, unmatched = [], 0
    try:
        with conn.cursor() as cursor:
            for entry in entries:
                paths = candidate_paths(entry["path"])
                placeholders = ", ".join(["%s"] * len(paths))
                cursor.execute(
                    "SELECT t.track_uid FROM library_media_files f"
                    " JOIN library_tracks t ON f.track_id = t.id"
                    f" WHERE f.file_path IN ({placeholders})",
                    tuple(paths),
                )
                row = cursor.fetchone()
                if row is None:
                    unmatched += 1
                    continue
                resolved.append((row["track_uid"], entry["username"], int(entry["rating"])))
            print(f"{len(entries)} ratings read, {len(resolved)} resolved, {unmatched} without a matching track")
            if not args.apply:
                print("dry run, nothing written. re-run with --apply")
                return 0
            cursor.executemany(
                "INSERT INTO rating_tracks (entity_type, entity_id, username, rating)"
                " VALUES ('track', %s, %s, %s) ON DUPLICATE KEY UPDATE rating = VALUES(rating)",
                resolved,
            )
            conn.commit()
            cursor.execute("SELECT count(*) AS n FROM rating_tracks")
            print(f"upserted {len(resolved)} rows, rating_tracks now holds {cursor.fetchone()['n']}")
    finally:
        conn.close()
    return 0


def command_export_muma(args):
    from services.music_manager.database import get_db_connection

    conn = get_db_connection()
    if conn is None:
        print("cannot reach the music-management database", file=sys.stderr)
        return 1
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT r.username, r.rating, f.file_path AS path, r.updated_at"
                " FROM rating_tracks r"
                " JOIN library_tracks t ON r.entity_id = t.track_uid"
                " JOIN library_media_files f ON f.track_id = t.id"
                " WHERE r.entity_type = 'track'"
            )
            rows = cursor.fetchall()
    finally:
        conn.close()
    entries = [
        {
            "username": row["username"],
            "rating": int(row["rating"]),
            "path": row["path"],
            "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
        }
        for row in rows
    ]
    Path(args.out).write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"wrote {len(entries)} resolvable ratings to {args.out}")
    return 0


def command_restore(args):
    entries = json.loads(Path(args.muma_json).read_text(encoding="utf-8")) if args.muma_json else []
    conn = sqlite3.connect(args.database)
    try:
        check_schema(conn)
        report = Report(user=args.user, user_id=resolve_user(conn, args.user))
        plan = build_plan(conn, entries, [args.user, *args.also_user], not args.no_tags, report)
        print(report.render())
        if not args.apply:
            print("\ndry run, nothing written. re-run with --apply")
            return 0
        exported = export_current(conn, args.export)
        print(f"\nexported {exported} existing rated_track rows to {args.export}")
        apply_plan(conn, plan, report.user_id)
        total = conn.execute("SELECT count(*) FROM rated_track").fetchone()[0]
        print(f"inserted {len(plan)} rows, rated_track now holds {total}")
    finally:
        conn.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export-muma", help="dump music-management's mirror to JSON")
    export.add_argument("--out", required=True)
    export.set_defaults(func=command_export_muma)

    restore = sub.add_parser("restore", help="insert missing rated_track rows")
    restore.add_argument("--database", required=True, help="path to lms.db")
    restore.add_argument("--muma-json", help="output of export-muma; omit to restore from tags only")
    restore.add_argument("--user", required=True, help="LMS login name the ratings belong to")
    restore.add_argument(
        "--also-user",
        action="append",
        default=[],
        help="extra music-management username to fold into --user, for tracks --user did not rate",
    )
    restore.add_argument("--no-tags", action="store_true", help="ignore the RATING tags, use the mirror only")
    restore.add_argument("--export", default="rated-track-before.json", help="where to write the pre-change rows")
    restore.add_argument("--apply", action="store_true", help="write; without it the script only reports")
    restore.set_defaults(func=command_restore)

    export_lms = sub.add_parser("export-lms", help="dump LMS's ratings to JSON")
    export_lms.add_argument("--database", required=True, help="path to lms.db")
    export_lms.add_argument("--user", required=True, help="LMS login name")
    export_lms.add_argument("--out", required=True)
    export_lms.set_defaults(func=command_export_lms)

    import_muma = sub.add_parser("import-muma", help="upsert LMS's ratings into the mirror")
    import_muma.add_argument("--json", required=True, help="output of export-lms")
    import_muma.add_argument("--apply", action="store_true", help="write; without it the script only reports")
    import_muma.set_defaults(func=command_import_muma)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
