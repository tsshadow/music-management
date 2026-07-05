from fastapi import APIRouter, HTTPException, BackgroundTasks, Header
from fastapi.responses import FileResponse
import os
import sqlite3
from services.music_manager.database import get_db_connection
from typing import Optional

router = APIRouter(prefix="/artists", tags=["artists"])

STORAGE_PATH = os.getenv("STORAGE_PATH", "/music/artists")

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

def trigger_fetch(artist_name: str):
    try:
        from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher
        conn = get_db_connection()
        if not conn: return
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

def sync_artist_images_to_lms(muma_conn, lms_conn):
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
