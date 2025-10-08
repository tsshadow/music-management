from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from .settings import get_settings

logger = logging.getLogger(__name__)


def build_engine() -> AsyncEngine:
    settings = get_settings()
    kwargs = {"echo": False, "future": True}
    if settings.db_dsn.endswith(":memory:"):
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_async_engine(settings.db_dsn, **kwargs)


async def init_database(engine: AsyncEngine, metadata) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    logger.info("Database schema ensured")
