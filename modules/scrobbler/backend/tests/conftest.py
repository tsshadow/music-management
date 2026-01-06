from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path
from typing import Any
import pytest
from httpx import ASGITransport, AsyncClient
ROOT = Path(__file__).resolve().parents[3]
# Ensure root and app path are in sys.path BEFORE imports
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
APP_PATH = str(ROOT / 'modules' / 'scrobbler' / 'backend')
if APP_PATH not in sys.path:
    sys.path.insert(0, APP_PATH)

from app.core.settings import get_settings
# Import app later or inside fixtures if it still fails due to environment
from app.main import app
os.environ.setdefault('SCROBBLER_DB_DSN', 'sqlite+aiosqlite:///:memory:')
get_settings.cache_clear()

class DummyEnrichmentQueueService:
    """Collect enrichment job requests queued during tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def queue_enrich(self, *, since=None, limit: int=500) -> str:
        job_id = f'job-{len(self.calls) + 1}'
        self.calls.append({'since': since, 'limit': limit, 'job_id': job_id})
        return job_id

@pytest.fixture(scope='session')
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def client():
    await app.router.startup()
    dummy_queue = DummyEnrichmentQueueService()
    app.state.enrichment_queue_service = dummy_queue
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as ac:
        ac.enrichment_queue = dummy_queue
        yield ac
    await app.router.shutdown()