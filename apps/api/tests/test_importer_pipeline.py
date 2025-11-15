from __future__ import annotations

import asyncio

import pytest

from apps.api.services.importer.pipeline import ImporterPipeline, RecurringJobManager


class DummyStep:
    def __init__(self, selectors: list[str]):
        self.condition_keys = set(selectors)
        self.calls: list[dict[str, object]] = []

    def run(self, selectors: list[str], **kwargs: object) -> str | None:
        if self.condition_keys.intersection(selectors):
            self.calls.append(kwargs)
            return f"job-{len(self.calls)}"
        return None


class StubPipeline(ImporterPipeline):
    def __init__(self) -> None:
        super().__init__(steps=[])
        self.calls: list[dict[str, object]] = []

    def run_job(self, kind: str, **options: object) -> list[str]:
        self.calls.append({"kind": kind, "options": options})
        return ["job"]


def test_pipeline_translates_options() -> None:
    step = DummyStep(["download-youtube"])
    pipeline = ImporterPipeline([step])

    job_ids = pipeline.run_job("download-youtube", break_on_existing=False, redownload=True)

    assert job_ids == ["job-1"]
    assert step.calls == [{"breakOnExisting": False, "redownload": True}]


@pytest.mark.asyncio
async def test_recurring_job_manager_runs_and_tracks() -> None:
    pipeline = StubPipeline()
    manager = RecurringJobManager(pipeline)
    job = await manager.start("import", interval=0.01)

    await asyncio.sleep(0.03)
    manager.cancel(job.job_id)
    await asyncio.sleep(0)  # allow cancellation to propagate

    assert pipeline.calls, "recurring job should have executed at least once"
    assert job.runs >= 1
    assert job.last_job_ids == ["job"]
    assert list(job.history), "history should store past executions"


@pytest.mark.asyncio
async def test_run_once_returns_job_record() -> None:
    pipeline = StubPipeline()
    manager = RecurringJobManager(pipeline)

    record = await manager.run_once("import")

    assert record.job_ids == ["job"]
    assert record.started_at <= record.completed_at
