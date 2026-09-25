"""Read and write the downloader timing settings and inspect the backoff state.

The settings live in the database rather than in ConfigStore, because the manager
and the worker containers mount different host directories for /app/data and so
do not share config.json. See services/downloader/settings_store.py.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.downloader.account_schedule import DatabaseCheckStore
from services.downloader.rate_state import DatabaseRateStateStore, RateState
from services.downloader.settings_store import DatabaseSettingsStore
from services.downloader.timing import SOURCES, TIMING_FIELDS, load_timing
from services.music_manager import downloader_coverage
from services.music_manager.database import get_db_connection
from services.music_manager.deprecation import DEPRECATED_CALL
from services.music_manager.downloader_coverage import ConfiguredAccount, youtube_key
from services.music_manager.routers.users import verify_api_key

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
        raise HTTPException(status_code=503, detail=f'Could not read the downloader settings: {exc}') from exc
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
def get_settings(_auth: dict = Depends(verify_api_key)):
    """The schema of every knob, with the value that is currently in effect."""
    return {'sources': [{'source': source, 'fields': _fields_for(source)} for source in SOURCES]}


@router.post('/settings')
def update_settings(payload: SettingsUpdatePayload, _auth: dict = Depends(verify_api_key)):
    from services.downloader.settings_store import save_settings

    try:
        updated = save_settings(payload.source, payload.updates, store=settings_store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Could not store the downloader settings: {exc}') from exc
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
        # Why the cooldown was set when it is not a plain 403/429, e.g. 'bot_check'
        # (bug report 076); Beheer turns it into an instruction.
        'block_reason': snapshot.block_reason,
        'effective_sweep_interval': effective.sweep_interval,
        'effective_account_cooldown': effective.account_cooldown,
    }


@router.get('/rate-state')
def get_rate_state(_auth: dict = Depends(verify_api_key)):
    """How hard each downloader is currently holding back, and until when."""
    return {'sources': [_state_for(source) for source in SOURCES]}


@router.post('/rate-state/{source}/reset')
def reset_rate_state(source: str, _auth: dict = Depends(verify_api_key)):
    """Forget the backoff for one source and let it run at full speed again."""
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail=f'Unknown downloader source: {source}')
    timing = load_timing(source, overrides=_stored(source))
    RateState(source, timing, store=rate_state_store).reset()
    return {'status': 'success', 'source': source}


@router.get('/schedule/{source}', deprecated=True, dependencies=[DEPRECATED_CALL])
def get_schedule(source: str, _auth: dict = Depends(verify_api_key)):
    """When each account of a source was last checked."""
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail=f'Unknown downloader source: {source}')
    try:
        checked = DatabaseCheckStore().load(source)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Could not read the schedule: {exc}') from exc
    return {
        'source': source,
        'accounts': [
            {'account': account, 'last_checked_at': when.isoformat()} for account, when in sorted(checked.items())
        ],
    }


class CoverageQueries:
    """The four reads behind the coverage page, one statement each, on the manager's pool.

    Module level so tests can swap it for canned data. Every method answers for one
    source; the YouTube ones key on `<name>#video` for the video form of a channel, which
    is how the schedule and the ledger file it too.
    """

    def _connection(self):
        connection = get_db_connection()
        if connection is None:
            raise RuntimeError('no database connection')
        return connection

    def configured(self, source: str) -> list[ConfiguredAccount]:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                if source == 'youtube':
                    cursor.execute(
                        'SELECT name, download_type FROM downloads_youtube_accounts WHERE active = 1 ORDER BY name'
                    )
                    return [
                        ConfiguredAccount(
                            row['name'], youtube_key(row['name'], row['download_type']), row['download_type']
                        )
                        for row in cursor.fetchall()
                    ]
                cursor.execute('SELECT name FROM downloads_soundcloud_accounts ORDER BY name')
                return [ConfiguredAccount(row['name'], row['name']) for row in cursor.fetchall()]
        finally:
            connection.close()

    def last_downloads(self, source: str) -> dict[str, datetime]:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                if source == 'youtube':
                    cursor.execute(
                        'SELECT account, download_type, MAX(added_at) AS last_at FROM downloads_youtube_archive '
                        'GROUP BY account, download_type'
                    )
                    return {
                        youtube_key(row['account'], row['download_type']): row['last_at']
                        for row in cursor.fetchall()
                        if row['last_at'] is not None
                    }
                cursor.execute(
                    'SELECT account, MAX(added_at) AS last_at FROM downloads_soundcloud_archive GROUP BY account'
                )
                return {row['account']: row['last_at'] for row in cursor.fetchall() if row['last_at'] is not None}
        finally:
            connection.close()

    def recent_downloads(self, source: str) -> tuple[int, int]:
        """Archive rows of the last 7 and 30 days. Rows with no timestamp are in neither."""
        table = 'downloads_youtube_archive' if source == 'youtube' else 'downloads_soundcloud_archive'
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT SUM(added_at >= NOW() - INTERVAL 7 DAY) AS week, '
                    f'       SUM(added_at >= NOW() - INTERVAL 30 DAY) AS month '
                    f'FROM {table} WHERE added_at IS NOT NULL'
                )
                row = cursor.fetchone() or {}
                return int(row.get('week') or 0), int(row.get('month') or 0)
        finally:
            connection.close()

    def write_offs(self, source: str) -> dict[str, int]:
        connection = self._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT reason, COUNT(*) AS n FROM downloads_soundcloud_unavailable WHERE source = %s GROUP BY reason',
                    (source,),
                )
                return {row['reason']: int(row['n']) for row in cursor.fetchall()}
        finally:
            connection.close()


coverage_queries = CoverageQueries()


@router.get('/coverage/{source}')
def get_coverage(source: str, _auth: dict = Depends(verify_api_key)):
    """How complete every followed channel of a source is. See docs/designs/channel-coverage."""
    if source not in downloader_coverage.SOURCES:
        raise HTTPException(status_code=400, detail=f'Unknown downloader source: {source}')
    try:
        configured = coverage_queries.configured(source)
        checks = DatabaseCheckStore().load(source)
        last_downloads = coverage_queries.last_downloads(source)
        week, month = coverage_queries.recent_downloads(source)
        write_offs = coverage_queries.write_offs(source)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Could not read the coverage: {exc}') from exc
    # The backoff is context, not the point of the page: an outage there must not
    # take the counts down with it.
    try:
        rate_state = _state_for(source)
    except HTTPException:
        rate_state = None
    return downloader_coverage.build_coverage(
        source, configured, checks, last_downloads, week, month, write_offs, rate_state, datetime.now()
    )


def init_db(cursor) -> None:
    """Create the downloader tables at startup, alongside the other routers."""
    from services.downloader.db_schema import ensure_downloader_tables

    ensure_downloader_tables(cursor)
