from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ..schemas.common import ArtistInput, ScrobblePayload, TrackInput
from ..services.ingest_service import IngestService
from .deps import get_ingest_service, verify_api_key

router = APIRouter(prefix="/rest", tags=["subsonic"])


@router.get("/ping.view")
async def ping():
    """Return a basic Subsonic-compatible health response."""

    return {"status": "ok"}


@router.get("/scrobble.view", dependencies=[Depends(verify_api_key)])
async def subsonic_scrobble(
    u: str = Query(..., alias="u"),
    id: str = Query(..., alias="id"),
    time: int = Query(..., alias="time"),
    t: str | None = None,
    a: str | None = None,
    al: str | None = None,
    g: str | None = None,
    service: IngestService = Depends(get_ingest_service),
):
    """Translate a Subsonic scrobble request into the generic ingest payload."""

    listened_at = datetime.utcfromtimestamp(time / 1000)
    track_title = t or id
    artists = []
    if a:
        artists.append(ArtistInput(name=a))
    genres = g.split(",") if g else []
    payload = ScrobblePayload(
        user=u,
        source="subsonic",
        listened_at=listened_at,
        position_secs=None,
        duration_secs=None,
        source_track_id=id,
        track=TrackInput(title=track_title, album=al),
        artists=artists,
        genres=genres,
    )
    await service.ingest(payload)
    return {"status": "ok"}
