import logging
import os
import subprocess
import json
import sys
import time

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.common.Helpers.Cache import databaseHelpers
from services.common.Helpers.FilterTableHelper import FilterTableHelper

# Setup logging to stdout
import sys
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(message)s')
logger = logging.getLogger('trace-fetcher')
logger.info("Script is starting...")

def fetch_metadata(url):
    try:
        result = subprocess.run(['yt-dlp', '--dump-single-json', '--no-playlist', url], 
                               capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except Exception as e:
        logger.error(f"  [!] yt-dlp error for {url}")
        return None

def trace_test():
    logger.info("=== Start Trace Test ===")
    
    try:
        conn = DatabaseConnector().connect()
        with conn.cursor() as cursor:
            # Pak 5 recente tracks om te testen
            cursor.execute("SELECT id, url, filename FROM downloads_soundcloud_archive ORDER BY id DESC LIMIT 5")
            tracks = cursor.fetchall()
    except Exception as e:
        logger.error(f"Database error: {e}")
        return

    if not tracks:
        logger.info("Geen tracks gevonden in downloads_soundcloud_archive.")
        return

    # Genre helper laden
    genre_helper = FilterTableHelper('rules_genres', 'name', 'corrected_genre')
    
    for track_id, url, filename in tracks:
        logger.info(f"\n--- Processing Track ID: {track_id} ---")
        logger.info(f"URL: {url}")
        logger.info(f"File path: {filename}")
        
        # 1. Bestandscontrole
        if not filename or not os.path.exists(filename):
            logger.info(f"  [RESULT] Bestand niet gevonden op schijf: {filename}")
            continue
            
        # 2. Metadata ophalen
        logger.info("  [STEP] Metadata ophalen via yt-dlp...")
        metadata = fetch_metadata(url)
        
        if not metadata:
            logger.info("  [RESULT] Geen metadata kunnen ophalen van SoundCloud.")
            continue
            
        sc_genre = metadata.get('genre')
        logger.info(f"  [DATA] SoundCloud Genre gevonden: '{sc_genre}'")
        
        if not sc_genre:
            logger.info("  [RESULT] Geen genre tag aanwezig op SoundCloud.")
            continue
            
        # 3. Normalisatie
        orig_genre = sc_genre
        if sc_genre.startswith('#'):
            sc_genre = sc_genre[1:]
            logger.info(f"  [DATA] Genre genormaliseerd (hashtag verwijderd): '{sc_genre}'")
            
        # 4. Database check
        logger.info(f"  [STEP] Controleren of '{sc_genre}' in rules_genres staat...")
        allowed_genre = genre_helper.get_corrected_or_exists(sc_genre)
        
        if allowed_genre:
            logger.info(f"  [MATCH] Genre '{sc_genre}' IS toegestaan (gematcht op: '{allowed_genre}').")
            
            # 5. Song object laden en simuleren
            try:
                song = SoundcloudSong(filename, metadata)
                current_genres = song.rules_genres()
                logger.info(f"  [DATA] Huidige genres in bestand: {current_genres}")
                
                # Check of het genre al in het bestand zit
                if allowed_genre in current_genres:
                    logger.info(f"  [RESULT] Niks te schrijven: genre '{allowed_genre}' zit al in de file tags.")
                else:
                    logger.info(f"  [RESULT] ZOU SCHRIJVEN: '{allowed_genre}' toevoegen aan bestand.")
            except Exception as e:
                logger.info(f"  [ERROR] Fout bij laden song object: {e}")
        else:
            logger.info(f"  [RESULT] NIKS SCHRIJVEN: Genre '{sc_genre}' staat niet in rules_genres.")
            
        # Kleine delay om SoundCloud te pleasen
        time.sleep(1)

if __name__ == "__main__":
    trace_test()
