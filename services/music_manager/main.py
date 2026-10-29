import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from services.common.config_store import ConfigStore
from services.common.db_init import ensure_tables_exist
from services.common.Helpers.EventService import event_service
from services.common.Helpers.logging_setup import setup_logging
from services.common.version_helper import get_version
from services.music_manager import artist_auto_approve_worker, lms_listen_backfill
from services.music_manager.bpm import status as bpm_status
from services.music_manager.cors import ALLOWED_METHODS, allowed_origins
from services.music_manager.database import (
    DatabaseBusyError,
    DatabaseUnavailableError,
    check_database,
    get_db_connection,
)
from services.music_manager.events_retention import run_events_retention
from services.music_manager.feeds import snapshot as feeds_snapshot
from services.music_manager.feeds.hardness import seed_genre_hardness
from services.music_manager.popular_tracks import worker as popular_tracks_worker
from services.music_manager.routers import (
    analytics,
    artist_curation,
    artist_images,
    bpm,
    channel_links,
    config,
    curation,
    diagnostics,
    downloaders,
    events,
    feeds,
    festivals,
    genre_curation,
    library,
    lineups,
    listening,
    management,
    news,
    radio,
    rating,
    reconcile,
    scanner,
    scrobbler,
    songs,
    stats,
    tagger,
    user_requests,
    users,
)
from services.music_manager.routers.artist_images import run_fetch_missing
from services.music_manager.routers.scanner import run_scanner_loop
from services.music_manager.routers.tagger import run_tagger_loop
from services.music_manager.routers.users import run_lms_db_sync_loop
from services.music_manager.scrobble_rematch import run_scrobble_rematch
from services.music_manager.song_version_worker import run_song_version_grouping
from services.music_manager.thread_registry import start_thread, thread_heartbeats, thread_status

load_dotenv()
logger = logging.getLogger('music-manager')
app = FastAPI(title='Music Manager API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(os.getenv('MUMA_CORS_ORIGINS'), logger),
    allow_methods=list(ALLOWED_METHODS),
    allow_headers=['*'],
    allow_credentials=False,
)
app.include_router(users.router, prefix="/api/users")
app.include_router(events.router, prefix="/api/events")
# /api/auth/* and /api/roles only. The users router itself is mounted once, above: mounting it
# at /api as well published every user route a second time as /api/{user_id}/...
app.include_router(users.auth_router, prefix="/api")
app.include_router(scrobbler.router, prefix="/api/scrobble")
app.include_router(reconcile.router, prefix="/api/scrobble/reconcile")
app.include_router(rating.router, prefix="/api/rating")
app.include_router(stats.router, prefix="/api/stats")
app.include_router(management.router, prefix="/api")
app.include_router(artist_images.router, prefix="/api/artists")
app.include_router(library.router, prefix="/api/library")
# Browse by BPM (docs/designs/bpm-browse/): /api/library/bpm/tracks and /histogram.
app.include_router(bpm.router, prefix="/api/library/bpm")
app.include_router(analytics.router, prefix="/api/analytics")
app.include_router(listening.router, prefix="/api/listening")
app.include_router(tagger.router, prefix="/api/tagger")
app.include_router(scanner.router, prefix="/api/scanner")
app.include_router(config.router, prefix="/api/config")
app.include_router(downloaders.router, prefix="/api/downloaders")
app.include_router(user_requests.router, prefix="/api")  # /api/auth/google, /api/user-requests/*
app.include_router(radio.router, prefix="/api/radio")
app.include_router(news.router, prefix="/api/news")
app.include_router(diagnostics.router, prefix="/api/diagnostics")
app.include_router(curation.router, prefix="/api/curation")
app.include_router(artist_curation.router, prefix="/api/rules/artists")
app.include_router(genre_curation.router, prefix="/api/rules/genres")
app.include_router(festivals.router, prefix="/api/rules/festivals")
app.include_router(lineups.router, prefix="/api/rules/lineups")
app.include_router(songs.router, prefix="/api/songs")
app.include_router(feeds.router, prefix="/api/feeds")
app.include_router(channel_links.router, prefix="/api/channel-links")


def background_workers_enabled() -> bool:
    """Whether startup should spin up the tagger, scanner and radio loops.

    They keep writing to the database on their own schedule, which is right in
    production and wrong against a test database: the radio scheduler holds rows
    in radio_timeline while the integration suite is emptying every table between
    tests, and the two deadlock on the same tables (see tests/integration for the
    lock-wait history). Set MUMA_DISABLE_BACKGROUND_WORKERS=1 to run the API
    without them.
    """
    return os.getenv('MUMA_DISABLE_BACKGROUND_WORKERS', '').strip().lower() not in ('1', 'true', 'yes')


@app.on_event('startup')
def startup_event():
    setup_logging('music-manager')
    ensure_tables_exist()
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                users.init_db(cursor)  # also seeds RBAC roles/permissions, see rbac.init_db
                scrobbler.init_db(cursor)
                rating.init_db(cursor)
                management.init_db(cursor)
                artist_images.init_db(cursor)
                user_requests.init_db(cursor)
                radio.init_db(cursor)
                news.init_db(cursor)
                downloaders.init_db(cursor)
                diagnostics.init_db(cursor)
                events.init_db(cursor)
                feeds.init_db(cursor)
                feeds_snapshot.init_db(cursor)
                # Idempotent: only ever fills a genre whose hardness is still NULL, so a
                # curator's own edit from the genre edit page is never overwritten. Cheap
                # on every later restart -- almost every row already has a value after
                # the first run finds it.
                seed_genre_hardness(cursor)
            conn.commit()
            print('Music Manager: Database initialized')
        finally:
            conn.close()
    if background_workers_enabled():
        # Eenmalige achtergrondtaken: die geven na afloop terug en horen niet in
        # het liveness-register, anders staat /health binnen een minuut op degraded.
        # A loop, not a one-off: the version worker keeps grouping tracks for as long as it
        # has a backlog, and what it learns has to reach the server without waiting for the
        # next deploy. See run_lms_db_sync_loop.
        start_thread('lms-db-sync', run_lms_db_sync_loop, (int(os.getenv('LMS_DB_SYNC_SLEEPTIME', '3600')),))
        threading.Thread(target=run_fetch_missing, daemon=True).start()

        # Lussen die horen te blijven draaien.
        start_thread('tagger', run_tagger_loop, (int(os.getenv('TAGGER_SLEEPTIME', '300')),))
        start_thread('scanner', run_scanner_loop, (int(os.getenv('SCANNER_SLEEPTIME', '3600')),))
        start_thread('radio', radio.run_radio_scheduler)
        start_thread('news', news.run_news_recorder)
        start_thread('events-retention', run_events_retention)
        start_thread('scrobble-rematch', run_scrobble_rematch)
        # Inserts the listens LMS recorded but never relayed (bug report 075).
        start_thread(lms_listen_backfill.THREAD_NAME, lms_listen_backfill.run_lms_listen_backfill)
        start_thread('song-versions', run_song_version_grouping)
        # Judges the artist curation queue on external recording evidence once a day
        # (docs/designs/artist-curation/technical.md, "Scheduled evidence run").
        start_thread(artist_auto_approve_worker.THREAD_NAME, artist_auto_approve_worker.run_artist_auto_approve)
        # Fetches the top tracks of the artists listeners rate or play, for the "Oude hitjes"
        # feed's known-hits tier (docs/designs/old-hits-feed/technical.md, "Popularity crawl").
        start_thread(popular_tracks_worker.THREAD_NAME, popular_tracks_worker.run_popular_tracks)
        # Keeps every active listener's feeds built ahead of the read, so opening
        # Home reads rows instead of running four profile builds. See
        # docs/designs/feeds/home-load.md.
        start_thread(
            'feeds-refresh',
            feeds_snapshot.run_feeds_refresh,
            (feeds.SNAPSHOT_SLUGS, feeds.params_key, feeds.snapshot_body),
        )


# The whole /health answer has to arrive within about this many seconds, whatever MariaDB is
# doing. The probe runs on a small executor so a hung DNS lookup or TCP connect cannot hold
# the request past it; two workers bound how many stuck probes can ever pile up.
HEALTH_DB_DEADLINE_SECONDS = 2.0
_health_probe = ThreadPoolExecutor(max_workers=2, thread_name_prefix='health-db')


def _database_status() -> str:
    """'ok' when MariaDB answered `SELECT 1` within HEALTH_DB_DEADLINE_SECONDS, else 'unreachable'."""
    try:
        future = _health_probe.submit(check_database)
        return 'ok' if future.result(timeout=HEALTH_DB_DEADLINE_SECONDS) else 'unreachable'
    except Exception:  # pylint: disable=broad-except  # timeout or a full executor: both unreachable
        return 'unreachable'


@app.exception_handler(DatabaseBusyError)
@app.exception_handler(DatabaseUnavailableError)
async def database_busy_handler(_request: Request, exc: RuntimeError):
    """An exhausted pool, or no pool at all, is a database outage: answer 503, not 500 or a hang."""
    return JSONResponse(status_code=503, content={'detail': str(exc)}, headers={'Retry-After': '5'})


def _public_source_url() -> str:
    """The `public_source_url` setting if it is a plain http(s) address, else an empty string.

    /health is unauthenticated and the About and login screens turn this value into a link, so
    it is checked here instead of in every client: the scheme must be http or https (any case),
    there must be a host, and no user info (`https://a@evil.example` hides the real host).
    """
    try:
        url = str(ConfigStore().get('public_source_url') or '').strip()
        parts = urlsplit(url)
        if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
            return ''
        if parts.username is not None or parts.password is not None:
            return ''
    except Exception:  # pylint: disable=broad-except  # /health must always answer
        return ''
    return url


@app.get('/health')
def health(response: Response):
    """Rapporteert wat het beweert, zodat de Uptime Kuma-monitor iets meet.

    De oude versie gaf altijd 'ok' terug en bleef dus groen terwijl de
    database weg was of een achtergrondlus aan een exceptie was gestorven.

    The database check runs `SELECT 1` on its own short-lived connection
    (database.check_database), not on a pooled one: the pool only pings a cached
    connection when a query runs, so taking one proved nothing, and an exhausted
    pool used to make this endpoint wait forever. The probe is bounded at
    HEALTH_DB_DEADLINE_SECONDS, so the endpoint always answers.

    `threads` is True per loop when its thread is alive and its heartbeat -- the
    last completed tick -- is younger than that loop's staleness window;
    `heartbeats` carries the detail behind each verdict. `lms_listen_outbox` says, per
    LMS, how many listens it still holds for us and since when; it never affects `status`.
    """
    database = _database_status()

    threads = thread_status()
    threads['events'] = event_service.is_alive()

    heartbeats: dict[str, Any] = thread_heartbeats()
    bpm_analysis = bpm_status.read_status()
    if bpm_analysis is not None:
        heartbeats['bpm-analyzer'] = bpm_status.heartbeat_entry(bpm_analysis)

    healthy = database == 'ok' and all(threads.values())
    if not healthy:
        response.status_code = 503
    return {
        'status': 'ok' if healthy else 'degraded',
        'service': 'music-manager',
        'version': get_version(),
        'source_url': _public_source_url(),
        'database': database,
        'threads': threads,
        'heartbeats': heartbeats,
        'lms_listen_outbox': _lms_listen_outbox_status(),
        # The bpm-analyzer container's own report; informational, never affects `status`
        # (services/music_manager/bpm/status.py says why).
        'bpm_analysis': bpm_analysis,
    }


def _lms_listen_outbox_status() -> list[dict] | None:
    """What each LMS still has to relay to us (lms_listen_backfill.outbox_status); None when unreadable.

    Informational: it never turns /health red. Listens wait there during every restart of this
    service, and LMS drops what it has to with its own WARNING (docs/designs/lms-listen-outbox/).
    """
    try:
        return lms_listen_backfill.outbox_status()
    except Exception:  # pylint: disable=broad-except  # a status field must not break the health check
        logger.debug('lms listen outbox status unavailable', exc_info=True)
        return None


@app.get('/health/backup')
def health_backup(response: Response):
    """Meldt hoe oud de nieuwste databasebackup is, voor een monitor buiten deze host.

    tools/db_backup.py kan zijn eigen verval melden, maar deelt dan een blinde
    vlek met de timer die hem start: een timer die helemaal stopt produceert geen
    fouten en dus ook geen alarm. Precies dat is hier gebeurd -- tussen 23 juli en
    31 augustus 2026 liep er geen backup en merkte niemand het.

    Dit endpoint kijkt van de andere kant: het leest het latest.json dat de job
    naast de dumps schrijft, en geeft 503 zodra die te oud is. De Uptime
    Kuma-monitor die er tegenaan praat draait niet op deze machine, dus hij blijft
    het merken als hier alles stilvalt.

    Bewust los van /health: een verlopen backup is een echt probleem, maar geen
    storing van de dienst, en die twee door elkaar halen levert een piepertje op
    het verkeerde kanaal.
    """
    destination = os.getenv('BACKUP_PATH')
    if not destination:
        response.status_code = 503
        return {'status': 'unconfigured', 'reason': 'BACKUP_PATH is not set'}

    latest = Path(destination) / 'latest.json'
    try:
        payload = json.loads(latest.read_text())
        finished = datetime.fromisoformat(payload['finished_at'])
    except FileNotFoundError:
        response.status_code = 503
        return {'status': 'missing', 'reason': f'{latest} does not exist'}
    except (OSError, ValueError, KeyError) as exc:
        response.status_code = 503
        return {'status': 'unreadable', 'reason': f'{latest}: {exc}'}

    limit_hours = int(os.getenv('BACKUP_STALE_AFTER_HOURS', '36'))
    age_hours = (datetime.now(UTC) - finished).total_seconds() / 3600
    stale = age_hours > limit_hours
    if stale:
        response.status_code = 503
    return {
        'status': 'stale' if stale else 'ok',
        'file': payload.get('file'),
        'finished_at': payload['finished_at'],
        'age_hours': round(age_hours, 1),
        'limit_hours': limit_hours,
        'tables': payload.get('tables'),
    }


# Music Manager is API-only and must never serve a UI of its own: the single
# unified web interface (player + management views) lives in services/frontend
# and is built/served by music-management-server (see Dockerfile-release's
# svelte-build stage, docroot/spotify). Do not add static-file/UI mounting here.
@app.get('/')
def root():
    return {'service': 'music-manager', 'status': 'ok', 'message': 'API only, no UI is served here.'}


# Dit blok draait bij het importeren van de module, ruim voordat startup_event
# setup_logging aanroept. Logging is op dit moment dus nog niet ingericht: de
# info-regel hieronder haalt de standaarddrempel (WARNING) niet en verdwijnt
# stilletjes, en de foutregel valt terug op Pythons ongeformatteerde
# lastResort-handler. Beide missen de events-pipeline. Bekend en geaccepteerd
# gevolg van logging pas bij startup opzetten in plaats van bij import.
artist_images_path = os.getenv('STORAGE_PATH', '/mnt/music/artists')
try:
    os.makedirs(artist_images_path, exist_ok=True)
    logger.info(f'Mounting artist images from {artist_images_path} at /media/artist-images')
    app.mount('/media/artist-images', StaticFiles(directory=artist_images_path), name='artist-images')
except Exception as e:
    logger.error(f'Could not setup artist images storage at {artist_images_path}: {e}')
if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)
