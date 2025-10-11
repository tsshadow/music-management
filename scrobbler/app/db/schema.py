"""Schema helper utilities for runtime migrations."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from ..models import LISTENS_SCHEMA, MEDIALIBRARY_SCHEMA

__all__ = ["apply_schema_updates"]

MEDIA_LIBRARY_TABLES = {
    "artists",
    "artist_aliases",
    "genres",
    "albums",
    "tracks",
    "track_artists",
    "track_genres",
    "labels",
    "track_labels",
    "title_aliases",
    "media_files",
    "tag_sources",
    "track_tag_attributes",
}

LISTENING_TABLES = {
    "users",
    "listens",
    "listen_match_candidates",
    "listen_artists",
    "listen_genres",
    "config",
}


async def apply_schema_updates(engine: AsyncEngine) -> None:
    """Ensure schemas exist and legacy tables migrate into the new layout."""

    async with engine.begin() as conn:
        await conn.run_sync(_run_schema_updates)


def _run_schema_updates(connection) -> None:
    dialect = connection.dialect.name
    inspector = inspect(connection)

    if dialect == "sqlite":
        _ensure_sqlite_schemas(connection)
    else:
        _ensure_mariadb_schemas(connection)

    _migrate_legacy_tables(connection, inspector, dialect)

    # Refresh inspector after potential migrations
    inspector = inspect(connection)

    _ensure_media_columns(connection, inspector)
    _ensure_listen_columns(connection, inspector)


def _ensure_sqlite_schemas(connection) -> None:
    attached = {row[1] for row in connection.execute(text("PRAGMA database_list"))}
    for schema in (MEDIALIBRARY_SCHEMA, LISTENS_SCHEMA):
        if schema not in attached:
            connection.execute(text(f"ATTACH DATABASE ':memory:' AS {schema}"))


def _ensure_mariadb_schemas(connection) -> None:
    for schema in (MEDIALIBRARY_SCHEMA, LISTENS_SCHEMA):
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS `{schema}`"))


def _migrate_legacy_tables(connection, inspector, dialect: str) -> None:
    legacy_tables = set(inspector.get_table_names())
    if not legacy_tables or dialect == "sqlite":
        return

    medialibrary_tables = set(inspector.get_table_names(schema=MEDIALIBRARY_SCHEMA))
    listens_tables = set(inspector.get_table_names(schema=LISTENS_SCHEMA))

    def rename(table: str, target_schema: str) -> None:
        qualified = f"{target_schema}.{table}"
        if dialect in {"mysql", "mariadb"}:
            connection.execute(text(f"RENAME TABLE `{table}` TO `{target_schema}`.`{table}`"))
        else:
            connection.execute(text(f"ALTER TABLE {table} RENAME TO {qualified}"))

    if dialect in {"mysql", "mariadb"}:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))

    try:
        for table in MEDIA_LIBRARY_TABLES:
            if table in legacy_tables and table not in medialibrary_tables:
                rename(table, MEDIALIBRARY_SCHEMA)
        for table in LISTENING_TABLES:
            if table in legacy_tables and table not in listens_tables:
                rename(table, LISTENS_SCHEMA)
    finally:
        if dialect in {"mysql", "mariadb"}:
            connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def _ensure_media_columns(connection, inspector) -> None:
    tables = set(inspector.get_table_names(schema=MEDIALIBRARY_SCHEMA))

    def ensure_column(table: str, column: str, ddl: str) -> None:
        if table not in tables:
            return
        columns = {
            col["name"]
            for col in inspector.get_columns(table, schema=MEDIALIBRARY_SCHEMA)
        }
        if column not in columns:
            qualified = f"{MEDIALIBRARY_SCHEMA}.{table}"
            connection.execute(text(f"ALTER TABLE {qualified} ADD COLUMN {column} {ddl}"))

    def ensure_index(table: str, index: str, ddl: str) -> None:
        if table not in tables:
            return
        indexes = {
            idx["name"]
            for idx in inspector.get_indexes(table, schema=MEDIALIBRARY_SCHEMA)
        }
        if index not in indexes:
            connection.execute(text(ddl.format(schema=MEDIALIBRARY_SCHEMA)))

    ensure_column("artists", "name_normalized", "VARCHAR(255) NOT NULL DEFAULT ''")
    ensure_column("artists", "sort_name", "VARCHAR(255) NOT NULL DEFAULT ''")
    ensure_column("artists", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

    ensure_column("genres", "name_normalized", "VARCHAR(100) NOT NULL DEFAULT ''")
    ensure_column("genres", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

    ensure_column("albums", "artist_id", "INTEGER")
    ensure_column("albums", "title_normalized", "VARCHAR(255) NOT NULL DEFAULT ''")
    ensure_column("albums", "year", "SMALLINT")
    ensure_column("albums", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

    if "tracks" in tables:
        ensure_column("tracks", "title_normalized", "VARCHAR(255) NOT NULL DEFAULT ''")
        ensure_column("tracks", "primary_artist_id", "INTEGER")
        ensure_column("tracks", "acoustid", "VARCHAR(40)")
        ensure_column("tracks", "track_uid", "VARCHAR(40)")
        ensure_column("tracks", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
        columns = {
            col["name"]
            for col in inspector.get_columns("tracks", schema=MEDIALIBRARY_SCHEMA)
        }
        if "duration_sec" in columns and "duration_secs" not in columns:
            connection.execute(
                text(
                    f"ALTER TABLE {MEDIALIBRARY_SCHEMA}.tracks "
                    "RENAME COLUMN duration_sec TO duration_secs"
                )
            )
        ensure_index(
            "tracks",
            "ix_tracks_track_uid",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_tracks_track_uid "
            "ON {schema}.tracks (track_uid)",
        )


def _ensure_listen_columns(connection, inspector) -> None:
    tables = set(inspector.get_table_names(schema=LISTENS_SCHEMA))

    def ensure_column(table: str, column: str, ddl: str) -> None:
        if table not in tables:
            return
        columns = {
            col["name"]
            for col in inspector.get_columns(table, schema=LISTENS_SCHEMA)
        }
        if column not in columns:
            qualified = f"{LISTENS_SCHEMA}.{table}"
            connection.execute(text(f"ALTER TABLE {qualified} ADD COLUMN {column} {ddl}"))

    def ensure_index(table: str, index: str, ddl: str) -> None:
        if table not in tables:
            return
        indexes = {
            idx["name"]
            for idx in inspector.get_indexes(table, schema=LISTENS_SCHEMA)
        }
        if index not in indexes:
            connection.execute(text(ddl.format(schema=LISTENS_SCHEMA)))

    if "listens" in tables:
        ensure_column("listens", "artist_name_raw", "VARCHAR(255)")
        ensure_column("listens", "track_title_raw", "VARCHAR(255)")
        ensure_column("listens", "album_title_raw", "VARCHAR(255)")
        ensure_column("listens", "match_confidence", "SMALLINT")
        ensure_column("listens", "last_enriched_at", "DATETIME")
        ensure_column("listens", "enrich_status", "VARCHAR(16) DEFAULT 'pending'")
        columns = {
            col["name"]
            for col in inspector.get_columns("listens", schema=LISTENS_SCHEMA)
        }
        if "position_sec" in columns and "position_secs" not in columns:
            connection.execute(
                text(
                    f"ALTER TABLE {LISTENS_SCHEMA}.listens "
                    "RENAME COLUMN position_sec TO position_secs"
                )
            )
        if "duration_sec" in columns and "duration_secs" not in columns:
            connection.execute(
                text(
                    f"ALTER TABLE {LISTENS_SCHEMA}.listens "
                    "RENAME COLUMN duration_sec TO duration_secs"
                )
            )
        ensure_index(
            "listens",
            "ix_listens_enrich_status",
            "CREATE INDEX IF NOT EXISTS ix_listens_enrich_status "
            "ON {schema}.listens (enrich_status)",
        )
        ensure_index(
            "listens",
            "ix_listens_listened_at",
            "CREATE INDEX IF NOT EXISTS ix_listens_listened_at "
            "ON {schema}.listens (listened_at)",
        )
