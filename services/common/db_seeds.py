"""Reference rows a new database needs before the services can work with it.

Some rows are data, not schema: the YouTube categories that are never a genre, the festivals the
tagger recognises, the promo markers that are not artists. A migration used to insert them, so a
database got them only from the deploy. :func:`seed` runs the same inserts from
``services/common/seeds/*.sql``, after the tables exist
(docs/designs/declarative-schema/technical.md, "Seeds move into the init").

Every statement in a seed file is idempotent: a second run inserts nothing, and a row a curator
changed stays as it is (``INSERT IGNORE`` on the table's unique key, or an anti-join). So
:func:`seed` is safe on every start, on a new database and on production alike.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)

#: Where the seed files live, next to this module.
SEEDS_DIR: Final = Path(__file__).resolve().parent / 'seeds'

#: The seed files, in the order :func:`seed` runs them. A table that reads another table's seed
#: comes after it: rules_artists copies the markers from rules_ignored_artists.
SEED_FILES: Final = (
    'rules_genres.sql',
    'rules_festivals.sql',
    'rules_label_name_choices.sql',
    'rules_ignored_artists.sql',
    'rules_artists.sql',
    'rules_scene_group_date_format.sql',
    'radio_stations.sql',
)


def split_statements(sql: str) -> list[str]:
    """Split SQL text into statements on the ``;`` that are outside quotes and comments.

    Knows enough of the MariaDB lexer for the seed files: strings in ``'...'`` and ``"..."``
    with a doubled quote or a backslash escape inside, identifiers in backticks, ``-- `` line
    comments (also after code on the same line) and ``/* */`` block comments. Comments are
    dropped from the result, and so is a statement that is empty after that.
    """
    statements: list[str] = []
    current: list[str] = []
    i, length = 0, len(sql)
    while i < length:
        char = sql[i]
        if char in ("'", '"', '`'):
            end = _end_of_quoted(sql, i)
            current.append(sql[i:end])
            i = end
        elif char == '-' and sql.startswith('--', i) and (i + 2 == length or sql[i + 2].isspace()):
            newline = sql.find('\n', i)
            i = length if newline == -1 else newline
        elif char == '/' and sql.startswith('/*', i):
            close = sql.find('*/', i + 2)
            i = length if close == -1 else close + 2
            current.append(' ')
        elif char == ';':
            statements.append(''.join(current))
            current = []
            i += 1
        else:
            current.append(char)
            i += 1
    statements.append(''.join(current))
    return [statement.strip() for statement in statements if statement.strip()]


def _end_of_quoted(sql: str, start: int) -> int:
    """Index just past the quoted string or identifier that opens at ``start``.

    A doubled quote stays inside the string. A backslash escapes the next character in a string,
    not in a backtick identifier. An unclosed quote runs to the end of the text.
    """
    quote = sql[start]
    i = start + 1
    while i < len(sql):
        char = sql[i]
        if char == '\\' and quote != '`':
            i += 2
            continue
        if char == quote:
            if i + 1 < len(sql) and sql[i + 1] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    return len(sql)


def seed_statements(name: str) -> list[str]:
    """The statements of the seed file ``name`` in :data:`SEEDS_DIR`, in file order."""
    return split_statements((SEEDS_DIR / name).read_text(encoding='utf-8'))


def seed(cursor: Any) -> None:
    """Insert the reference rows of every seed file, in the order of :data:`SEED_FILES`.

    ``cursor`` is an open DB-API cursor on the target database, after every table exists. The
    statements run on its one connection, because some seed files fill a temporary table first.
    A missing seed file or a failing statement raises: a database without its reference rows
    must not look healthy. The caller commits, if its connection does not autocommit.
    """
    for name in SEED_FILES:
        statements = seed_statements(name)
        for statement in statements:
            cursor.execute(statement)
        logger.debug('seeded %s (%d statements)', name, len(statements))
