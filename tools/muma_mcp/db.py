#!/usr/bin/env python3
"""Read-only access to the production database.

Every statement runs inside ``START TRANSACTION READ ONLY`` with a server-side
``max_statement_time``. Neither is the security boundary -- the ``muma-readonly``
grant is -- but together they mean a runaway query is the database's problem for
ten seconds rather than production's problem for an hour.

The result is deliberately *not* rewritten to carry a ``LIMIT``. Editing someone's
SQL before running it is a good way to silently answer a different question than
the one asked; instead one row more than the limit is fetched and the caller is
told plainly that the result was cut off.

Usage:
    python -m tools.muma_mcp.db --check-read              # can it read?
    python -m tools.muma_mcp.db --check-write-is-refused  # is it really read-only?
"""

from __future__ import annotations

import argparse
import datetime
import decimal
import json
import sys
from typing import Any

import pymysql

from tools.muma_mcp.config import Config, ConfigError, load
from tools.muma_mcp.guard import QueryRejected, check

# Ten seconds is long for a question and short for an outage. MariaDB spells this
# max_statement_time (seconds, fractional); MySQL's max_execution_time is
# milliseconds and does not apply here -- production runs MariaDB 12.3.
STATEMENT_TIMEOUT_SECONDS = 10

# Enough for a real answer, small enough that one wide BLOB column cannot eat the
# agent's whole context window.
MAX_RESULT_BYTES = 100_000

CONNECT_TIMEOUT_SECONDS = 5


class WriteProbeSucceeded(RuntimeError):
    """The account could write. It must not be used until that is fixed."""


def connect(config: Config) -> pymysql.connections.Connection:
    """A connection with the read-only session settings already applied."""
    connection = pymysql.connect(
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        password=config.db_pass,
        database=config.db_name,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        read_timeout=STATEMENT_TIMEOUT_SECONDS + 5,
        charset='utf8mb4',
        autocommit=False,
    )
    with connection.cursor() as cursor:
        cursor.execute('SET SESSION max_statement_time=%s', (STATEMENT_TIMEOUT_SECONDS,))
    return connection


def _jsonable(value: Any) -> Any:
    """Row values the JSON encoder does not know about, in a readable form."""
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, bytes | bytearray):
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            return f'<{len(value)} bytes binair>'
    return value


def _fit(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Drop trailing rows until the serialized result fits ``MAX_RESULT_BYTES``."""
    kept = rows
    while kept and len(json.dumps(kept, ensure_ascii=False)) > MAX_RESULT_BYTES:
        kept = kept[: max(1, len(kept) // 2)]
        if len(kept) == 1:
            break
    return kept, len(kept) < len(rows)


def run_query(config: Config, sql: str, limit: int = 100) -> dict[str, Any]:
    """Run a validated read-only statement and return columns plus rows.

    Raises ``QueryRejected`` before touching the database when the statement is
    not one this server runs.
    """
    statement = check(sql)
    limit = max(1, min(int(limit), 1000))

    connection = connect(config)
    try:
        with connection.cursor() as cursor:
            cursor.execute('START TRANSACTION READ ONLY')
            cursor.execute(statement)
            columns = [column[0] for column in cursor.description or []]
            fetched = cursor.fetchmany(limit + 1)
        connection.rollback()
    finally:
        connection.close()

    truncated_by_limit = len(fetched) > limit
    rows = [{column: _jsonable(value) for column, value in zip(columns, row, strict=False)} for row in fetched[:limit]]
    rows, truncated_by_size = _fit(rows)

    return {
        'columns': columns,
        'rows': rows,
        'row_count': len(rows),
        'truncated': truncated_by_limit or truncated_by_size,
        'truncated_reason': (
            f'meer dan limit={limit} rijen beschikbaar'
            if truncated_by_limit
            else (f'resultaat groter dan {MAX_RESULT_BYTES} bytes' if truncated_by_size else None)
        ),
    }


def list_tables(config: Config) -> list[str]:
    """Every table the read-only account can see, which is the whole schema."""
    connection = connect(config)
    try:
        with connection.cursor() as cursor:
            cursor.execute('START TRANSACTION READ ONLY')
            cursor.execute('SHOW TABLES')
            names = [str(row[0]) for row in cursor.fetchall()]
        connection.rollback()
    finally:
        connection.close()
    return sorted(names)


def describe(config: Config, table: str) -> list[dict[str, Any]]:
    """Columns of one table.

    Asked of ``information_schema`` rather than with ``DESCRIBE``, because
    DESCRIBE takes no placeholder and would mean interpolating the table name
    into the statement. Here the name is a bound parameter -- data, never syntax
    -- so no validation of it is needed and none can be forgotten. An unknown
    name simply matches nothing.
    """
    connection = connect(config)
    try:
        with connection.cursor() as cursor:
            cursor.execute('START TRANSACTION READ ONLY')
            cursor.execute(
                'SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT, EXTRA '
                'FROM information_schema.COLUMNS '
                'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s '
                'ORDER BY ORDINAL_POSITION',
                (config.db_name, table),
            )
            columns = [column[0] for column in cursor.description or []]
            rows = [{c: _jsonable(v) for c, v in zip(columns, row, strict=False)} for row in cursor.fetchall()]
        connection.rollback()
    finally:
        connection.close()

    if not rows:
        raise QueryRejected(f'tabel {table!r} bestaat niet; gebruik prod_tables voor de lijst')
    return rows


def check_read(config: Config) -> int:
    """Prove the account can read. Returns a process exit code."""
    try:
        tables = list_tables(config)
    except Exception as exc:  # noqa: BLE001 -- this is a CLI check; the message is the product
        print(f'lezen mislukt: {exc}', file=sys.stderr)
        return 1
    print(f'gelezen: {len(tables)} tabellen zichtbaar in {config.db_name}')
    return 0


def check_write_is_refused(config: Config) -> int:
    """Prove the account cannot write. Returns a process exit code.

    The probe runs *outside* the read-only transaction on purpose. Inside one,
    every write fails regardless of privilege -- which would prove the transaction
    works and say nothing at all about the grant this check exists to verify.
    """
    connection = connect(config)
    try:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS muma_mcp_write_probe (id INT)')
    except pymysql.MySQLError as exc:
        print(f'schrijfpoging geweigerd door de database: {exc}')
        return 0
    finally:
        connection.close()

    raise WriteProbeSucceeded(
        'Het account kon een tabel aanmaken. Het is niet read-only. '
        'Verwijder muma_mcp_write_probe en trek de rechten in voordat je verdergaat.'
    )


def main(argv: list[str] | None = None) -> int:
    """Command line: check that the configured account can read, or that it cannot write."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check-read', action='store_true', help='verify the account can read')
    group.add_argument('--check-write-is-refused', action='store_true', help='verify the account cannot write')
    args = parser.parse_args(argv)

    try:
        config = load()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.check_read:
        return check_read(config)

    try:
        return check_write_is_refused(config)
    except WriteProbeSucceeded as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
