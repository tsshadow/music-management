from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from .deps import get_ingest_service, verify_api_key
from ..schemas.common import ArtistInput, ScrobblePayload, TrackInput
from ..services.ingest_service import IngestService
router = APIRouter(prefix='/rest', tags=['subsonic'])

@router.get('/ping.view')
async def ping():
    """Return a basic Subsonic-compatible health response."""
    return {'status': 'ok'}

@router.get('/scrobble.view', dependencies=[Depends(verify_api_key)])
async def subsonic_scrobble(u: str=Query(..., alias='u'), track_id: str=Query(..., alias='id'), time: int=Query(..., alias='time'), t: str | None=None, a: str | None=None, al: str | None=None, g: str | None=None, service: IngestService=Depends(get_ingest_service)):
    """Translate a Subsonic scrobble request into the generic ingest payload."""
    listened_at = datetime.fromtimestamp(time / 1000, tz=timezone.utc).replace(tzinfo=None)
    track_title = t or track_id
    library_artists = []
    if a:
        library_artists.append(ArtistInput(name=a))
    rules_genres = g.split(',') if g else []
    payload = ScrobblePayload(user=u, source='subsonic', listened_at=listened_at, position_secs=None, duration_secs=None, source_track_id=track_id, track=TrackInput(title=track_title, album=al), library_artists=library_artists, rules_genres=rules_genres)
    await service.ingest(payload)
    return {'status': 'ok'}
