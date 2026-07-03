import os
import sys
from pathlib import Path
from tqdm import tqdm
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from analyzer import TrackAnalyzer

def update_metadata():
    load_dotenv()
    
    analyzer = TrackAnalyzer()
    if analyzer.engine is None:
        print("Geen database verbinding.")
        return

    # Haal alle library_tracks op die we al geanalyseerd hebben
    # We proberen ook het file_path en internal_track_id op te halen als die er al staan
    query = "SELECT track_id, file_path, internal_track_id FROM library_track_audio_features"
    try:
        with analyzer.engine.connect() as conn:
            result = conn.execute(text(query))
            library_tracks = [dict(row._mapping) for row in result]
    except Exception as e:
        if "Unknown column 'file_path'" in str(e) or "Unknown column 'internal_track_id'" in str(e):
            print("\nFOUT: De database tabel 'library_track_audio_features' is verouderd.")
            print("Draai eerst het volgende script om de database bij te werken:")
            print("  python fix_db_schema.py\n")
            return
        else:
            print(f"Database fout: {e}")
            return

    if not library_tracks:
        print("Geen library_tracks gevonden in de database om te updaten.")
        return

    print(f"Update metadata voor {len(library_tracks)} library_tracks...")
    
    count = 0
    for track in tqdm(library_tracks):
        track_id = track['track_id']
        file_path = track.get('file_path')
        
        # Als we geen pad hebben, probeer het te vinden via library_media_files
        if not file_path:
            with analyzer.engine.connect() as conn:
                res = conn.execute(
                    text("SELECT file_path FROM library_media_files WHERE file_path_hash = :hash"),
                    {"hash": track_id}
                ).fetchone()
                if res:
                    file_path = res[0]
        
        if not file_path or not os.path.exists(file_path):
            continue

        try:
            metadata = analyzer.extract_metadata(file_path)
            
            # Update metadata en zorg dat het pad nu ook wordt opgeslagen
            update_query = """
                UPDATE library_track_audio_features 
                SET artist_name = :artist,
                    label_name = :label,
                    release_year = :year,
                    bpm_tag = :bpm,
                    genre_tag = :genre,
                    source_platform = :platform,
                    file_path = :path
                WHERE track_id = :tid
            """
            with analyzer.engine.begin() as conn:
                conn.execute(text(update_query), {
                    'artist': metadata.get('artist_name'),
                    'label': metadata.get('label_name'),
                    'year': metadata.get('release_year'),
                    'bpm': metadata.get('bpm_tag'),
                    'genre': metadata.get('genre_tag'),
                    'platform': metadata.get('source_platform'),
                    'path': file_path,
                    'tid': track_id
                })
            count += 1
        except Exception as e:
            print(f"Fout bij updaten van {track_id}: {e}")

    print(f"Klaar! Metadata bijgewerkt voor {count} library_tracks.")

if __name__ == "__main__":
    # Dit script is een hulpmiddel om bestaande data te verrijken
    # Het vereist dat track_id in de DB overeenkomt met een vindbaar pad
    update_metadata()
