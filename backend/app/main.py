from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    routes_config,
    routes_import,
    routes_listens,
    routes_scrobble,
    routes_stats,
    routes_subsonic,
)
from .core.settings import get_settings
from .core.startup import build_engine, init_database
from .db.maria import MariaDBAdapter
from .models import metadata
from .services.ingest_service import IngestService
from .services.listenbrainz_service import ListenBrainzImportService
from .services.stats_service import StatsService

logger = logging.getLogger(__name__)

app = FastAPI(title="Scrobbler")


@app.on_event("startup")
async def on_startup():
    """Initialize application services and ensure the database schema exists."""

    settings = get_settings()
    engine = build_engine()
    await init_database(engine, metadata)
    adapter = MariaDBAdapter(engine)
    ingest_service = IngestService(adapter)
    app.state.db_adapter = adapter
    app.state.ingest_service = ingest_service
    app.state.stats_service = StatsService(adapter)
    app.state.listenbrainz_service = ListenBrainzImportService(
        ingest_service,
        base_url=settings.listenbrainz_base_url,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    logger.info("Application startup complete")


@app.on_event("shutdown")
async def on_shutdown():
    """Dispose database resources when the application stops."""

    adapter: MariaDBAdapter = app.state.db_adapter
    await adapter.close()


app.include_router(
    routes_scrobble.router,
    prefix=get_settings().api_prefix,
)
app.include_router(
    routes_listens.router,
    prefix=get_settings().api_prefix,
)
app.include_router(
    routes_stats.router,
    prefix=get_settings().api_prefix,
)
app.include_router(
    routes_config.router,
    prefix=get_settings().api_prefix,
)
app.include_router(
    routes_import.router,
    prefix=get_settings().api_prefix,
)
static_dir = Path(__file__).parent / "static"
app.include_router(routes_subsonic.router)

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Serve the built single-page application or a simple fallback message."""

    if static_dir.exists():
        index = static_dir / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
    return HTMLResponse("<h1>Scrobbler</h1>")
