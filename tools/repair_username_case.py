"""Fold case-variant account names back into the one account they belong to.

The data half of docs/bug-reports/074-login-case-forks-user-identity.md. The code fix
stops new forks; this repairs the ones already made:

* MuMa: every table with a `username` column (discovered from information_schema, not
  listed by hand) gets the account's own spelling from `users.username` wherever a row
  carries a case variant of it. `UPDATE IGNORE`, then whatever a unique key refused is
  counted and reported, never deleted.
* LMS (`lms.db`, SQLite): users whose login names differ only in case are merged into
  one. Every table with a `user_id` column (discovered from the schema) is moved from the
  variant to the canonical user; for the per-entity tables where a user holds at most
  one row per entity (ratings, stars, bookmarks, play queue by name) the variant's row
  wins, because it is the newer one -- the variant only exists since the bad login. Then
  the variant user is deleted, in the same transaction, with foreign keys enforced.

Driven by scripts/prod/repair-username-case.sh, which runs it inside the music-manager
container (it has pymysql, the DB_* environment and lms.db mounted at /app/data/stable).
Every subcommand is safe to repeat: a second `apply` finds nothing to do. Never prints
a secret: the database password is read from the environment and not echoed.

Usage:
    python3 repair_username_case.py plan        --lms-db PATH
    python3 repair_username_case.py backup-lms  --lms-db PATH --to PATH
    python3 repair_username_case.py apply-muma
    python3 repair_username_case.py apply-lms   --lms-db PATH
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Any

#: LMS tables where one user holds at most one row per key. On a merge the variant's row
#: replaces the canonical user's row for the same key rather than sitting next to it.
LMS_ONE_ROW_PER_KEY: dict[str, tuple[str, ...]] = {
    'rated_track': ('track_id',),
    'rated_artist': ('artist_id',),
    'rated_release': ('release_id',),
    'starred_track': ('track_id', 'backend'),
    'starred_artist': ('artist_id', 'backend'),
    'starred_release': ('release_id', 'backend'),
    'track_bookmark': ('track_id',),
    'playqueue': ('name',),
}


# --- LMS ------------------------------------------------------------------------------------


@dataclass
class LmsMerge:
    """One variant LMS user to fold into the canonical one, and what moves with it."""

    canonical_id: int
    canonical_login: str
    variant_id: int
    variant_login: str
    #: The spelling the canonical user ends up with: MuMa's, when MuMa has the account.
    target_login: str
    #: table -> rows the variant owns.
    rows: dict[str, int] = field(default_factory=dict)
    #: table -> canonical rows the variant's rows replace (one-row-per-key tables only).
    replaced: dict[str, int] = field(default_factory=dict)


def lms_user_tables(conn: sqlite3.Connection) -> list[str]:
    """Every table in the LMS database with a `user_id` column, the `user` table aside."""
    tables = []
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
        if name == 'user' or name.startswith('sqlite_'):
            continue
        columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{name}")')}
        if 'user_id' in columns:
            tables.append(name)
    return tables


def _pick_canonical(group: list[dict], muma_names: dict[str, str]) -> dict:
    """The LMS user a case-variant group folds into.

    The one linked to a MuMa account first (that is what UserSynchronizer maintains), then
    the one spelled exactly as MuMa spells the account, then the oldest.
    """
    linked = [u for u in group if u['muma_id'] is not None]
    if linked:
        return min(linked, key=lambda u: u['id'])
    wanted = muma_names.get(group[0]['login_name'].casefold())
    exact = [u for u in group if u['login_name'] == wanted]
    if exact:
        return min(exact, key=lambda u: u['id'])
    return min(group, key=lambda u: u['id'])


def _key_columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    """The one-row-per-key columns for `table`, when the table really has all of them."""
    keys = LMS_ONE_ROW_PER_KEY.get(table, ())
    if not keys:
        return ()
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
    return keys if all(k in columns for k in keys) else ()


def _replaced_condition(keys: tuple[str, ...]) -> str:
    """SQL matching a canonical row (alias-free, table `t`) that a variant row replaces."""
    return ' AND '.join(f'v."{k}" IS t."{k}"' for k in keys)


def plan_lms(conn: sqlite3.Connection, muma_usernames: list[str]) -> list[LmsMerge]:
    """Every LMS user to merge, with per-table counts. Reads only."""
    muma_names = {name.casefold(): name for name in muma_usernames}
    users = [
        {'id': int(r[0]), 'login_name': r[1] or '', 'muma_id': r[2]}
        for r in conn.execute('SELECT id, login_name, muma_id FROM user ORDER BY id')
    ]
    groups: dict[str, list[dict]] = {}
    for user in users:
        if user['login_name']:
            groups.setdefault(user['login_name'].casefold(), []).append(user)

    tables = lms_user_tables(conn)
    merges = []
    for folded, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        canonical = _pick_canonical(group, muma_names)
        target = muma_names.get(folded, canonical['login_name'])
        for variant in sorted((u for u in group if u['id'] != canonical['id']), key=lambda u: u['id']):
            merge = LmsMerge(canonical['id'], canonical['login_name'], variant['id'], variant['login_name'], target)
            for table in tables:
                count = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE user_id = ?', (variant['id'],)).fetchone()[
                    0
                ]
                if not count:
                    continue
                merge.rows[table] = int(count)
                keys = _key_columns(conn, table)
                if keys:
                    replaced = conn.execute(
                        f'SELECT COUNT(*) FROM "{table}" t WHERE t.user_id = ? AND EXISTS '  # nosec B608 - schema names only
                        f'(SELECT 1 FROM "{table}" v WHERE v.user_id = ? AND {_replaced_condition(keys)})',
                        (canonical['id'], variant['id']),
                    ).fetchone()[0]
                    if replaced:
                        merge.replaced[table] = int(replaced)
            merges.append(merge)
    return merges


def apply_lms(conn: sqlite3.Connection, merges: list[LmsMerge]) -> None:
    """Carry out `merges` in one transaction; nothing is written unless all of it succeeds.

    Foreign keys are enforced, so a row still pointing at a variant user makes the final
    DELETE fail and the whole merge roll back, rather than leaving an orphan.
    """
    if not merges:
        return
    conn.isolation_level = None
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 30000')
    conn.execute('BEGIN IMMEDIATE')
    try:
        tables = lms_user_tables(conn)
        for merge in merges:
            for table in tables:
                keys = _key_columns(conn, table)
                if keys:
                    conn.execute(
                        f'DELETE FROM "{table}" WHERE rowid IN (SELECT t.rowid FROM "{table}" t '  # nosec B608 - schema names only
                        f'WHERE t.user_id = ? AND EXISTS '
                        f'(SELECT 1 FROM "{table}" v WHERE v.user_id = ? AND {_replaced_condition(keys)}))',
                        (merge.canonical_id, merge.variant_id),
                    )
                conn.execute(
                    f'UPDATE "{table}" SET user_id = ? WHERE user_id = ?',  # nosec B608 - schema names only
                    (merge.canonical_id, merge.variant_id),
                )
            conn.execute(
                'UPDATE user SET muma_id = (SELECT muma_id FROM user WHERE id = ?) WHERE id = ? AND muma_id IS NULL',
                (merge.variant_id, merge.canonical_id),
            )
            conn.execute('DELETE FROM user WHERE id = ?', (merge.variant_id,))
            conn.execute('UPDATE user SET login_name = ? WHERE id = ?', (merge.target_login, merge.canonical_id))
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise


def backup_lms(conn: sqlite3.Connection, destination: str) -> None:
    """A consistent copy through SQLite's backup API (WAL included, unlike a file copy)."""
    target = sqlite3.connect(destination)
    try:
        conn.backup(target)
    finally:
        target.close()


# --- MuMa -----------------------------------------------------------------------------------


@dataclass
class MumaRewrite:
    """Rows in one table carrying a case variant of one account's name."""

    table: str
    username: str
    variants: dict[str, int]

    @property
    def rows(self) -> int:
        return sum(self.variants.values())


def muma_username_tables(cursor: Any) -> list[str]:
    """Every base table with a `username` column except `users` itself."""
    cursor.execute(
        'SELECT c.table_name AS name FROM information_schema.columns c '
        'JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name '
        "WHERE c.table_schema = DATABASE() AND c.column_name = 'username' "
        "AND t.table_type = 'BASE TABLE' AND c.table_name <> 'users' ORDER BY c.table_name"
    )
    return [row['name'] if 'name' in row else row['NAME'] for row in cursor.fetchall()]


def _variant_condition() -> str:
    """Rows spelled like the account in any case, but not exactly like it."""
    return 'LOWER(username) = LOWER(%s) AND BINARY username <> BINARY %s'


def plan_muma(cursor: Any) -> list[MumaRewrite]:
    """Every (table, account) with rows under a case variant of the account's name. Reads only."""
    cursor.execute('SELECT username FROM users ORDER BY id')
    accounts = [row['username'] for row in cursor.fetchall() if row.get('username')]
    rewrites = []
    for table in muma_username_tables(cursor):
        for account in accounts:
            cursor.execute(
                f'SELECT username, COUNT(*) AS n FROM `{table}` WHERE {_variant_condition()} '  # nosec B608 - schema names only
                'GROUP BY BINARY username',
                (account, account),
            )
            variants = {row['username']: int(row['n']) for row in cursor.fetchall()}
            if variants:
                rewrites.append(MumaRewrite(table, account, variants))
    return rewrites


def apply_muma(conn: Any, rewrites: list[MumaRewrite]) -> dict[str, int]:
    """Rewrite every planned row to the account's spelling; returns leftovers per table.

    A leftover is a row a unique key refused because the account already has the same
    row under its own spelling. With a case-insensitive collation that cannot happen (the
    key would have refused the variant in the first place); on a binary one it can, and
    those rows are reported for a person to decide, not deleted here.
    """
    leftovers: dict[str, int] = {}
    with conn.cursor() as cursor:
        for rewrite in rewrites:
            cursor.execute(
                f'UPDATE IGNORE `{rewrite.table}` SET username = %s WHERE {_variant_condition()}',  # nosec B608
                (rewrite.username, rewrite.username, rewrite.username),
            )
            cursor.execute(
                f'SELECT COUNT(*) AS n FROM `{rewrite.table}` WHERE {_variant_condition()}',  # nosec B608
                (rewrite.username, rewrite.username),
            )
            left = int((cursor.fetchone() or {}).get('n') or 0)
            if left:
                leftovers[rewrite.table] = leftovers.get(rewrite.table, 0) + left
    conn.commit()
    return leftovers


# --- reporting and CLI ----------------------------------------------------------------------


def describe(rewrites: list[MumaRewrite], merges: list[LmsMerge]) -> str:
    """The plan as text: counts per table, names, never a secret."""
    lines = ['MuMa rows under a case variant of an account name:']
    if not rewrites:
        lines.append('    none')
    for rewrite in rewrites:
        spelled = ', '.join(f'{name!r}: {n}' for name, n in sorted(rewrite.variants.items()))
        lines.append(f'    {rewrite.table:<32} -> {rewrite.username!r}   {spelled}')
    lines.append('LMS users that differ only in case from another:')
    if not merges:
        lines.append('    none')
    for merge in merges:
        lines.append(
            f'    user {merge.variant_id} {merge.variant_login!r} -> user {merge.canonical_id} '
            f'{merge.canonical_login!r} (login becomes {merge.target_login!r})'
        )
        for table, count in sorted(merge.rows.items()):
            replaced = merge.replaced.get(table)
            note = f'  (replaces {replaced} of the canonical user)' if replaced else ''
            lines.append(f'        {table:<28} {count:>7}{note}')
        if not merge.rows:
            lines.append('        (owns no rows)')
    return '\n'.join(lines)


def _muma_connection():  # pragma: no cover - production only
    import pymysql  # pylint: disable=import-outside-toplevel

    return pymysql.connect(
        host=os.getenv('DB_HOST', 'db'),
        port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER', 'music-management'),
        password=os.getenv('DB_PASS', ''),
        database=os.getenv('DB_DB', 'music-management'),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI over tested functions
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n', 1)[0])
    parser.add_argument('command', choices=('plan', 'backup-lms', 'apply-muma', 'apply-lms'))
    parser.add_argument('--lms-db')
    parser.add_argument('--to')
    args = parser.parse_args(argv)

    muma = _muma_connection()
    try:
        with muma.cursor() as cursor:
            rewrites = plan_muma(cursor)
            cursor.execute('SELECT username FROM users')
            muma_names = [row['username'] for row in cursor.fetchall()]
        lms = sqlite3.connect(args.lms_db, timeout=30) if args.lms_db else None
        merges = plan_lms(lms, muma_names) if lms else []

        if args.command == 'plan':
            print(describe(rewrites, merges))
        elif args.command == 'backup-lms':
            if not lms or not args.to:
                parser.error('backup-lms needs --lms-db and --to')
            backup_lms(lms, args.to)
            print(f'LMS backup written to {args.to}')
        elif args.command == 'apply-muma':
            leftovers = apply_muma(muma, rewrites)
            print(f'MuMa: rewrote {sum(r.rows for r in rewrites)} rows in {len({r.table for r in rewrites})} tables')
            for table, count in sorted(leftovers.items()):
                print(f'    LEFTOVER {table}: {count} rows a unique key refused -- decide by hand')
        elif args.command == 'apply-lms':
            if not lms:
                parser.error('apply-lms needs --lms-db')
            apply_lms(lms, merges)
            print(f'LMS: merged {len(merges)} users')
        return 0
    finally:
        muma.close()


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
