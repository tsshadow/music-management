import os
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Header, Depends
from fastapi.responses import FileResponse
from services.music_manager.database import get_db_connection

router = APIRouter(prefix="/api/artists", tags=["artists"])

# Global state for background tasks progress
fetch_progress = {
    "active": False,
    "total": 0,
    "current": 0,
    "last_artist": None,
    "status": "idle"
}

API_KEY = os.getenv("API_KEY") or os.getenv("MUMA_API_KEY") or "453ecd33-3cb2-4ca4-a531-1677330bbaee"

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")
    if API_KEY and x_api_key == API_KEY:
        return {"type": "system"}

    from services.music_manager.routers.users import verify_token # pylint: disable=import-outside-toplevel
    try:
        res = verify_token(x_api_key)
        if res.get("status") == "ok":
            return res
    except Exception: # pylint: disable=broad-except
        pass

    raise HTTPException(status_code=401, detail="Invalid API key")

STORAGE_PATH = os.getenv("STORAGE_PATH", "/music/artists")

def init_db(cursor):
    # library_artist_images table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS library_artist_images (
            id INT AUTO_INCREMENT PRIMARY KEY,
            artist_id INT NOT NULL,
            source VARCHAR(50),
            source_id VARCHAR(255),
            original_url TEXT,
            cached_path TEXT,
            public_path TEXT,
            width INT,
            height INT,
            mime_type VARCHAR(50),
            file_size INT,
            confidence INT DEFAULT 0,
            is_primary TINYINT(1) DEFAULT 0,
            created_at DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX (artist_id),
            INDEX (is_primary)
        )
    """)

    # artist_external_ids table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artist_external_ids (
            artist_id INT NOT NULL,
            source VARCHAR(50) NOT NULL,
            external_id VARCHAR(255) NOT NULL,
            created_at DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (artist_id, source)
        )
    """)

    # Alter library_artists to add image-related columns
    columns_to_add = [
        ("primary_image_id", "INT NULL"),
        ("image_updated_at", "DATETIME NULL"),
        ("image_status", "VARCHAR(50) NULL"),
        ("mbid", "VARCHAR(100) NULL")
    ]

    for col_name, col_type in columns_to_add:
        cursor.execute(f"SHOW COLUMNS FROM library_artists LIKE '{col_name}'")
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE library_artists ADD COLUMN {col_name} {col_type}")

@router.get("/search")
def search_artist_images(q: str = "", _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT a.id, a.name, a.primary_image_id, i.width, i.height, i.mime_type
                FROM library_artists a
                JOIN library_artist_images i ON a.primary_image_id = i.id
                WHERE a.name LIKE %s
                ORDER BY a.name
                LIMIT 100
            """, (f"%{q}%",))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get("/search-all")
def search_all_artists(q: str = "", _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT a.id, a.name, a.primary_image_id, i.width, i.height, i.mime_type, a.image_status
                FROM library_artists a
                LEFT JOIN library_artist_images i ON a.primary_image_id = i.id
                WHERE a.name LIKE %s
                ORDER BY a.name
                LIMIT 100
            """, (f"%{q}%",))
            return cursor.fetchall()
    finally:
        conn.close()

@router.get("/images/stats")
def get_artist_image_stats(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM library_artists")
            total = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) as with_image FROM library_artists WHERE primary_image_id IS NOT NULL")
            with_image = cursor.fetchone()['with_image']
            return {
                "total_artists": total,
                "artists_with_images": with_image,
                "artists_without_images": total - with_image
            }
    finally:
        conn.close()

@router.get("/fetch-progress")
def get_fetch_progress(_auth: dict = Depends(verify_api_key)):
    return fetch_progress

@router.get("/{artist_name}/image")
def get_artist_image(artist_name: str, background_tasks: BackgroundTasks):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT i.cached_path
                FROM library_artists a
                JOIN library_artist_images i ON a.primary_image_id = i.id
                WHERE a.name = %s
            """, (artist_name,))
            row = cursor.fetchone()

            if row and row['cached_path'] and os.path.exists(row['cached_path']):
                return FileResponse(row['cached_path'])

            # If not found, we could trigger a fetch here in background
            background_tasks.add_task(trigger_fetch, artist_name)

            raise HTTPException(status_code=404, detail="Artist image not found. Fetching triggered.")
    finally:
        conn.close()

@router.post("/fetch-missing")
@router.post("/fetch-images")
def fetch_missing_images(background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
    """
    Triggers a background task to fetch missing artist images for all artists.
    """
    if fetch_progress["active"]:
        return {"status": "error", "message": "Fetch already in progress"}

    background_tasks.add_task(run_fetch_missing)
    return {"status": "ok", "message": "Fetching missing artist images started in background"}

@router.post("/{artist_id}/fetch-image")
def fetch_artist_image_manual(artist_id: int, background_tasks: BackgroundTasks, _auth: dict = Depends(verify_api_key)):
    background_tasks.add_task(trigger_fetch_by_id, artist_id)
    return {"status": "ok", "message": f"Fetching image for artist ID {artist_id} started"}

def run_fetch_missing():
    try:
        from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher # pylint: disable=import-outside-toplevel
        conn = get_db_connection()
        if not conn:
            return
        try:
            fetcher = ArtistImageFetcher(db_conn=conn)
            # Find all artists without a primary image
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name
                    FROM library_artists
                    WHERE primary_image_id IS NULL
                    AND (image_status IS NULL OR image_status != 'failed')
                    ORDER BY name
                """)
                artists = cursor.fetchall()

                fetch_progress.update({
                    "active": True,
                    "total": len(artists),
                    "current": 0,
                    "last_artist": None,
                    "status": "running"
                })

                print(f"Starting background fetch for {len(artists)} artists")
                for i, artist in enumerate(artists):
                    fetch_progress["current"] = i + 1
                    fetch_progress["last_artist"] = artist['name']
                    try:
                        fetcher.fetch_for_artist(artist['id'], artist['name'])
                    except Exception as e:
                        print(f"Failed to fetch for {artist['name']}: {e}")

                fetch_progress.update({
                    "active": False,
                    "status": "completed"
                })
        finally:
            conn.close()
    except Exception as e:
        print(f"Global background fetch failed: {e}")
        fetch_progress.update({
            "active": False,
            "status": "failed"
        })

def trigger_fetch_by_id(artist_id: int):
    try:
        from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher # pylint: disable=import-outside-toplevel
        conn = get_db_connection()
        if not conn:
            return
        try:
            fetcher = ArtistImageFetcher(db_conn=conn)
            with conn.cursor() as cursor:
                cursor.execute("SELECT name FROM library_artists WHERE id = %s", (artist_id,))
                row = cursor.fetchone()
                if row:
                    fetcher.fetch_for_artist(artist_id, row['name'], force_refresh=True)
        finally:
            conn.close()
    except Exception as e:
        print(f"Background fetch failed for artist ID {artist_id}: {e}")

def trigger_fetch(artist_name: str):
    try:
        from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher # pylint: disable=import-outside-toplevel
        conn = get_db_connection()
        if not conn:
            return
        try:
            fetcher = ArtistImageFetcher(db_conn=conn)
            # Find artist ID
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM library_artists WHERE name = %s", (artist_name,))
                row = cursor.fetchone()
                if row:
                    fetcher.fetch_for_artist(row['id'], artist_name)
        finally:
            conn.close()
    except Exception as e:
        print(f"Background fetch failed for {artist_name}: {e}")

def sync_artist_images_to_lms(muma_conn, lms_conn): # pylint: disable=too-many-locals
    """
    Syncs primary artist images from MuMa MariaDB to LMS SQLite DB.
    """
    print("Syncing artist images to LMS...")
    try:
        with muma_conn.cursor() as muma_cursor:
            # 1. Get all primary artist images from MuMa
            muma_cursor.execute("""
                SELECT a.name as artist_name, i.cached_path, i.width, i.height, i.mime_type, i.file_size
                FROM library_artists a
                JOIN library_artist_images i ON a.primary_image_id = i.id
                WHERE i.cached_path IS NOT NULL
            """)
            images = muma_cursor.fetchall()

            lms_cursor = lms_conn.cursor()
            for img in images:
                artist_name = img['artist_name']
                abs_path = img['cached_path']

                # 2. Find artist in LMS
                lms_cursor.execute("SELECT id FROM artist WHERE name = ?", (artist_name,))
                artist_row = lms_cursor.fetchone()
                if not artist_row:
                    continue

                artist_id = artist_row[0]

                # 3. Ensure Image exists in LMS
                lms_cursor.execute("SELECT id FROM image WHERE absolute_file_path = ?", (abs_path,))
                image_row = lms_cursor.fetchone()

                image_id = None
                if image_row:
                    image_id = image_row[0]
                else:
                    stem = os.path.splitext(os.path.basename(abs_path))[0]
                    lms_cursor.execute("""
                        INSERT INTO image (version, absolute_file_path, stem, file_size, width, height, mime_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (1, abs_path, stem, img['file_size'], img['width'], img['height'], img['mime_type']))
                    image_id = lms_cursor.lastrowid

                # 4. Ensure Artwork exists in LMS
                lms_cursor.execute("SELECT id FROM artwork WHERE image_id = ?", (image_id,))
                artwork_row = lms_cursor.fetchone()

                artwork_id = None
                if artwork_row:
                    artwork_id = artwork_row[0]
                else:
                    lms_cursor.execute("INSERT INTO artwork (version, image_id) VALUES (?, ?)", (1, image_id))
                    artwork_id = lms_cursor.lastrowid

                # 5. Link Artwork to Artist in LMS
                lms_cursor.execute("UPDATE artist SET preferred_artwork_id = ? WHERE id = ?", (artwork_id, artist_id))

            lms_conn.commit()
            print(f"Synced {len(images)} artist images to LMS")
    except Exception as e:
        print(f"Failed to sync artist images to LMS: {e}")
