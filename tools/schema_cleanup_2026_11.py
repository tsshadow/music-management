#!/usr/bin/env python3
"""One-off: remove from production what the code no longer declares (issue #43).

services/common/schema_tables.py declares production's shape, less the items below. The
deploy's reconcile only adds, so it reports these as differences and leaves them. This
script settles them once, after the release that brought the declarative schema:

- drops 6 tables and 6 columns that nothing reads;
- replaces the `scrobble_listens.track_id` foreign key: ON DELETE CASCADE took a track's
  listens with it, SET NULL keeps them;
- adds the `rules_genres.canonical_id` foreign key, after it clears ids that point nowhere.

Without --apply it prints what it would do and changes nothing. With --apply it first
dumps the whole database through tools/db_backup.py into --backup-dir and checks the dump,
then runs the statements. Every step looks at the live schema first, so a second run
finds nothing to do.

The account needs ALTER and DROP on the database: set CLEANUP_DB_USER and CLEANUP_DB_PASS,
else DB_USER and DB_PASS are used. The dump uses the same account.

Usage, in the tools image (it has mariadb-dump):
    python tools/schema_cleanup_2026_11.py                          # dry run
    python tools/schema_cleanup_2026_11.py --apply --backup-dir /backups
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from tools import db_backup  # noqa: E402

DROPPED_TABLES = (
    'downloads_soundcloud_queue',
    'downloads_youtube_queue',
    'rules_genres_new',
    'rules_genres_old',
    'library_broken_songs',
    'library_broken_song_artist_lookup',
)

DROPPED_COLUMNS = (
    ('artist_external_ids', 'confidence'),
    ('downloads_soundcloud_accounts', 'account_type'),
    ('downloads_soundcloud_accounts', 'image_enrichment_hint'),
    ('downloads_soundcloud_accounts', 'linked_artist_id'),
    ('library_artist_images', 'status'),
    ('library_artist_images', 'error_message'),
)

# The constraint names schema_tables.py declares.
SCROBBLE_FK = 'scrobble_listens_ibfk_1'
GENRE_FK = 'fk_rules_genres_canonical'

DEFAULT_LOCK_WAIT_SECONDS = 120


def _rows(cursor, query: str, args: tuple) -> list[tuple]:
    """Rows as tuples, whatever cursor class the connection uses."""
    cursor.execute(query, args)
    return [tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in cursor.fetchall()]


def plan(cursor, database: str) -> list[str]:
    """The statements that bring DATABASE to the declared shape, in the order to run them."""
    tables = {
        name
        for (name,) in _rows(
            cursor, 'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s', (database,)
        )
    }
    columns = set(
        _rows(
            cursor,
            'SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s',
            (database,),
        )
    )
    foreign_keys = _rows(
        cursor,
        'SELECT CONSTRAINT_NAME, TABLE_NAME, REFERENCED_TABLE_NAME, DELETE_RULE'
        ' FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = %s',
        (database,),
    )
    genre_index = _rows(
        cursor,
        'SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = %s'
        " AND TABLE_NAME = 'rules_genres' AND COLUMN_NAME = 'canonical_id' AND SEQ_IN_INDEX = 1",
        (database,),
    )

    statements = [f'DROP TABLE `{table}`' for table in DROPPED_TABLES if table in tables]

    by_table: dict[str, list[str]] = {}
    for table, column in DROPPED_COLUMNS:
        if (table, column) in columns:
            by_table.setdefault(table, []).append(f'DROP COLUMN `{column}`')
    statements += [f'ALTER TABLE `{table}` {", ".join(drops)}' for table, drops in by_table.items()]

    scrobble = [
        (name, rule)
        for name, table, ref, rule in foreign_keys
        if (table, ref) == ('scrobble_listens', 'library_tracks')
    ]
    if not any(rule == 'SET NULL' for _, rule in scrobble):
        statements += [f'ALTER TABLE `scrobble_listens` DROP FOREIGN KEY `{name}`' for name, _ in scrobble]
        statements.append(
            f'ALTER TABLE `scrobble_listens` ADD CONSTRAINT `{SCROBBLE_FK}` FOREIGN KEY (`track_id`)'
            ' REFERENCES `library_tracks` (`id`) ON DELETE SET NULL'
        )

    if not any((table, ref) == ('rules_genres', 'rules_genres') for _, table, ref, _ in foreign_keys):
        if not genre_index:
            # Without it ADD CONSTRAINT would create an index named after the constraint.
            statements.append('ALTER TABLE `rules_genres` ADD KEY `canonical_id` (`canonical_id`)')
        statements.append(
            'UPDATE `rules_genres` g LEFT JOIN `rules_genres` c ON c.`id` = g.`canonical_id`'
            ' SET g.`canonical_id` = NULL WHERE g.`canonical_id` IS NOT NULL AND c.`id` IS NULL'
        )
        statements.append(
            f'ALTER TABLE `rules_genres` ADD CONSTRAINT `{GENRE_FK}` FOREIGN KEY (`canonical_id`)'
            ' REFERENCES `rules_genres` (`id`) ON DELETE SET NULL'
        )
    return statements


def apply(connection, statements: list[str], lock_wait_seconds: int) -> None:
    """Run STATEMENTS one by one; each waits at most LOCK_WAIT_SECONDS for a lock."""
    with connection.cursor() as cursor:
        cursor.execute(f'SET SESSION lock_wait_timeout = {int(lock_wait_seconds)}')
        cursor.execute(f'SET SESSION innodb_lock_wait_timeout = {int(lock_wait_seconds)}')
        for statement in statements:
            print(f'run: {statement}', flush=True)
            cursor.execute(statement)
    connection.commit()


def credentials() -> dict[str, str]:
    """db_backup's credentials, with CLEANUP_DB_USER and CLEANUP_DB_PASS first."""
    creds = db_backup._credentials()
    creds['user'] = os.getenv('CLEANUP_DB_USER') or creds['user']
    creds['password'] = os.getenv('CLEANUP_DB_PASS') or creds['password']
    return creds


def backup(destination: Path, creds: dict[str, str], now: datetime) -> Path:
    """Dump the whole database into DESTINATION and check the dump; returns its path."""
    if not destination.is_dir():
        raise db_backup.BackupError(f'{destination} is not a directory')
    target = destination / f'muma_db_schema-cleanup_{now:%Y%m%d_%H%M%S}.sql.gz'
    db_backup.dump(target, creds)
    db_backup.verify(target)
    return target


def _connect(creds: dict[str, str]):
    """A pymysql connection on the database CREDS name."""
    import pymysql

    return pymysql.connect(
        host=creds['host'],
        port=int(creds['port']),
        user=creds['user'],
        password=creds['password'],
        database=creds['database'],
        connect_timeout=10,
    )


def main(argv: list[str] | None = None) -> int:
    """Command line: print the plan, or back up and apply it with --apply."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--apply', action='store_true', help='back up, then run the statements')
    parser.add_argument('--backup-dir', type=Path, help='where the dump goes; required with --apply')
    parser.add_argument('--lock-wait-timeout', type=int, default=DEFAULT_LOCK_WAIT_SECONDS)
    args = parser.parse_args(argv)
    if args.apply and not args.backup_dir:
        parser.error('--apply needs --backup-dir: nothing changes without a backup')
    creds = credentials()
    if not creds['database']:
        print('DB_DB is not set', file=sys.stderr)
        return 2

    connection = _connect(creds)
    try:
        with connection.cursor() as cursor:
            statements = plan(cursor, creds['database'])
        if not statements:
            print('nothing to do: the schema is already clean')
            return 0
        if not args.apply:
            for statement in statements:
                print(f'would run: {statement}')
            print('dry run, nothing changed; run again with --apply --backup-dir DIR')
            return 0
        path = backup(args.backup_dir, creds, datetime.now(UTC))
        print(f'backup: {path}', flush=True)
        apply(connection, statements, args.lock_wait_timeout)
        print(f'done: {len(statements)} statements')
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    sys.exit(main())
