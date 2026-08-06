import logging
import os
import threading

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.common.db_init import ensure_tables_exist
from services.common.Helpers.EventService import event_service
from services.common.version_helper import get_version
from services.music_manager.database import get_db_connection
from services.music_manager.events_retention import run_events_retention
from services.music_manager.ntfy_listener import start_ntfy_listener
from services.music_manager.routers import (
    analytics,
    artist_images,
    config,
    diagnostics,
    downloaders,
    events,
    jobs,
    library,
    management,
    notifications,
    radio,
    rating,
    scanner,
    scrobbler,
    stats,
    tagger,
    user_requests,
    users,
)
from services.music_manager.routers.artist_images import run_fetch_missing
from services.music_manager.routers.scanner import run_scanner_loop
from services.music_manager.routers.tagger import run_tagger_loop
from services.music_manager.routers.users import run_lms_db_sync
from services.music_manager.thread_registry import start_thread, thread_status

load_dotenv()
logger = logging.getLogger('music-manager')
logging.basicConfig(level=logging.INFO)
app = FastAPI(title='Music Manager API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
app.include_router(users.router, prefix="/api/users")
app.include_router(events.router, prefix="/api/events") # before /api/auth/* below: its bare /{user_id} DELETE would otherwise shadow /api/events
app.include_router(users.router, prefix="/api") # For /api/auth/*
app.include_router(scrobbler.router, prefix="/api/scrobble")
app.include_router(rating.router, prefix="/api/rating")
app.include_router(stats.router, prefix="/api/stats")
app.include_router(management.router, prefix="/api")
app.include_router(artist_images.router, prefix="/api/artists")
app.include_router(library.router, prefix="/api/library")
app.include_router(analytics.router, prefix="/api/analytics")
app.include_router(notifications.router, prefix="/api/notifications")
app.include_router(tagger.router, prefix="/api/tagger")
app.include_router(scanner.router, prefix="/api/scanner")
app.include_router(jobs.router, prefix="/api/jobs")
app.include_router(config.router, prefix="/api/config")
app.include_router(downloaders.router, prefix="/api/downloaders")
app.include_router(user_requests.router, prefix="/api") # /api/auth/google, /api/user-requests/*
app.include_router(radio.router, prefix="/api/radio")
app.include_router(diagnostics.router, prefix="/api/diagnostics")

@app.on_event('startup')
def startup_event():
    ensure_tables_exist()
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                users.init_db(cursor) # also seeds RBAC roles/permissions, see rbac.init_db
                scrobbler.init_db(cursor)
                rating.init_db(cursor)
                management.init_db(cursor)
                artist_images.init_db(cursor)
                notifications.init_db(cursor)
                user_requests.init_db(cursor)
                radio.init_db(cursor)
                downloaders.init_db(cursor)
                diagnostics.init_db(cursor)
                events.init_db(cursor)
            conn.commit()
            print('Music Manager: Database initialized')
        finally:
            conn.close()
    # Eenmalige achtergrondtaken: die geven na afloop terug en horen niet in
    # het liveness-register, anders staat /health binnen een minuut op degraded.
    threading.Thread(target=run_lms_db_sync, daemon=True).start()
    threading.Thread(target=run_fetch_missing, daemon=True).start()

    # Lussen die horen te blijven draaien.
    start_thread('tagger', run_tagger_loop, (int(os.getenv('TAGGER_SLEEPTIME', '300')),))
    start_thread('scanner', run_scanner_loop, (int(os.getenv('SCANNER_SLEEPTIME', '3600')),))
    start_thread('radio', radio.run_radio_scheduler)
    start_thread('events-retention', run_events_retention)
    start_ntfy_listener()

@app.get('/health')
def health(response: Response):
    """Rapporteert wat het beweert, zodat de Uptime Kuma-monitor iets meet.

    De oude versie gaf altijd 'ok' terug en bleef dus groen terwijl de
    database weg was of een achtergrondlus aan een exceptie was gestorven.

    get_db_connection() geeft alleen None terug als de pool zelf niet
    aangemaakt kon worden; als de pool wel bestaat maar geen connectie meer
    kan uitgeven, gooit hij een exceptie. Die vangen we hier af, want een
    monitoring-endpoint dat zelf crasht is erger dan een dat liegt.
    """
    conn = None
    try:
        conn = get_db_connection()
    except Exception:
        conn = None
    database = 'unreachable'
    if conn:
        database = 'ok'
        try:
            conn.close()
        except Exception:
            pass

    threads = thread_status()
    threads['events'] = event_service.is_alive()

    healthy = database == 'ok' and all(threads.values())
    if not healthy:
        response.status_code = 503
    return {
        'status': 'ok' if healthy else 'degraded',
        'service': 'music-manager',
        'version': get_version(),
        'database': database,
        'threads': threads,
    }

# Music Manager is API-only and must never serve a UI of its own: the single
# unified web interface (player + management views) lives in services/frontend
# and is built/served by music-management-server (see Dockerfile-release's
# svelte-build stage, docroot/spotify). Do not add static-file/UI mounting here.
@app.get('/')
def root():
    return {'service': 'music-manager', 'status': 'ok', 'message': 'API only, no UI is served here.'}

artist_images_path = os.getenv('STORAGE_PATH', '/mnt/music/artists')
try:
    os.makedirs(artist_images_path, exist_ok=True)
    logger.info(f'Mounting artist images from {artist_images_path} at /media/artist-images')
    app.mount('/media/artist-images', StaticFiles(directory=artist_images_path), name='artist-images')
except Exception as e:
    logger.error(f'Could not setup artist images storage at {artist_images_path}: {e}')
if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)