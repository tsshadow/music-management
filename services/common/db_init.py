"""Create the shared database's tables and seed rows on start-up.

The tables are declared in services/common/schema_tables.py. This only creates what is missing;
it never alters a table that exists. Adding a column or an index to an existing database is
services/common/schema_reconcile.py's job, which the deploy runs before the containers start.
"""

import logging

from services.common import db_seeds, schema_tables
from services.common.Helpers.DatabaseConnector import DatabaseConnector

#: Outcome of the last ensure_tables_exist() in this process: 'unknown' before it ran, then
#: 'ok' or 'failed'. /health reports it, so a stack that started with missing tables says so.
_status = 'unknown'


def schema_status() -> str:
    """'ok', 'failed' or 'unknown': how the last create pass in this process ended."""
    return _status


def create_tables(cursor) -> None:
    """Run every declared CREATE TABLE and CREATE VIEW; an existing one is left as it is."""
    for _, statement in schema_tables.TABLES + schema_tables.VIEWS:
        cursor.execute(statement)


def ensure_tables_exist() -> bool:
    """Create every missing table and view, then the seed rows (services/common/db_seeds.py).

    A failure stops the pass at that statement and is logged at ERROR; start-up goes on, and
    schema_status() answers 'failed' until a later pass succeeds. Returns whether it succeeded.
    """
    global _status  # pylint: disable=global-statement  # one process-wide outcome, read by /health
    try:
        conn = DatabaseConnector().connect()
        try:
            with conn.cursor() as cursor:
                create_tables(cursor)
                db_seeds.seed(cursor)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pylint: disable=broad-except  # start-up goes on; /health reports it
        logging.error('Failed to ensure DB tables exist: %s', exc)
        _status = 'failed'
        return False
    _status = 'ok'
    return True
