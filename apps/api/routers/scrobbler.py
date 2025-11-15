"""Router integration for the Scrobbler and Analyzer services."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from modules.scrobbler.backend.app.api import (
    routes_analyzer,
    routes_analyzer_summary,
    routes_config,
    routes_enrichment,
    routes_export,
    routes_import,
    routes_library,
    routes_listens,
    routes_scrobble,
    routes_stats,
    routes_subsonic,
)
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
from modules.scrobbler.backend.analyzer.db.repo import AnalyzerRepository
from modules.scrobbler.backend.analyzer.services.library_admin_service import (
    AnalyzerLibraryAdminService,
)
from modules.scrobbler.backend.analyzer.services.library_stats_service import (
    AnalyzerLibraryStatsService,
)
from modules.scrobbler.backend.analyzer.services.summary_service import (
    AnalyzerSummaryService,
)

logger = logging.getLogger(__name__)


def register_scrobbler(app: FastAPI) -> None:
    """Attach the Scrobbler backend routers to the shared app."""

    settings = get_settings()
    api_prefix = settings.api_prefix

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - glue
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
        logger.info("Scrobbler services ready")

    @app.on_event("shutdown")
    async def _shutdown() -> None:  # pragma: no cover - glue
        adapter: MariaDBAdapter = app.state.db_adapter
        await adapter.close()

    for route in (
        routes_scrobble.router,
        routes_listens.router,
        routes_library.router,
        routes_stats.router,
        routes_config.router,
        routes_enrichment.router,
        routes_import.router,
        routes_export.router,
        routes_analyzer_summary.router,
        routes_analyzer.router,
    ):
        app.include_router(route, prefix=api_prefix)

    app.include_router(routes_subsonic.router)


__all__ = ["register_scrobbler"]
