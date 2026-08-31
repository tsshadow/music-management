import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def check():
    # Geen defaults voor host of credentials: hier stond het root-wachtwoord van
    # de productiedatabase als platte string, met het productie-IP ernaast. Dat
    # zit nog in de git-historie, dus het hoort geroteerd te zijn.
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")
    db_name = os.getenv("DB_DB")
    missing = [name for name, value in
               (("DB_HOST", host), ("DB_USER", user),
                ("DB_PASS", password), ("DB_DB", db_name)) if not value]
    if missing:
        raise SystemExit(f"ontbrekende omgevingsvariabelen: {', '.join(missing)}")
    
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        print("--- Integriteits Check ---")
        
        # 1. Koppeling Media Files -> Tracks
        linked_media = conn.execute(text("SELECT count(*) FROM library_media_files WHERE track_id IS NOT NULL")).fetchone()[0]
        total_media = conn.execute(text("SELECT count(*) FROM library_media_files")).fetchone()[0]
        print(f"Media files gekoppeld aan tracks: {linked_media} van de {total_media}")
        
        # 2. Koppeling Audio Features -> Tracks
        linked_features = conn.execute(text("SELECT count(*) FROM library_track_audio_features WHERE internal_track_id IS NOT NULL")).fetchone()[0]
        total_features = conn.execute(text("SELECT count(*) FROM library_track_audio_features")).fetchone()[0]
        print(f"Audio features gekoppeld aan tracks: {linked_features} van de {total_features}")
        
        # 3. Zijn er tracks zonder media files?
        tracks_no_media = conn.execute(text("SELECT count(*) FROM library_tracks t WHERE NOT EXISTS (SELECT 1 FROM library_media_files m WHERE m.track_id = t.id)")).fetchone()[0]
        total_tracks = conn.execute(text("SELECT count(*) FROM library_tracks")).fetchone()[0]
        print(f"Tracks zonder media files: {tracks_no_media} van de {total_tracks}")

if __name__ == "__main__":
    check()
