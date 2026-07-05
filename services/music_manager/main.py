from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("music-manager")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Music Manager API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routers (we will create these)
from services.music_manager.routers import users, scrobbler, rating, stats, management, artist_images

app.include_router(users.router)
app.include_router(scrobbler.router)
app.include_router(rating.router)
app.include_router(stats.router)
app.include_router(management.router)
app.include_router(artist_images.router)

@app.on_event("startup")
def startup_event():
    from services.music_manager.database import get_db_connection
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Initialize all modules
                users.init_db(cursor)
                scrobbler.init_db(cursor)
                rating.init_db(cursor)
                # stats doesn't have its own tables usually, it reads from others
                management.init_db(cursor)
            conn.commit()
            print("Music Manager: Database initialized")
        finally:
            conn.close()
    
    # Start LMS sync in background
    from services.music_manager.routers.users import run_lms_db_sync
    import threading
    threading.Thread(target=run_lms_db_sync, daemon=True).start()

@app.get("/health")
def health():
    return {"status": "ok", "service": "music-manager"}

# Serve Frontend
def serve_frontend(app: FastAPI):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_path = os.path.join(base_dir, "frontend", "dist")
    
    logger.info(f"Checking for frontend at: {frontend_path}")
    logger.info(f"Current Working Directory: {os.getcwd()}")
    logger.info(f"__file__: {__file__}")
    
    if os.path.exists(frontend_path):
        logger.info(f"Frontend found at {frontend_path}. Mounting at /")
        app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
    else:
        logger.warning(f"Frontend build directory not found at {frontend_path}; static files will not be served.")
        # Check parent directory
        parent = os.path.dirname(frontend_path)
        if os.path.exists(parent):
            logger.info(f"Parent directory {parent} exists. Contents: {os.listdir(parent)}")
        
        @app.get("/", response_class=HTMLResponse)
        def root_fallback():
            return "<h1>Music Manager</h1><p>Frontend not found. API is active.</p>"

serve_frontend(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
