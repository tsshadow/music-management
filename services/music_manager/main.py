import logging
import os
import threading
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from services.music_manager.database import get_db_connection
from services.music_manager.routers import users, scrobbler, rating, stats, management, artist_images, notifications, library, tagger, scanner, jobs, config
from services.music_manager.routers.users import run_lms_db_sync
from services.music_manager.routers.tagger import run_tagger_loop
from services.music_manager.routers.scanner import run_scanner_loop
from services.music_manager.ntfy_listener import start_ntfy_listener
from services.common.db_init import ensure_tables_exist
from services.common.version_helper import get_version, get_release_notes, get_changelog
load_dotenv()
logger = logging.getLogger('music-manager')
logging.basicConfig(level=logging.INFO)
app = FastAPI(title='Music Manager API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
app.include_router(users.router, prefix="/api/users")
app.include_router(users.router, prefix="/api") # For /api/auth/*
app.include_router(scrobbler.router, prefix="/api/scrobble")
app.include_router(rating.router, prefix="/api/rating")
app.include_router(stats.router, prefix="/api/stats")
app.include_router(management.router, prefix="/api")
app.include_router(artist_images.router, prefix="/api/artists")
app.include_router(library.router, prefix="/api/library")
app.include_router(notifications.router, prefix="/api/notifications")
app.include_router(tagger.router, prefix="/api/tagger")
app.include_router(scanner.router, prefix="/api/scanner")
app.include_router(jobs.router, prefix="/api/jobs")
app.include_router(config.router, prefix="/api/config")

@app.on_event('startup')
def startup_event():
    ensure_tables_exist()
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                users.init_db(cursor)
                scrobbler.init_db(cursor)
                rating.init_db(cursor)
                management.init_db(cursor)
                artist_images.init_db(cursor)
                notifications.init_db(cursor)
            conn.commit()
            print('Music Manager: Database initialized')
        finally:
            conn.close()
    threading.Thread(target=run_lms_db_sync, daemon=True).start()
    threading.Thread(target=run_tagger_loop, args=(int(os.getenv('TAGGER_SLEEPTIME', '300')),), daemon=True).start()
    threading.Thread(target=run_scanner_loop, args=(int(os.getenv('SCANNER_SLEEPTIME', '3600')),), daemon=True).start()
    start_ntfy_listener()

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'music-manager', 'version': get_version()}

def serve_frontend(fastapi_app: FastAPI):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_path = os.path.join(base_dir, 'frontend', 'dist')
    logger.info(f'Checking for frontend at: {frontend_path}')
    logger.info(f'Current Working Directory: {os.getcwd()}')
    logger.info(f'__file__: {__file__}')
    if os.path.exists(frontend_path):
        logger.info(f'Frontend found at {frontend_path}. Mounting at /')
        fastapi_app.mount('/', StaticFiles(directory=frontend_path, html=True), name='frontend')
    else:
        logger.warning(f'Frontend build directory not found at {frontend_path}; static files will not be served.')
        parent = os.path.dirname(frontend_path)
        if os.path.exists(parent):
            logger.info(f'Parent directory {parent} exists. Contents: {os.listdir(parent)}')

        @fastapi_app.get('/', response_class=HTMLResponse)
        def root_fallback():
            return '<h1>Music Manager</h1><p>Frontend not found. API is active.</p>'
artist_images_path = os.getenv('STORAGE_PATH', '/mnt/music/artists')
try:
    os.makedirs(artist_images_path, exist_ok=True)
    logger.info(f'Mounting artist images from {artist_images_path} at /media/artist-images')
    app.mount('/media/artist-images', StaticFiles(directory=artist_images_path), name='artist-images')
except Exception as e:
    logger.error(f'Could not setup artist images storage at {artist_images_path}: {e}')
serve_frontend(app)
if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)