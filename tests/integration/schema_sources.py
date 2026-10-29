"""Where this project's schema is declared, and how a fresh database gets it.

Every table of the shared database is declared once, in services/common/schema_tables.py
(docs/designs/declarative-schema/). This module reads that declaration, checks that no other
file under services/ declares a table of its own, and builds a database from nothing the way a
fresh stack does: ``db_init.ensure_tables_exist()`` (tables, views, seed rows), then every
``init_db`` main.py's startup calls.

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

# The one file that may declare a table in the shared database.
SCHEMA_FILE = 'services/common/schema_tables.py'

# Not part of the shared MariaDB: the ml-analyzer keeps its own database
# (services/ml-analyzer/db_init.sql), and the rest are not Python services.
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
# comment or docstring that mentions "CREATE TABLE IF NOT EXISTS that ..." is not
# mistaken for a declaration.
_CREATE_RE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z0-9_{}.]+)`?\s*\(',
    re.IGNORECASE,
)


def _is_test_file(path: Path) -> bool:
    """True for the files the unit suite collects or supports, which declare no schema."""
    name = path.name
    return name.endswith('Test.py') or name.startswith('test_') or name == 'conftest.py' or name == 'mock_base.py'


def python_schema_files() -> list[Path]:
    """Every non-test Python file under services/ that could create a shared table."""
    files = []
    for path in sorted((ROOT / 'services').rglob('*.py')):
        relative = path.relative_to(ROOT / 'services')
        if set(relative.parts[:-1]) & _EXCLUDED_DIRS or _is_test_file(path):
            continue
        files.append(path)
    return files


def stray_declarations() -> dict[str, list[str]]:
    """File -> the tables it declares, for every file under services/ but SCHEMA_FILE."""
    stray: dict[str, list[str]] = {}
    for path in python_schema_files():
        relative = str(path.relative_to(ROOT))
        if relative == SCHEMA_FILE:
            continue
        code = '\n'.join(
            line for line in path.read_text(encoding='utf-8').splitlines() if not line.strip().startswith('#')
        )
        names = _CREATE_RE.findall(code)
        if names:
            stray[relative] = names
    return stray


def declared_tables() -> set[str]:
    """Every table schema_tables.py declares: what a deployed stack must have."""
    from services.common import schema_tables

    return {name for name, _ in schema_tables.TABLES}


def declared_views() -> set[str]:
    """Every view schema_tables.py declares."""
    from services.common import schema_tables

    return {name for name, _ in schema_tables.VIEWS}


def startup_init_dbs() -> list:
    """The init_db functions main.py's startup runs, in its order.

    Read from the startup function itself, so a router wired in there is run here
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

    db_init.ensure_tables_exist() does; it reads the variable when it connects, so setting
    it around the call is enough.
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


def build_fresh(connection, name: str) -> None:
    """Create the schema and seed rows the way a fresh stack does, in database `name`."""
    from services.common import db_init

    with database_env(name):
        db_init.ensure_tables_exist()
    with connection.cursor() as cursor:
        for init in startup_init_dbs():
            init(cursor)
    connection.commit()
