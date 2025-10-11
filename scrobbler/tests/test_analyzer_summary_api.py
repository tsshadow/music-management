"""Tests for the analyzer summary HTTP endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analyzer.db.repo import AnalyzerRepository

from scrobbler.app.main import app
from scrobbler.tests.fixtures import seed_dataset


@pytest.mark.asyncio
async def test_analyzer_summary_endpoint(client):
    """Ensure the analyzer summary endpoint returns aggregated metrics."""

    await seed_dataset(client)

    repo = AnalyzerRepository(app.state.db_adapter.engine)
    await repo.upsert_media_file(
        file_path="/music/morning-track.flac",
        file_size=12_345,
        file_mtime=datetime.now(timezone.utc),
        audio_hash=None,
        duration=240,
        metadata={"source": "test"},
    )

    response = await client.get("/api/v1/analyzer/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["files"] == 1
    assert payload["songs"] == 2
    assert payload["livesets"] == 1
    assert any(entry["artist"] == "Artist A" and entry["songs"] == 2 for entry in payload["artists"])
    assert any(entry["genre"] == "Uplifting" for entry in payload["genres"])
