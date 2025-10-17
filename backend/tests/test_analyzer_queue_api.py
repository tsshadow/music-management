from __future__ import annotations

from types import SimpleNamespace

import pytest

import analyzer.api.router as analyzer_router


class DummyQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, str]] = []
        self._counter = 0

    def enqueue(self, job_path: str, **kwargs):
        self._counter += 1
        job_id = f"job-{self._counter}"
        self.calls.append((job_path, kwargs, job_id))
        return SimpleNamespace(id=job_id)


@pytest.mark.asyncio
async def test_scan_library_uses_config_timeout(client, monkeypatch):
    queue = DummyQueue()
    monkeypatch.setattr(analyzer_router, "get_queue", lambda *_, **__: queue)

    update = {"analyzer_scan_job_timeout": "900"}
    response = await client.put("/api/v1/config", json=update)
    assert response.status_code == 200

    payload = {"paths": ["/music"], "force": False}
    response = await client.post("/api/v1/analyzer/library/scan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "job-1"

    assert len(queue.calls) == 1
    job_path, kwargs, job_id = queue.calls[0]
    assert job_path == "analyzer.jobs.handlers.scan_library_job"
    assert job_id == "job-1"
    assert kwargs["job_timeout"] == 900
    assert kwargs["kwargs"]["paths"] == ["/music"]


@pytest.mark.asyncio
async def test_scan_library_split_paths(client, monkeypatch):
    queue = DummyQueue()
    monkeypatch.setattr(analyzer_router, "get_queue", lambda *_, **__: queue)

    payload = {"paths": ["/music/A", "/music/B"], "split_paths": True}
    response = await client.post("/api/v1/analyzer/library/scan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["job_ids"] == ["job-1", "job-2"]

    assert len(queue.calls) == 2
    assert queue.calls[0][1]["kwargs"]["paths"] == ["/music/A"]
    assert queue.calls[1][1]["kwargs"]["paths"] == ["/music/B"]
