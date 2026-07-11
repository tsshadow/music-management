import os
import time
import hashlib
import logging
import threading
from pathlib import Path
import pymysql
from fastapi import APIRouter, BackgroundTasks, Query, HTTPException
from services.common.settings import Settings
from services.music_manager.database import get_db_connection
from services.scanner.Song.ReadonlySong import ReadonlySong
from services.tagger.Song.BaseSong import ExtensionNotSupportedException

router = APIRouter(prefix="/api/scanner", tags=["scanner"])
logger = logging.getLogger("music-manager.scanner")

class ScannerManager:
    def __init__(self):
        self.settings = Settings()
        self.music_path = self.settings.music_folder_path
        self._lock = threading.Lock()

    def get_file_hash(self, path):
        return hashlib.sha256(path.encode('utf-8')).hexdigest()

    def scan_single(self, path: str | Path, force=False):
        with self._lock:
            logger.info("Processing single file scan request: %s", path)
            conn = get_db_connection()
            if not conn:
                logger.error("Could not get database connection")
                return False
            try:
                full_path = str(Path(path).resolve())
                if not os.path.exists(full_path):
                    logger.error(f"File not found for scanning: {full_path}")
                    return False
                
                result = self._process_file_safe(conn, full_path, force=force)
                # Autocommit is on in the pool, but we commit just in case or if it was changed
                # conn.commit() 
                return result
            finally:
                conn.close()

    def run_full(self, force=False):
        if not self.music_path or not os.path.exists(self.music_path):
            logger.error(f"Music path does not exist: {self.music_path}")
            return

        if self._lock.locked():
            logger.warning("Scan already in progress, skipping full run")
            return

        with self._lock:
            logger.info(f"Starting scan of {self.music_path} (force={force})")
            conn = get_db_connection()
            if not conn:
                logger.error("Could not get database connection")
                return
            try:
                count = self._scan_recursive(conn, force)
                logger.info(f"Scan completed. Total files processed/updated: {count}")
            finally:
                conn.close()

    def _scan_recursive(self, conn, force):
        count = 0
        for root, _, files in os.walk(self.music_path):
            for file in files:
                if file.startswith('.'):
                    continue

                full_path = os.path.join(root, file)
                if self._process_file_safe(conn, full_path, force):
                    count += 1
                    if count % 100 == 0:
                        logger.info(f"Processed {count} files...")
        return count

    def _process_file_safe(self, conn, full_path, force):
        try:
            return self.process_file(conn, full_path, force)
        except ExtensionNotSupportedException:
            pass
        except Exception as e:
            logger.error(f"Error processing {full_path}: {e}")
        return False

    def process_file(self, conn, path, force=False):
        path_hash = self.get_file_hash(path)
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)

        with conn.cursor() as cursor:
            # Check if file exists in DB
            cursor.execute("SELECT id, file_mtime, file_size FROM library_media_files WHERE file_path_hash = %s", (path_hash,))
            record = cursor.fetchone()

            if not force and record and record['file_mtime'] == mtime and record['file_size'] == size:
                return False

            try:
                song = ReadonlySong(path)
            except Exception:
                return False

            artist_names = song.library_artists()
            artist_ids = []
            for name in artist_names:
                if not name:
                    continue
                cursor.execute("INSERT IGNORE INTO library_artists (name) VALUES (%s)", (name,))
                cursor.execute("SELECT id FROM library_artists WHERE name = %s", (name,))
                artist_ids.append(cursor.fetchone()['id'])

            label_name = song.publisher()
            label_id = None
            if label_name:
                cursor.execute("INSERT IGNORE INTO library_labels (name) VALUES (%s)", (label_name,))
                cursor.execute("SELECT id FROM library_labels WHERE name = %s", (label_name,))
                label_id = cursor.fetchone()['id']

            title = song.title()
            duration = song.length()
            primary_artist_id = artist_ids[0] if artist_ids else None
            track_uid = hashlib.sha256(f"{title}-{duration}-{primary_artist_id}".encode('utf-8')).hexdigest()

            cursor.execute("""
                INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE title=%s, duration_secs=%s, primary_artist_id=%s
            """, (track_uid, title, duration, primary_artist_id, title, duration, primary_artist_id))

            cursor.execute("SELECT id FROM library_tracks WHERE track_uid = %s", (track_uid,))
            track_id = cursor.fetchone()['id']

            cursor.execute("DELETE FROM library_track_artists WHERE track_id = %s", (track_id,))
            for i, a_id in enumerate(artist_ids):
                role = 'primary' if i == 0 else 'featuring'
                cursor.execute(
                    "INSERT IGNORE INTO library_track_artists (track_id, artist_id, role, position) VALUES (%s, %s, %s, %s)",
                    (track_id, a_id, role, i)
                )

            if label_id:
                cursor.execute("INSERT IGNORE INTO library_track_labels (track_id, label_id) VALUES (%s, %s)", (track_id, label_id))

            cursor.execute("""
                INSERT INTO library_media_files (file_path, file_path_hash, file_mtime, file_size, track_id, duration_secs)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE file_mtime=%s, file_size=%s, track_id=%s, duration_secs=%s
            """, (path, path_hash, mtime, size, track_id, duration, mtime, size, track_id, duration))

            return True

scanner_manager = ScannerManager()

@router.get("/health")
async def health():
    return {"status": "OK", "busy": scanner_manager._lock.locked()}

@router.post("/scan/all")
async def api_scan_all(background_tasks: BackgroundTasks, force: bool = False):
    if scanner_manager._lock.locked():
        raise HTTPException(status_code=409, detail="A scan operation is already in progress")
    background_tasks.add_task(scanner_manager.run_full, force=force)
    return {"message": "Full library scan started in background"}

@router.post("/scan/file")
async def api_scan_file(path: str = Query(...), force: bool = False):
    scanner_manager.scan_single(path, force=force)
    return {"message": f"Scan for {path} completed"}

def run_scanner_loop(sleeptime: int = 3600):
    logger.info("Starting background scanner loop with sleeptime %d", sleeptime)
    # Initial scan on startup
    scanner_manager.run_full()
    while True:
        time.sleep(sleeptime)
        scanner_manager.run_full()
