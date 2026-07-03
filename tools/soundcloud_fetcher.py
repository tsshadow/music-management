import logging
import os
import subprocess
import json
import sys
import time

# Ensure project root is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.settings import Settings
from services.tagger.Song.SoundcloudSong import SoundcloudSong
from services.common.Helpers.Cache import databaseHelpers
from services.common.Helpers.FilterTableHelper import FilterTableHelper

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_tracks_to_process():
    """Fetch all SoundCloud tracks from the archive."""
    try:
        conn = DatabaseConnector().connect()
        with conn.cursor() as cursor:
            # We fetch url and filename. Filename contains the local path.
            cursor.execute("SELECT id, url, filename FROM downloads_soundcloud_archive")
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Failed to fetch tracks from archive: {e}")
        return []

def fetch_metadata(url):
    """Fetch metadata from SoundCloud using yt-dlp binary."""
    try:
        # Using the same approach as SoundcloudSongProcessor
        result = subprocess.run(['yt-dlp', '--dump-single-json', '--no-playlist', url], 
                               capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logging.error(f"yt-dlp failed for {url}: {e.stderr}")
    except Exception as e:
        logging.error(f"Unexpected error fetching metadata for {url}: {e}")
    return None

def main():
    logging.info("Starting SoundCloud genre fetcher...")
    
    tracks = get_tracks_to_process()
    if not tracks:
        logging.info("No tracks found in archive to process.")
        return

    logging.info(f"Found {len(tracks)} tracks to check.")

    # Get the genre helper from cache or create one
    genre_helper = databaseHelpers.get('rules_genres')
    if not genre_helper:
        logging.warning("Genre helper not found in cache, creating new instance.")
        genre_helper = FilterTableHelper('rules_genres', 'name', 'corrected_genre')
    
    updated_count = 0
    skipped_count = 0
    not_found_count = 0
    
    for track_id, url, filename in tracks:
        # Debug path if it doesn't exist
        if filename and not os.path.exists(filename):
             logging.debug(f"Path does not exist: {filename}")
             # Check if we can find it by replacing /mnt/music with the music_folder_path setting
             settings_path = Settings().music_folder_path
             if settings_path and filename.startswith('/mnt/music') and settings_path != '/mnt/music':
                 alternative_path = filename.replace('/mnt/music', settings_path, 1)
                 if os.path.exists(alternative_path):
                     logging.info(f"Found alternative path: {alternative_path}")
                     filename = alternative_path

        if not filename or not os.path.exists(filename):
            logging.warning(f"File not found or path empty: {filename} (ID: {track_id})")
            not_found_count += 1
            continue
            
        logging.info(f"Processing: {url}")
        metadata = fetch_metadata(url)
        
        # Respect SoundCloud's rate limits
        time.sleep(60)
        
        if not metadata:
            skipped_count += 1
            continue
            
        sc_genre = metadata.get('genre')
        logging.info(f"Got genre: '{sc_genre}'")
        if not sc_genre:
            skipped_count += 1
            continue
            
        # Normalize genre (SoundCloud often uses hashtags)
        if sc_genre.startswith('#'):
            sc_genre = sc_genre[1:]
            metadata['genre'] = sc_genre
            logging.info(f"Normalized to: '{sc_genre}'")
            
        # Check if the genre is allowed/validated
        allowed_genre = genre_helper.get_corrected_or_exists(sc_genre)
        
        if allowed_genre:
            logging.info(f"Valid: '{allowed_genre}'")
            try:
                song = SoundcloudSong(filename, metadata)
                
                # Check if genre already exists in file to avoid redundant writes
                if allowed_genre in song.rules_genres():
                    logging.info(f"Already exists: '{allowed_genre}'")
                    skipped_count += 1
                    continue

                logging.info(f"Assigning: '{allowed_genre}'")
                song.parse()
                song.save_file()
                
                logging.info(f"Successfully updated: {os.path.basename(filename)}")
                updated_count += 1
            except Exception as e:
                logging.error(f"Failed to update {os.path.basename(filename)}: {e}")
                skipped_count += 1
        else:
            logging.info(f"Not valid (not in rules_genres): '{sc_genre}'")
            skipped_count += 1

    logging.info("--- Processing Finished ---")
    logging.info(f"Total tracks checked: {len(tracks)}")
    logging.info(f"Updated:             {updated_count}")
    logging.info(f"Skipped/Unchanged:   {skipped_count}")
    logging.info(f"Files not found:     {not_found_count}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Process interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logging.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
