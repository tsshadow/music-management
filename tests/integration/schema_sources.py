"""Where this project's schema is declared, read from the source instead of listed by hand.

tests/integration/test_schema.py used to carry a hand-kept set of table names. It
drifted the way such lists do: some twenty tables the code creates and reads --
channels, the feed snapshot, radio, news, the festival and podcast rules, the
downloader's own tables -- were never on it, so nothing noticed if a fresh stack
stopped creating one of them. The set is now whatever the code and the migrations
say in their CREATE TABLE statements, so it cannot fall behind them.

This module also knows the two ways a schema comes into being, which
test_schema_drift.py builds side by side and compares:

* **code** -- what a fresh stack runs: ``db_init.ensure_tables_exist()``, then every
  ``init_db`` main.py's startup calls, then the one table the tagger loop creates for
  itself (tagger_processed_files);
* **migrations** -- what production runs on every deploy: ``db_init`` and then every
  ``migrate_*.sql``, twice.

Not collected by pytest (no test_ prefix); imported by the tests that need it.
"""

from __future__ import annotations

import contextlib
import inspect
import os
import re
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Everything under services/ that can declare a table in the shared MariaDB. The
# ml-analyzer keeps its own database (services/ml-analyzer/db_init.sql); the rest are
# not Python services.
_EXCLUDED_DIRS = {
    'ml-analyzer',
    'music-management-server',
    'muma-mobile',
    'frontend',
    'node_modules',
    'tests',
    '__pycache__',
}

# `CREATE TABLE [IF NOT EXISTS] name (` -- the opening parenthesis is required, so a
# comment or docstring that merely mentions "CREATE TABLE IF NOT EXISTS that ..." is
# not mistaken for a declaration.
_CREATE_RE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z0-9_{}.]+)`?\s*\(',
    re.IGNORECASE,
)

# A table whose name is only known at runtime. Each one has to be resolved here by
# hand; test_schema.py fails on any template it does not find in this map, so a new
# one cannot slip past unlisted.
TEMPLATED_TABLES = {
    # ProcessedFilesHelper(table_name='tagger_processed_files'); no other name is used.
    ('services/common/Helpers/ProcessedFilesHelper.py', '{self.table_name}'): 'tagger_processed_files',
}


def _is_test_file(path: Path) -> bool:
    """True for the files the unit suite collects or supports, which declare no schema."""
    name = path.name
    return name.endswith('Test.py') or name.startswith('test_') or name == 'conftest.py' or name == 'mock_base.py'


def python_schema_files() -> list[Path]:
    """Every non-test Python file under services/ that can create a shared table."""
    files = []
    for path in sorted((ROOT / 'services').rglob('*.py')):
        relative = path.relative_to(ROOT / 'services')
        if set(relative.parts[:-1]) & _EXCLUDED_DIRS or _is_test_file(path):
            continue
        files.append(path)
    return files


def migration_files() -> list[Path]:
    """The migrate_*.sql files, in the order scripts/deploy.sh applies them."""
    return sorted(ROOT.glob('migrate_*.sql'))


def _strip_sql_comments(text: str) -> str:
    """Drop `--` comment lines, which often quote the DDL they explain."""
    return '\n'.join(line for line in text.splitlines() if not line.strip().startswith('--'))


def _strip_python_comments(text: str) -> str:
    """Drop `#` comment lines, for the same reason as the SQL variant."""
    return '\n'.join(line for line in text.splitlines() if not line.strip().startswith('#'))


def unresolved_templates() -> list[tuple[str, str]]:
    """Templated CREATE TABLE names found in code that TEMPLATED_TABLES does not resolve."""
    found = []
    for path in python_schema_files():
        relative = str(path.relative_to(ROOT))
        for name in _CREATE_RE.findall(_strip_python_comments(path.read_text(encoding='utf-8'))):
            if '{' in name and (relative, name) not in TEMPLATED_TABLES:
                found.append((relative, name))
    return found


def code_declared_tables() -> dict[str, set[str]]:
    """Table name -> the Python files that declare it."""
    declared: dict[str, set[str]] = {}
    for path in python_schema_files():
        relative = str(path.relative_to(ROOT))
        for name in _CREATE_RE.findall(_strip_python_comments(path.read_text(encoding='utf-8'))):
            name = TEMPLATED_TABLES.get((relative, name), name)
            if '{' in name:
                continue  # reported by unresolved_templates()
            declared.setdefault(name, set()).add(relative)
    return declared


def migration_declared_tables() -> dict[str, set[str]]:
    """Table name -> the migrations that declare it.

    Names starting with an underscore are scratch tables a migration builds and
    drops within the same file (the festival seed lists); they are not schema.
    """
    declared: dict[str, set[str]] = {}
    for path in migration_files():
        for name in _CREATE_RE.findall(_strip_sql_comments(path.read_text(encoding='utf-8'))):
            if name.startswith('_'):
                continue
            declared.setdefault(name, set()).add(path.name)
    return declared


def declared_tables() -> set[str]:
    """Every table the code or a migration declares: what a deployed stack must have."""
    return set(code_declared_tables()) | set(migration_declared_tables())


def startup_init_dbs() -> list:
    """The init_db functions main.py's startup runs, in its order.

    Read from the startup function itself, so a router wired in there is built here
    without anyone remembering to add it.
    """
    from services.music_manager import main

    source = inspect.getsource(main.startup_event)
    names = re.findall(r'^\s*(\w+)\.init_db\(cursor\)', source, re.MULTILINE)
    assert names, 'no init_db calls found in main.startup_event; the extraction broke'
    return [getattr(main, name).init_db for name in names]


def startup_init_db_modules() -> set[str]:
    """Module names of the init_db functions main.py calls directly."""
    return {function.__module__ for function in startup_init_dbs()}


def modules_defining_init_db() -> set[str]:
    """Every services/ module that defines a top-level init_db."""
    modules = set()
    for path in python_schema_files():
        if re.search(r'^def init_db\(', path.read_text(encoding='utf-8'), re.MULTILINE):
            relative = path.relative_to(ROOT).with_suffix('')
            modules.add('.'.join(relative.parts))
    return modules


@contextlib.contextmanager
def database_env(name: str) -> Iterator[None]:
    """Point DB_DB at `name` for code that opens its own connection from the environment.

    db_init.ensure_tables_exist() and ProcessedFilesHelper do; both read the variable
    when they connect, so setting it around the call is enough.
    """
    previous = os.environ.get('DB_DB')
    os.environ['DB_DB'] = name
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('DB_DB', None)
        else:
            os.environ['DB_DB'] = previous


def build_from_code(connection, name: str) -> None:
    """Create the schema the way a fresh stack does, in database `name`."""
    from services.common import db_init
    from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper

    with database_env(name):
        db_init.ensure_tables_exist()
        with connection.cursor() as cursor:
            for init in startup_init_dbs():
                init(cursor)
        # Created by the tagger loop on its first round, not at startup.
        ProcessedFilesHelper().create_table()


def build_from_migrations(connection, name: str, apply_migrations) -> None:
    """Create the schema the way production has it: db_init, then every migration twice."""
    from services.common import db_init

    with database_env(name):
        db_init.ensure_tables_exist()
    apply_migrations(connection)
    apply_migrations(connection)


def snapshot(connection, name: str) -> dict[str, dict]:
    """Columns and indexes of every base table in database `name`, keyed by table.

    Column position is left out on purpose: ALTER ... ADD COLUMN appends, so a
    migrated table and a freshly created one legitimately order columns differently.
    """
    tables: dict[str, dict] = {}
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT c.table_name AS t, c.column_name AS c, c.column_type AS type, c.is_nullable AS nullable, '
            'c.column_default AS dflt, c.extra AS extra, c.collation_name AS coll '
            'FROM information_schema.columns c JOIN information_schema.tables t '
            'ON t.table_schema = c.table_schema AND t.table_name = c.table_name '
            "WHERE c.table_schema = %s AND t.table_type = 'BASE TABLE'",
            (name,),
        )
        for row in cursor.fetchall():
            table = tables.setdefault(row['t'], {'columns': {}, 'indexes': {}})
            table['columns'][row['c']] = {
                'type': row['type'],
                'nullable': row['nullable'],
                'default': row['dflt'],
                'extra': (row['extra'] or '').lower(),
                'collation': row['coll'],
            }
        cursor.execute(
            'SELECT table_name AS t, index_name AS i, non_unique AS nu, seq_in_index AS seq, '
            'column_name AS c, sub_part AS sub FROM information_schema.statistics WHERE table_schema = %s',
            (name,),
        )
        indexes: dict[tuple[str, str], dict] = {}
        for row in cursor.fetchall():
            entry = indexes.setdefault((row['t'], row['i']), {'unique': not row['nu'], 'columns': []})
            entry['columns'].append((row['seq'], row['c'], row['sub']))
        for (table_name, index_name), entry in indexes.items():
            if table_name not in tables:
                continue
            columns = [f'{column}({sub})' if sub else column for _, column, sub in sorted(entry['columns'])]
            tables[table_name]['indexes'][index_name] = {'unique': entry['unique'], 'columns': columns}
    return tables


def diff(code: dict[str, dict], migrated: dict[str, dict]) -> list[str]:
    """Human-readable differences for every table both schemas contain."""
    problems = []
    for table in sorted(set(code) & set(migrated)):
        for kind, label in (('columns', 'column'), ('indexes', 'index')):
            left, right = code[table][kind], migrated[table][kind]
            for key in sorted(set(left) | set(right)):
                if key not in right:
                    problems.append(f'{table}: {label} {key} only in code: {left[key]}')
                elif key not in left:
                    problems.append(f'{table}: {label} {key} only in migrations: {right[key]}')
                elif left[key] != right[key]:
                    changed = {
                        field: (left[key][field], right[key][field])
                        for field in left[key]
                        if left[key][field] != right[key][field]
                    }
                    problems.append(f'{table}: {label} {key} differs (code, migrations): {changed}')
    return problems
