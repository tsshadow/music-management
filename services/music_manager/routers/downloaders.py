"""Read and write the downloader timing settings and inspect the backoff state.

The settings live in the database rather than in ConfigStore, because the manager
and the worker containers mount different host directories for /app/data and so
do not share config.json. See services/downloader/settings_store.py.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.downloader.account_schedule import DatabaseCheckStore
from services.downloader.rate_state import DatabaseRateStateStore, RateState
from services.downloader.settings_store import DatabaseSettingsStore
from services.downloader.timing import SOURCES, TIMING_FIELDS, load_timing
from services.music_manager.routers.config import verify_api_key

router = APIRouter(tags=['downloaders'])

# Module level so tests can swap them for in-memory stores.
settings_store = DatabaseSettingsStore()
rate_state_store = DatabaseRateStateStore()


class SettingsUpdatePayload(BaseModel):
    source: str
    updates: dict[str, Any] = Field(default_factory=dict)


def _stored(source: str) -> dict[str, Any]:
    """The stored overrides, reporting an outage instead of falling back to defaults.

    `settings_store.load_settings` swallows storage failures on purpose, so a worker
    that cannot reach the database keeps running on the defaults rather than stopping.
    The UI must not inherit that: a form full of defaults is indistinguishable from
    settings that were never saved, with nothing on screen to say otherwise.
    """
    from services.downloader.timing import sanitize_settings
    try:
        raw = settings_store.load(source)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f'Could not read the downloader settings: {exc}') from exc
    return sanitize_settings(source, raw)


def _fields_for(source: str) -> list[dict[str, Any]]:
    stored = _stored(source)
    return [
        {
            'key': item.key,
            'value': stored.get(item.key, item.default),
            'default': item.default,
            'minimum': item.minimum,
            'maximum': item.maximum,
            'unit': item.unit,
            'description': item.description,
        }
        for item in TIMING_FIELDS[source]
    ]


@router.get('/settings')
def get_settings(_auth: dict=Depends(verify_api_key)):
    """The schema of every knob, with the value that is currently in effect."""
    return {'sources': [{'source': source, 'fields': _fields_for(source)} for source in SOURCES]}


@router.post('/settings')
def update_settings(payload: SettingsUpdatePayload, _auth: dict=Depends(verify_api_key)):
    from services.downloader.settings_store import save_settings
    try:
        updated = save_settings(payload.source, payload.updates, store=settings_store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f'Could not store the downloader settings: {exc}') from exc
    return {'status': 'success', 'source': payload.source, 'updated': updated}


def _state_for(source: str) -> dict[str, Any]:
    timing = load_timing(source, overrides=_stored(source))
    state = RateState(source, timing, store=rate_state_store)
    snapshot = state.snapshot()
    effective = timing.with_multiplier(state.multiplier)
    return {
        'source': source,
        'multiplier': state.multiplier,
        'clean_runs': snapshot.clean_runs,
        'consecutive_403': snapshot.consecutive_403,
        'consecutive_429': snapshot.consecutive_429,
        'last_403_at': snapshot.last_403_at.isoformat() if snapshot.last_403_at else None,
        'last_429_at': snapshot.last_429_at.isoformat() if snapshot.last_429_at else None,
        'cooldown_until': snapshot.cooldown_until.isoformat() if snapshot.cooldown_until else None,
        'cooldown_remaining': state.cooldown_remaining(),
        'effective_sweep_interval': effective.sweep_interval,
        'effective_account_cooldown': effective.account_cooldown,
    }


@router.get('/rate-state')
def get_rate_state(_auth: dict=Depends(verify_api_key)):
    """How hard each downloader is currently holding back, and until when."""
    return {'sources': [_state_for(source) for source in SOURCES]}


@router.post('/rate-state/{source}/reset')
def reset_rate_state(source: str, _auth: dict=Depends(verify_api_key)):
    """Forget the backoff for one source and let it run at full speed again."""
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail=f'Unknown downloader source: {source}')
    timing = load_timing(source, overrides=_stored(source))
    RateState(source, timing, store=rate_state_store).reset()
    return {'status': 'success', 'source': source}


@router.get('/schedule/{source}')
def get_schedule(source: str, _auth: dict=Depends(verify_api_key)):
    """When each account of a source was last checked."""
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail=f'Unknown downloader source: {source}')
    try:
        checked = DatabaseCheckStore().load(source)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Could not read the schedule: {exc}') from exc
    return {'source': source,
            'accounts': [{'account': account, 'last_checked_at': when.isoformat()}
                         for account, when in sorted(checked.items())]}


def init_db(cursor) -> None:
    """Create the downloader tables at startup, alongside the other routers."""
    from services.downloader.db_schema import ensure_downloader_tables
    ensure_downloader_tables(cursor)
