"""Pydantic models describing importer service contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


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


__all__ = [
    "DownloadTask",
    "DownloadedTrack",
    "DownloadBatch",
    "TaggingTask",
    "TagMutation",
    "TaggingReport",
]
