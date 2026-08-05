#!/usr/bin/env python3
"""Turns LMS's starred_* rows into rated_* rows, because rating 5 is what favorite means.

There is no separate favorite flag any more. The server answers getStarred and the
`starred` response attribute from the rated_* tables, so every existing star has to
become a rating or it silently disappears from the interface.

The rule, the same one `scripts/migrate_lms_history.py` already uses: an explicit
rating always wins. A starred (object, user) pair that already has a row in the
matching rated_* table is left exactly as it is; only pairs with no rating at all
become rating 5. The star's own timestamp is carried over into `last_updated`, so
"favorites, most recent first" keeps the order it had.

Nothing is deleted. The starred_* rows stay where they are, and every row -- also the
ones that change nothing -- is written to a JSON export, so the old state survives in
two places.

Re-running is a no-op: the second pass finds the rating this pass wrote and leaves it
alone.

Scope: this writes to the LMS database only. It deliberately does not fire the
`rating_changed` webhook, so these ratings do not travel on to music-management and the
file tags. That is not a regression -- a star never reached the tags either -- but it
does mean a rebuilt LMS database loses them again. Ratings the user sets from here on
take the normal path and do end up in the tags.

Usage:
    python3 scripts/migrate_stars_to_ratings.py \\
        --database /var/lms/lms.db \\
        [--export docs/lms-stars-to-ratings-export.json] \\
        [--dry-run]
"""
import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

FAVORITE_RATING = 5

# (entity name, starred table, rated table, foreign key column)
ENTITIES = (
    ("track", "starred_track", "rated_track", "track_id"),
    ("release", "starred_release", "rated_release", "release_id"),
    ("artist", "starred_artist", "rated_artist", "artist_id"),
)


class SchemaError(RuntimeError):
    """The database does not look like an LMS database we can migrate."""


@dataclass
class EntityReport:
    entity: str
    total: int = 0
    rated: int = 0
    kept_explicit_rating: int = 0


@dataclass
class Report:
    entities: list = field(default_factory=list)

    def print_summary(self, dry_run):
        prefix = "Would rate" if dry_run else "Rated"
        print("\n=== Stars to ratings ===")
        for report in self.entities:
            print(
                f"{report.entity:<8} starred={report.total} "
                f"{prefix.lower()}={report.rated} kept_explicit_rating={report.kept_explicit_rating}"
            )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", required=True, help="Path to the LMS SQLite database")
    parser.add_argument(
        "--export",
        default="docs/lms-stars-to-ratings-export.json",
        help="Where to write the full starred-rows export (default: docs/lms-stars-to-ratings-export.json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing anything")
    return parser.parse_args(argv)


def columns_of(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def check_schema(conn):
    """Fails before touching anything if a table or column we rely on is missing."""
    for _, starred, rated, foreign_key in ENTITIES:
        starred_columns = columns_of(conn, starred)
        if not starred_columns:
            raise SchemaError(f"table '{starred}' not found -- is this an LMS database?")
        for required in (foreign_key, "user_id", "date_time"):
            if required not in starred_columns:
                raise SchemaError(f"table '{starred}' has no column '{required}'")

        rated_columns = columns_of(conn, rated)
        if not rated_columns:
            raise SchemaError(f"table '{rated}' not found -- is this an LMS database?")
        for required in (foreign_key, "user_id", "rating", "last_updated"):
            if required not in rated_columns:
                raise SchemaError(f"table '{rated}' has no column '{required}'")


def migrate_entity(conn, entity, starred, rated, foreign_key, dry_run, export):
    report = EntityReport(entity)

    already_rated = {
        (row[foreign_key], row["user_id"])
        for row in conn.execute(f"SELECT {foreign_key}, user_id FROM {rated}")
    }

    rows = conn.execute(
        f"SELECT {foreign_key} AS object_id, user_id, date_time FROM {starred}"
    ).fetchall()

    for row in rows:
        report.total += 1
        key = (row["object_id"], row["user_id"])
        has_explicit_rating = key in already_rated

        export.append(
            {
                "entity": entity,
                "object_id": row["object_id"],
                "user_id": row["user_id"],
                "starred_at": row["date_time"],
                "had_explicit_rating": has_explicit_rating,
                "imported_as_rating5": not has_explicit_rating,
            }
        )

        if has_explicit_rating:
            report.kept_explicit_rating += 1
            continue

        report.rated += 1
        if not dry_run:
            conn.execute(
                f"INSERT INTO {rated} ({foreign_key}, user_id, rating, last_updated) VALUES (?, ?, ?, ?)",
                (row["object_id"], row["user_id"], FAVORITE_RATING, row["date_time"]),
            )
            # A star that has just become a rating must not be imported twice if the
            # same pair is starred again further down the result set.
            already_rated.add(key)

    return report


def migrate(conn, dry_run):
    check_schema(conn)

    export = []
    report = Report()
    for entity, starred, rated, foreign_key in ENTITIES:
        report.entities.append(migrate_entity(conn, entity, starred, rated, foreign_key, dry_run, export))

    return report, export


def main(argv=None):
    args = parse_args(argv)

    conn = sqlite3.connect(args.database)
    conn.row_factory = sqlite3.Row
    try:
        report, export = migrate(conn, args.dry_run)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    except SchemaError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    export_path = Path(args.export)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {len(export)} starred rows to {export_path}")

    report.print_summary(args.dry_run)
    if args.dry_run:
        print("\nDry run: the database was not modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
