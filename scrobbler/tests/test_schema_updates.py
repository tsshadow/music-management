from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from scrobbler.app.db.schema import apply_schema_updates


@pytest.mark.asyncio
async def test_apply_schema_updates_creates_tables(tmp_path):
    """Running schema updates should create the core tables for a new database."""

    db_path = tmp_path / "schema.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    try:
        await apply_schema_updates(engine)
        async with engine.begin() as conn:
            def list_tables(connection):
                return sorted(inspect(connection).get_table_names())

            tables = await conn.run_sync(list_tables)
    finally:
        await engine.dispose()

    assert "config" in tables
    assert "listens" in tables
    assert "tracks" in tables
