"""Unified FastAPI application exposing MuMa services."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Set

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from analyzer.db.repo import AnalyzerRepository
from analyzer.services.library_admin_service import AnalyzerLibraryAdminService
from analyzer.services.library_stats_service import AnalyzerLibraryStatsService
from analyzer.services.summary_service import AnalyzerSummaryService

from modules.importer.api.router import (
    DEFAULT_CORS_ORIGINS,
    importer_router,
    importer_shutdown,
    importer_startup,
    mount_frontend,
)
from modules.scrobbler.backend.app import api as scrobbler_api
from modules.scrobbler.backend.app.core.settings import get_settings
from modules.scrobbler.backend.app.core.startup import build_engine, init_database
from modules.scrobbler.backend.app.db.maria import MariaDBAdapter
from modules.scrobbler.backend.app.models import metadata
from modules.scrobbler.backend.app.services.deduplication_service import (
    DeduplicationService,
)
from modules.scrobbler.backend.app.services.enrichment_queue_service import (
    EnrichmentQueueService,
)
from modules.scrobbler.backend.app.services.ingest_service import IngestService
from modules.scrobbler.backend.app.services.listenbrainz_export_service import (
    ListenBrainzExportService,
)
from modules.scrobbler.backend.app.services.listenbrainz_service import (
    ListenBrainzImportService,
)
from modules.scrobbler.backend.app.services.stats_service import StatsService


def _resolve_cors_origins() -> List[str]:
    """Combine importer and scrobbler CORS declarations."""

    origins: Set[str] = set()
    settings = get_settings()
    if settings.cors_origins:
        origins.update(settings.cors_origins)
    importer_origins = os.getenv("CORS_ORIGINS")
    if importer_origins:
        origins.update(origin.strip() for origin in importer_origins.split(",") if origin.strip())
    elif DEFAULT_CORS_ORIGINS:
        origins.update(DEFAULT_CORS_ORIGINS)
    return sorted(origins)


app = FastAPI(title="MuMa API")


cors_origins = _resolve_cors_origins()
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
async def on_startup() -> None:
    """Initialise application services and ensure both schemas exist."""

    settings = get_settings()
    engine = build_engine()
    await init_database(engine, metadata)
    adapter = MariaDBAdapter(engine)
    ingest_service = IngestService(adapter)
    app.state.db_adapter = adapter
    app.state.ingest_service = ingest_service
    app.state.deduplication_service = DeduplicationService(adapter)
    app.state.stats_service = StatsService(adapter)
    analyzer_repo = AnalyzerRepository(engine)
    app.state.analyzer_summary_service = AnalyzerSummaryService(analyzer_repo)
    app.state.analyzer_library_stats_service = AnalyzerLibraryStatsService(analyzer_repo)
    app.state.analyzer_library_admin_service = AnalyzerLibraryAdminService(analyzer_repo)
    app.state.listenbrainz_service = ListenBrainzImportService(
        ingest_service,
        base_url=settings.listenbrainz_base_url,
        musicbrainz_base_url=settings.musicbrainz_base_url,
        musicbrainz_user_agent=settings.musicbrainz_user_agent,
    )
    app.state.listenbrainz_export_service = ListenBrainzExportService(
        adapter,
        base_url=settings.listenbrainz_base_url,
    )
    app.state.enrichment_queue_service = EnrichmentQueueService(settings)
    await importer_startup()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Dispose database resources when the application stops."""

    adapter: MariaDBAdapter = app.state.db_adapter
    await adapter.close()
    await importer_shutdown()


settings = get_settings()
app.include_router(scrobbler_api.routes_scrobble.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_listens.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_library.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_stats.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_config.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_enrichment.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_import.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_export.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_analyzer_summary.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_analyzer.router, prefix=settings.api_prefix)
app.include_router(scrobbler_api.routes_subsonic.router)

app.include_router(importer_router)


static_dir = Path(scrobbler_api.__file__).resolve().parent / "static"
if static_dir.exists():
    assets_dir = static_dir / "assets"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

mount_frontend(app)


@app.get("/", include_in_schema=False)
async def root() -> HTMLResponse:
    """Serve the Scrobbler SPA index page when available."""

    if static_dir.exists():
        index = static_dir / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
    return HTMLResponse("<h1>MuMa API</h1>")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> HTMLResponse:
    """Return the SPA entrypoint for client-side routes outside the API namespace."""

    api_prefix = settings.api_prefix.lstrip("/")
    if api_prefix and full_path.startswith(api_prefix):
        raise HTTPException(status_code=404)
    if full_path.startswith("static/") or full_path.startswith("assets/"):
        raise HTTPException(status_code=404)
    if static_dir.exists():
        index = static_dir / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
    raise HTTPException(status_code=404)
