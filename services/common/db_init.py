"""Create the shared database's tables and seed rows on start-up.

The tables are declared in services/common/schema_tables.py. This only creates what is missing;
it never alters a table that exists. Adding a column or an index to an existing database is
services/common/schema_reconcile.py's job, which the deploy runs before the containers start.
"""

import logging

from services.common import db_seeds, schema_tables
from services.common.Helpers.DatabaseConnector import DatabaseConnector


def create_tables(cursor) -> None:
    """Run every declared CREATE TABLE and CREATE VIEW; an existing one is left as it is."""
    for _, statement in schema_tables.TABLES + schema_tables.VIEWS:
        cursor.execute(statement)


def ensure_tables_exist() -> None:
    """Create every missing table and view, then the seed rows (services/common/db_seeds.py)."""
    try:
        conn = DatabaseConnector().connect()
        try:
            with conn.cursor() as cursor:
                create_tables(cursor)
                db_seeds.seed(cursor)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logging.warning('Failed to ensure DB tables exist: %s', exc)
