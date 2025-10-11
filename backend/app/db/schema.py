"""Schema helper utilities for runtime migrations."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = ["apply_schema_updates"]


async def apply_schema_updates(engine: AsyncEngine) -> None:
    """Ensure new analyzer columns and tables exist in legacy databases."""

    async with engine.begin() as conn:
        await conn.run_sync(_run_schema_updates)


def _run_schema_updates(connection) -> None:
    inspector = inspect(connection)

    def ensure_column(table: str, column: str, ddl: str) -> None:
        columns = {col["name"] for col in inspector.get_columns(table)}
        if column not in columns:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))

    def ensure_index(table: str, index: str, ddl: str) -> None:
        indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        if index not in indexes:
            connection.execute(text(ddl))

    if "artists" in inspector.get_table_names():
        ensure_column("artists", "name_normalized", "VARCHAR(255) NOT NULL DEFAULT ''")
        ensure_column("artists", "sort_name", "VARCHAR(255) NOT NULL DEFAULT ''")
        ensure_column("artists", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

    if "genres" in inspector.get_table_names():
        ensure_column("genres", "name_normalized", "VARCHAR(100) NOT NULL DEFAULT ''")
        ensure_column("genres", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

    if "albums" in inspector.get_table_names():
        ensure_column("albums", "artist_id", "INTEGER")
        ensure_column("albums", "title_normalized", "VARCHAR(255) NOT NULL DEFAULT ''")
        ensure_column("albums", "year", "SMALLINT")
        ensure_column("albums", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

    if "tracks" in inspector.get_table_names():
        ensure_column("tracks", "title_normalized", "VARCHAR(255) NOT NULL DEFAULT ''")
        ensure_column("tracks", "primary_artist_id", "INTEGER")
        ensure_column("tracks", "acoustid", "VARCHAR(40)")
        ensure_column("tracks", "track_uid", "VARCHAR(40)")
        ensure_column("tracks", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
        columns = {col["name"] for col in inspector.get_columns("tracks")}
        if "duration_sec" in columns and "duration_secs" not in columns:
            connection.execute(text("ALTER TABLE tracks RENAME COLUMN duration_sec TO duration_secs"))
        ensure_index(
            "tracks",
            "ix_tracks_track_uid",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_tracks_track_uid ON tracks (track_uid)",
        )

    if "listens" in inspector.get_table_names():
        ensure_column("listens", "artist_name_raw", "VARCHAR(255)")
        ensure_column("listens", "track_title_raw", "VARCHAR(255)")
        ensure_column("listens", "album_title_raw", "VARCHAR(255)")
        ensure_column("listens", "match_confidence", "SMALLINT")
        ensure_column("listens", "last_enriched_at", "DATETIME")
        ensure_column("listens", "enrich_status", "VARCHAR(16) DEFAULT 'pending'")
        columns = {col["name"] for col in inspector.get_columns("listens")}
        if "position_sec" in columns and "position_secs" not in columns:
            connection.execute(text("ALTER TABLE listens RENAME COLUMN position_sec TO position_secs"))
        if "duration_sec" in columns and "duration_secs" not in columns:
            connection.execute(text("ALTER TABLE listens RENAME COLUMN duration_sec TO duration_secs"))
        ensure_index(
            "listens",
            "ix_listens_enrich_status",
            "CREATE INDEX IF NOT EXISTS ix_listens_enrich_status ON listens (enrich_status)",
        )
        ensure_index(
            "listens",
            "ix_listens_listened_at",
            "CREATE INDEX IF NOT EXISTS ix_listens_listened_at ON listens (listened_at)",
        )

