from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from .maria import MariaDBAdapter


def create_sqlite_memory_adapter() -> MariaDBAdapter:
    """Return a MariaDBAdapter backed by an in-memory SQLite engine for tests."""

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    return MariaDBAdapter(engine)
