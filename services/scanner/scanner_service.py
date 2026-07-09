import os
import time
import hashlib
import logging
import argparse
import pymysql
from services.common.settings import Settings
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.api import start_api_server
from services.scanner.Song.ReadonlySong import ReadonlySong
from services.tagger.Song.BaseSong import ExtensionNotSupportedException

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ScannerService')

class ScannerService:
    def __init__(self):
        self.settings = Settings()
        self.db_connector = DatabaseConnector()
        self.music_path = self.settings.music_folder_path
        if not self.music_path:
            logger.error("music_folder_path not configured in settings/env")
        start_api_server()

    def get_db(self):
        return self.db_connector.connect()

    def get_file_hash(self, path):
        return hashlib.sha256(path.encode('utf-8')).hexdigest()

    def scan(self, force=False):
        if not self.music_path or not os.path.exists(self.music_path):
            logger.error(f"Music path does not exist: {self.music_path}")
            return

        logger.info(f"Starting scan of {self.music_path}")
        conn = self.get_db()
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
                        conn.commit()
        conn.commit()
        return count

    def _process_file_safe(self, conn, full_path, force):
        try:
            return self.process_file(conn, full_path, force)
        except ExtensionNotSupportedException:
            pass
        except Exception as e:
            logger.error(f"Error processing {full_path}: {e}")
        return False

    def process_file(self, conn, path, force=False): # pylint: disable=too-many-locals
        path_hash = self.get_file_hash(path)
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)

        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Check if file exists in DB
            cursor.execute("SELECT id, file_mtime, file_size FROM library_media_files WHERE file_path_hash = %s", (path_hash,))
            record = cursor.fetchone()

            if not force and record and record['file_mtime'] == mtime and record['file_size'] == size:
                # File unchanged
                return False

            # Need to process file
            try:
                song = ReadonlySong(path)
            except Exception:
                # Could be broken file or unsupported
                return False

            # 1. Get/Create Artists
            artist_names = song.library_artists()
            artist_ids = []
            for name in artist_names:
                if not name:
                    continue
                cursor.execute("INSERT IGNORE INTO library_artists (name) VALUES (%s)", (name,))
                cursor.execute("SELECT id FROM library_artists WHERE name = %s", (name,))
                artist_ids.append(cursor.fetchone()['id'])

            # 2. Get/Create Label
            label_name = song.publisher()
            label_id = None
            if label_name:
                cursor.execute("INSERT IGNORE INTO library_labels (name) VALUES (%s)", (label_name,))
                cursor.execute("SELECT id FROM library_labels WHERE name = %s", (label_name,))
                label_id = cursor.fetchone()['id']

            # 3. Create/Update Track
            title = song.title()
            duration = song.length()
            primary_artist_id = artist_ids[0] if artist_ids else None

            # Use a unique identifier for the track. For now title + duration + primary artist
            track_uid = hashlib.sha256(f"{title}-{duration}-{primary_artist_id}".encode('utf-8')).hexdigest()

            cursor.execute("""
                INSERT INTO library_tracks (track_uid, title, duration_secs, primary_artist_id)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE title=%s, duration_secs=%s, primary_artist_id=%s
            """, (track_uid, title, duration, primary_artist_id, title, duration, primary_artist_id))

            cursor.execute("SELECT id FROM library_tracks WHERE track_uid = %s", (track_uid,))
            track_id = cursor.fetchone()['id']

            # 4. Link Track Artists
            cursor.execute("DELETE FROM library_track_artists WHERE track_id = %s", (track_id,))
            for i, a_id in enumerate(artist_ids):
                role = 'primary' if i == 0 else 'featuring'
                cursor.execute(
                    "INSERT IGNORE INTO library_track_artists (track_id, artist_id, role, position) VALUES (%s, %s, %s, %s)",
                    (track_id, a_id, role, i)
                )

            # 5. Link Track Label
            if label_id:
                cursor.execute("INSERT IGNORE INTO library_track_labels (track_id, label_id) VALUES (%s, %s)", (track_id, label_id))

            # 6. Update Media File
            cursor.execute("""
                INSERT INTO library_media_files (file_path, file_path_hash, file_mtime, file_size, track_id, duration_secs)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE file_mtime=%s, file_size=%s, track_id=%s, duration_secs=%s
            """, (path, path_hash, mtime, size, track_id, duration, mtime, size, track_id, duration))

            return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Music Management Database Scanner')
    parser.add_argument('--force', action='store_true', help='Force re-scanning of all files')
    parser.add_argument('--repeat', action='store_true', help='Keep running in a loop')
    parser.add_argument('--sleeptime', type=int, default=3600, help='Time to sleep between scans (seconds)')

    args = parser.parse_args()
    scanner = ScannerService()

    while True:
        scanner.scan(force=args.force)
        if not args.repeat:
            break
        logger.info(f"Sleeping for {args.sleeptime} seconds...")
        time.sleep(args.sleeptime)
