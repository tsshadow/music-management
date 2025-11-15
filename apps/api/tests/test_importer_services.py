from datetime import datetime
from pathlib import Path

import pytest

from apps.api.models.importer import DownloadTask, DownloadedTrack, TagMutation, TaggingTask
from apps.api.services.importer.download import DownloadService
from apps.api.services.importer.jobs import job_manager
from apps.api.services.importer.tagging import TaggingService


@pytest.fixture(autouse=True)
def clear_jobs():
    job_manager.jobs.clear()
    yield
    job_manager.jobs.clear()


def test_download_service_collects_tracks():
    def fake_handler(task: DownloadTask):
        return [DownloadedTrack(source=task.source, location=Path(f"/tmp/{task.source}"))]

    service = DownloadService({"youtube": fake_handler})
    batch = service.execute([DownloadTask(source="youtube", target="channel", options={})])

    assert batch.tasks[0].source == "youtube"
    assert batch.tracks[0].location == Path("/tmp/youtube")
    assert batch.job_id in job_manager.jobs
    assert job_manager.jobs[batch.job_id]["status"] == "queued"


def test_tagging_service_records_mutations():
    def handler(track, task: TaggingTask) -> TagMutation:
        return TagMutation(location=track.location, applied={"profile": task.profile})

    service = TaggingService(handler)
    track = DownloadedTrack(source="youtube", location=Path("/tmp/example"))
    task = TaggingTask(profile="youtube", tracks=[track], dry_run=False)

    report = service.execute(task)
    assert report.profile == "youtube"
    assert len(report.mutations) == 1
    assert report.mutations[0].applied["profile"] == "youtube"
    assert report.job_id in job_manager.jobs
