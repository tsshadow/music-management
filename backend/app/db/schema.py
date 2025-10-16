"""Schema helper utilities for provisioning database structures."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ..models import LISTENS_SCHEMA, MEDIALIBRARY_SCHEMA, metadata

__all__ = ["apply_schema_updates"]


async def apply_schema_updates(engine: AsyncEngine) -> None:
    """Ensure configured schemas exist and create tables defined in metadata."""

    async with engine.begin() as conn:
        await conn.run_sync(_ensure_schemas_and_tables)


def _ensure_schemas_and_tables(connection) -> None:
    dialect = connection.dialect.name

    if dialect == "sqlite":
        _ensure_sqlite_schemas(connection)
    else:
        _ensure_mariadb_schemas(connection)

    metadata.create_all(bind=connection, checkfirst=True)


def _ensure_sqlite_schemas(connection) -> None:
    attached = {row[1] for row in connection.execute(text("PRAGMA database_list"))}
    for schema in filter(None, (MEDIALIBRARY_SCHEMA, LISTENS_SCHEMA)):
        if schema not in attached:
            connection.execute(text(f"ATTACH DATABASE ':memory:' AS {schema}"))


def _ensure_mariadb_schemas(connection) -> None:
    for schema in filter(None, (MEDIALIBRARY_SCHEMA, LISTENS_SCHEMA)):
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS `{schema}`"))
