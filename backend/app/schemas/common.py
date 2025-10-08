from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ArtistInput(BaseModel):
    name: str
    role: Literal["primary", "featured", "remixer", "composer"] = "primary"


class TrackInput(BaseModel):
    title: str
    album: str | None = None
    album_year: int | None = None
    track_no: int | None = None
    disc_no: int | None = None
    duration_secs: int | None = None
    mbid: str | None = None
    isrc: str | None = None


class ScrobblePayload(BaseModel):
    user: str
    source: str = Field(default="lms")
    listened_at: datetime
    position_secs: int | None = None
    duration_secs: int | None = None
    source_track_id: str | None = None
    track: TrackInput
    artists: list[ArtistInput] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
