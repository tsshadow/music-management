"""Pydantic models describing importer service contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator


class DownloadTask(BaseModel):
    """Represents a requested download run."""

    source: Literal["youtube", "soundcloud", "telegram", "manual"]
    target: Optional[str] = Field(
        default=None,
        description="Optional account or URL to fetch songs from.",
    )
    options: Dict[str, Any] = Field(default_factory=dict)


class DownloadedTrack(BaseModel):
    """Minimal information about a downloaded audio file."""

    source: str
    location: Path
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(json_encoders={Path: str})


class DownloadBatch(BaseModel):
    """Result payload returned by :class:`DownloadService`."""

    job_id: str
    created_at: datetime
    tasks: List[DownloadTask]
    tracks: List[DownloadedTrack] = Field(default_factory=list)


class TaggingTask(BaseModel):
    """Request to apply metadata to a collection of tracks."""

    profile: Literal["generic", "youtube", "soundcloud", "telegram"] = "generic"
    tracks: List[DownloadedTrack]
    dry_run: bool = False


class TagMutation(BaseModel):
    """Individual tagging outcome entry."""

    location: Path
    applied: Dict[str, Any] = Field(default_factory=dict)
    skipped: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(json_encoders={Path: str})


class TaggingReport(BaseModel):
    """Aggregated result of a tagging request."""

    job_id: str
    created_at: datetime
    profile: str
    mutations: List[TagMutation] = Field(default_factory=list)


class ImporterJobStatus(BaseModel):
    """Snapshot of a single importer job's lifecycle state."""

    id: str
    status: str
    step: Optional[str] = None
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    updated: Optional[datetime] = None
    log: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class JobRunSummary(BaseModel):
    """Aggregate information about a collection of importer jobs started together."""

    job_ids: List[str]
    started_at: datetime
    completed_at: Optional[datetime] = None
    details: List[ImporterJobStatus] = Field(default_factory=list)


class RecurringJobRequest(BaseModel):
    """Payload describing a scheduled importer job."""

    kind: Literal[
        "import",
        "download-youtube",
        "download-soundcloud",
        "download-telegram",
        "tag",
        "tag-soundcloud",
        "tag-youtube",
        "tag-telegram",
        "tag-labels",
        "tag-generic",
    ]
    repeat: bool = True
    interval: Optional[int] = Field(
        default=None,
        description="Interval in seconds between job executions.",
        ge=1,
    )
    break_on_existing: Optional[bool] = Field(default=None)
    redownload: bool = False

    @model_validator(mode="after")
    def _check_interval(cls, model: "RecurringJobRequest") -> "RecurringJobRequest":
        if model.repeat and model.interval is None:
            raise ValueError("interval is required when repeat is true")
        if not model.repeat:
            model.interval = None
        return model


class RecurringJobResponse(BaseModel):
    """Metadata for a scheduled recurring job."""

    job_id: Optional[str] = None
    kind: str
    repeat: bool
    interval: Optional[int] = None
    started_at: datetime
    runs: int
    last_run_at: Optional[datetime] = None
    last_job_ids: List[str] = Field(default_factory=list)
    options: Dict[str, Any] = Field(default_factory=dict)
    history: List[JobRunSummary] = Field(default_factory=list)


class ManualDownloadRequest(BaseModel):
    """Request body for triggering a manual download."""

    source: Literal["youtube", "soundcloud"]
    url: str
    break_on_existing: Optional[bool] = Field(default=None)
    redownload: bool = False


class ManualDownloadResponse(BaseModel):
    """Response emitted after enqueuing a manual download job."""

    job_ids: List[str]
    requested_at: datetime


__all__ = [
    "DownloadTask",
    "DownloadedTrack",
    "DownloadBatch",
    "TaggingTask",
    "TagMutation",
    "TaggingReport",
    "ImporterJobStatus",
    "JobRunSummary",
    "RecurringJobRequest",
    "RecurringJobResponse",
    "ManualDownloadRequest",
    "ManualDownloadResponse",
]
