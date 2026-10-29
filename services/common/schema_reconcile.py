"""Bring a live database up to the declared schema, by adding only.

`services/common/schema_tables.py` declares every table. This module builds that declaration in
a scratch database (the probe), reads both databases from information_schema and compares them.
What the live database lacks -- a table, a column, an index, a view -- it adds. Every other
difference (a type, a primary key, a foreign key, something live has that the code does not
declare) it reports and leaves alone: dropping or changing data is a script with a backup, never
a deploy step. See docs/designs/declarative-schema/technical.md.

Run before the new containers start (scripts/deploy.sh):

    python -m services.common.schema_reconcile [--dry-run]

`--snapshot` prints the live schema in the format of tests/integration/schema/production.tsv
and changes nothing.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass, field

from services.common import schema_tables

DEFAULT_LOCK_WAIT_SECONDS = 30

_COLUMNS_SQL = (
    'SELECT c.table_name, c.column_name, c.column_type, c.is_nullable, c.column_default, c.extra, '
    'c.collation_name FROM information_schema.columns c JOIN information_schema.tables t '
    'ON t.table_schema = c.table_schema AND t.table_name = c.table_name '
    "WHERE c.table_schema = %s AND t.table_type = 'BASE TABLE' ORDER BY c.table_name, c.ordinal_position"
)
_TABLES_SQL = (
    'SELECT table_name, table_type, engine, table_collation FROM information_schema.tables WHERE table_schema = %s'
)
_INDEXES_SQL = (
    'SELECT table_name, index_name, non_unique, column_name, sub_part, index_type '
    'FROM information_schema.statistics WHERE table_schema = %s ORDER BY table_name, index_name, seq_in_index'
)
_FOREIGN_KEYS_SQL = (
    'SELECT k.table_name, k.constraint_name, k.column_name, k.referenced_table_name, k.referenced_column_name, '
    'r.delete_rule, r.update_rule FROM information_schema.key_column_usage k '
    'JOIN information_schema.referential_constraints r ON r.constraint_schema = k.constraint_schema '
    'AND r.constraint_name = k.constraint_name AND r.table_name = k.table_name '
    'WHERE k.table_schema = %s ORDER BY k.table_name, k.constraint_name, k.ordinal_position'
)
_CHECKS_SQL = (
    'SELECT table_name, constraint_name, check_clause FROM information_schema.check_constraints '
    'WHERE constraint_schema = %s'
)


@dataclass(frozen=True)
class Column:
    """One column as information_schema describes it."""

    type: str
    nullable: str
    default: str
    extra: str
    collation: str


@dataclass(frozen=True)
class Index:
    """One index: whether it is unique, its columns in order (with prefix lengths), its kind."""

    unique: bool
    columns: tuple[str, ...]
    kind: str


@dataclass(frozen=True)
class ForeignKey:
    """One foreign key by what it does; its name is not compared."""

    columns: tuple[str, ...]
    table: str
    referenced: tuple[str, ...]
    on_delete: str
    on_update: str


@dataclass
class Table:
    """Everything the comparison looks at for one base table."""

    engine: str = ''
    collation: str = ''
    columns: dict[str, Column] = field(default_factory=dict)
    indexes: dict[str, Index] = field(default_factory=dict)
    foreign_keys: set[ForeignKey] = field(default_factory=set)
    checks: dict[str, str] = field(default_factory=dict)


@dataclass
class Schema:
    """The base tables and the view names of one database."""

    tables: dict[str, Table] = field(default_factory=dict)
    views: set[str] = field(default_factory=set)


@dataclass
class Plan:
    """What reconcile() will run, and what it only reports."""

    statements: list[str] = field(default_factory=list)
    reports: list[str] = field(default_factory=list)


def _values(row) -> tuple:
    """A row as a tuple, whether the cursor returns tuples or dicts."""
    return tuple(row.values()) if isinstance(row, dict) else tuple(row)


def _text(value) -> str:
    """information_schema text, with SQL NULL kept apart from the string 'NULL'."""
    return '<none>' if value is None else str(value)


def read_schema(cursor, database: str) -> Schema:
    """Read the tables, columns, indexes, foreign keys, checks and views of `database`."""
    schema = Schema()
    cursor.execute(_TABLES_SQL, (database,))
    for name, kind, engine, collation in map(_values, cursor.fetchall()):
        if kind == 'BASE TABLE':
            schema.tables[name] = Table(engine=_text(engine), collation=_text(collation))
        else:
            schema.views.add(name)
    cursor.execute(_COLUMNS_SQL, (database,))
    for table, column, type_, nullable, default, extra, collation in map(_values, cursor.fetchall()):
        schema.tables[table].columns[column] = Column(
            type_, nullable, _text(default), (extra or '').lower(), _text(collation)
        )
    cursor.execute(_INDEXES_SQL, (database,))
    parts: dict[tuple[str, str], list] = {}
    for table, index, non_unique, column, sub_part, kind in map(_values, cursor.fetchall()):
        entry = parts.setdefault((table, index), [not int(non_unique), [], kind])
        entry[1].append(f'{column}({sub_part})' if sub_part else column)
    for (table, index), (unique, columns, kind) in parts.items():
        if table in schema.tables:
            schema.tables[table].indexes[index] = Index(unique, tuple(columns), kind)
    cursor.execute(_FOREIGN_KEYS_SQL, (database,))
    keys: dict[tuple[str, str], list] = {}
    for table, name, column, ref_table, ref_column, on_delete, on_update in map(_values, cursor.fetchall()):
        entry = keys.setdefault((table, name), [[], ref_table, [], on_delete, on_update])
        entry[0].append(column)
        entry[2].append(ref_column)
    for (table, _), (columns, ref_table, ref_columns, on_delete, on_update) in keys.items():
        schema.tables[table].foreign_keys.add(
            ForeignKey(tuple(columns), ref_table, tuple(ref_columns), on_delete, on_update)
        )
    cursor.execute(_CHECKS_SQL, (database,))
    for table, name, clause in map(_values, cursor.fetchall()):
        if table in schema.tables:
            schema.tables[table].checks[name] = clause
    return schema


def snapshot_lines(schema: Schema) -> list[str]:
    """The schema as sorted tab-separated lines, one object per line.

    T table engine collation / C table column type nullable default extra collation /
    I table index unique columns kind / F table columns referenced-table referenced-columns
    on-delete on-update / K table check clause / V view. Foreign keys go without their name:
    MariaDB names an unnamed one differently per version.
    """
    lines = [f'V\t{view}' for view in schema.views]
    for name, table in schema.tables.items():
        lines.append(f'T\t{name}\t{table.engine}\t{table.collation}')
        for column, c in table.columns.items():
            lines.append(f'C\t{name}\t{column}\t{c.type}\t{c.nullable}\t{c.default}\t{c.extra}\t{c.collation}')
        for index, i in table.indexes.items():
            lines.append(f'I\t{name}\t{index}\t{int(i.unique)}\t{",".join(i.columns)}\t{i.kind}')
        for fk in table.foreign_keys:
            lines.append(
                f'F\t{name}\t{",".join(fk.columns)}\t{fk.table}\t{",".join(fk.referenced)}\t{fk.on_delete}\t{fk.on_update}'
            )
        for check, clause in table.checks.items():
            lines.append(f'K\t{name}\t{check}\t{clause}')
    return sorted(lines)


def _definitions(create_statement: str) -> tuple[dict[str, str], dict[str, str]]:
    """Column and index definitions, by name, from a `SHOW CREATE TABLE` text."""
    columns: dict[str, str] = {}
    indexes: dict[str, str] = {}
    for line in create_statement.splitlines()[1:]:
        line = line.strip().rstrip(',')
        column = re.match(r'`(\w+)` ', line)
        index = re.match(r'(?:UNIQUE |FULLTEXT |SPATIAL )?KEY `(\w+)` ', line)
        if column:
            columns[column.group(1)] = line
        elif index:
            indexes[index.group(1)] = line
    return columns, indexes


def _table_statement(create_statement: str) -> str:
    """A probe table's `SHOW CREATE TABLE`, as a statement to run on the live database."""
    return re.sub(r' AUTO_INCREMENT=\d+', '', create_statement)


def plan(declared: Schema, live: Schema, create_statements: dict[str, str]) -> Plan:
    """Compare the declared schema with the live one.

    `create_statements` is the probe's `SHOW CREATE TABLE` per declared table: the column and
    index definitions to add come from there, so they are exactly what MariaDB built.
    """
    result = Plan()
    for name, _ in schema_tables.TABLES:
        want = declared.tables[name]
        have = live.tables.get(name)
        if have is None:
            result.statements.append(_table_statement(create_statements[name]))
            continue
        _plan_table(name, want, have, create_statements[name], result)
    for name in sorted(set(live.tables) - set(declared.tables)):
        result.reports.append(f'extra table: {name}')
    for view, statement in schema_tables.VIEWS:
        if view not in live.views:
            result.statements.append(statement)
    for view in sorted(live.views - declared.views):
        result.reports.append(f'extra view: {view}')
    return result


def _plan_table(name: str, want: Table, have: Table, create_statement: str, result: Plan) -> None:
    """Add what `have` lacks of `want` to `result`; report the rest."""
    column_sql, index_sql = _definitions(create_statement)
    if (want.engine, want.collation) != (have.engine, have.collation):
        result.reports.append(
            f'changed table: {name} is {have.engine}/{have.collation}, declared {want.engine}/{want.collation}'
        )
    previous = None
    for column, definition in want.columns.items():
        if column not in have.columns:
            position = f'AFTER `{previous}`' if previous else 'FIRST'
            result.statements.append(f'ALTER TABLE `{name}` ADD COLUMN {column_sql[column]} {position}')
        elif have.columns[column] != definition:
            result.reports.append(f'changed column: {name}.{column} is {have.columns[column]}, declared {definition}')
        previous = column
    for column in have.columns.keys() - want.columns.keys():
        result.reports.append(f'extra column: {name}.{column}')
    if want.indexes.get('PRIMARY') != have.indexes.get('PRIMARY'):
        result.reports.append(
            f'changed primary key: {name} is {have.indexes.get("PRIMARY")}, declared {want.indexes.get("PRIMARY")}'
        )
    # Secondary indexes match by what they cover, not by name.
    existing = {definition for index, definition in have.indexes.items() if index != 'PRIMARY'}
    wanted = {definition for index, definition in want.indexes.items() if index != 'PRIMARY'}
    for index, covers in want.indexes.items():
        if index != 'PRIMARY' and covers not in existing:
            result.statements.append(f'ALTER TABLE `{name}` ADD {index_sql[index]}')
    for index, covers in have.indexes.items():
        if index != 'PRIMARY' and covers not in wanted:
            result.reports.append(f'extra index: {name}.{index} {covers}')
    for fk in sorted(want.foreign_keys - have.foreign_keys, key=str):
        result.reports.append(f'missing foreign key: {name} {fk}')
    for fk in sorted(have.foreign_keys - want.foreign_keys, key=str):
        result.reports.append(f'extra foreign key: {name} {fk}')
    if want.checks != have.checks:
        result.reports.append(f'changed checks: {name} is {have.checks}, declared {want.checks}')


def build_probe(connection, probe: str) -> dict[str, str]:
    """Create `probe` from nothing with every declared table and view.

    Returns each table's `SHOW CREATE TABLE`, read before the probe is dropped again.
    """
    with connection.cursor() as cursor:
        cursor.execute(f'DROP DATABASE IF EXISTS `{probe}`')
        cursor.execute(f'CREATE DATABASE `{probe}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
        cursor.execute(f'USE `{probe}`')
        for _, statement in schema_tables.TABLES:
            cursor.execute(statement)
        for _, statement in schema_tables.VIEWS:
            cursor.execute(statement)
        statements = {}
        for name, _ in schema_tables.TABLES:
            cursor.execute(f'SHOW CREATE TABLE `{name}`')
            statements[name] = _values(cursor.fetchone())[1]
    return statements


def reconcile(connection, database: str, probe: str, *, dry_run: bool, lock_wait_seconds: int) -> Plan:
    """Build the probe, compare it with `database`, run the additions unless `dry_run`.

    The probe is always dropped again. A statement that fails raises: the deploy stops before
    the new containers start.
    """
    try:
        create_statements = build_probe(connection, probe)
        with connection.cursor() as cursor:
            declared = read_schema(cursor, probe)
            live = read_schema(cursor, database)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS `{probe}`')
    result = plan(declared, live, create_statements)
    if dry_run:
        return result
    with connection.cursor() as cursor:
        cursor.execute(f'USE `{database}`')
        cursor.execute(f'SET SESSION lock_wait_timeout = {int(lock_wait_seconds)}')
        cursor.execute(f'SET SESSION innodb_lock_wait_timeout = {int(lock_wait_seconds)}')
        for statement in result.statements:
            logging.info('schema: %s', statement)
            cursor.execute(statement)
    return result


def _connect():
    """A connection from the same DB_* variables every service reads."""
    import pymysql

    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT') or 3306),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS'),
        autocommit=True,
        connect_timeout=10,
    )


def main(argv: list[str] | None = None) -> int:
    """Command line: reconcile the database DB_DB names, or print its snapshot."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dry-run', action='store_true', help='print the statements, run none')
    parser.add_argument('--snapshot', action='store_true', help='print the live schema and stop')
    parser.add_argument('--probe-database', help='scratch database name (default: <DB_DB>_schema_probe)')
    parser.add_argument('--lock-wait-timeout', type=int, default=DEFAULT_LOCK_WAIT_SECONDS)
    args = parser.parse_args(argv)
    database = os.getenv('DB_DB')
    if not database:
        print('DB_DB is not set', file=sys.stderr)
        return 2
    connection = _connect()
    try:
        if args.snapshot:
            with connection.cursor() as cursor:
                print('\n'.join(snapshot_lines(read_schema(cursor, database))))
            return 0
        probe = args.probe_database or f'{database}_schema_probe'
        result = reconcile(connection, database, probe, dry_run=args.dry_run, lock_wait_seconds=args.lock_wait_timeout)
    finally:
        connection.close()
    verb = 'would run' if args.dry_run else 'ran'
    for statement in result.statements:
        print(f'{verb}: {" ".join(statement.split())}')
    for report in result.reports:
        print(f'report: {report}')
    if not result.statements:
        print(f'schema in sync, {len(result.reports)} reported')
    else:
        print(f'schema reconciled: {len(result.statements)} changes, {len(result.reports)} reported')
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
