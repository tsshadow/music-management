from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ListenBrainzImportRequest(BaseModel):
    """Payload used to trigger a ListenBrainz history import."""

    user: str | None = Field(default=None, description="Override the configured ListenBrainz user")
    token: str | None = Field(default=None, description="Optional ListenBrainz API token")
    since: datetime | None = Field(default=None, description="Only import listens after this timestamp")
    page_size: int = Field(default=100, ge=1, le=500, description="Number of listens fetched per API page")
    max_pages: int | None = Field(default=None, ge=1, description="Optional cap on ListenBrainz pagination")


class ListenBrainzExportRequest(BaseModel):
    """Payload used to push stored listens to ListenBrainz."""

    user: str | None = Field(default=None, description="Override the configured ListenBrainz user")
    token: str | None = Field(default=None, description="Optional ListenBrainz API token")
    since: datetime | None = Field(default=None, description="Only export listens after this timestamp")
    listen_type: Literal["single", "import", "playing_now"] = Field(
        default="import",
        description="ListenBrainz submission type",
    )
    batch_size: int = Field(
        default=100,
        ge=1,
        le=100,
        description="Number of listens sent per API request",
    )
