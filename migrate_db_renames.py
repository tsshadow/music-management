import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

RENAMES = {
    "library_tracks": "library_tracks",
    "library_media_files": "library_media_files",
    "library_track_audio_features": "library_track_audio_features",
    "library_track_ml_labels": "library_track_ml_labels",
    "library_track_ml_predictions": "library_track_ml_predictions",
    "library_artists": "library_artists",
    "library_labels": "library_labels",
    "library_track_artists": "library_track_artists",
    "library_track_genres": "library_track_genres",
    "library_track_labels": "library_track_labels",
    "library_tagged_files": "library_tagged_files",
    "library_broken_songs": "library_broken_songs",
    "library_broken_song_artist_lookup": "library_broken_song_artist_lookup",
    "library_artist_aliases": "library_artist_aliases",
    "rules_genres": "rules_genres",
    "rules_artist_genre": "rules_artist_genre",
    "rules_label_genre": "rules_label_genre",
    "rules_subgenre_hierarchy": "rules_subgenre_hierarchy",
    "rules_ignored_artists": "rules_ignored_artists",
    "rules_ignored_genres": "rules_ignored_genres",
    "rules_catid_label": "rules_catid_label",
    "rules_festival_data": "rules_festival_data",
    "rules_genre_backlog": "rules_genre_backlog",
    "rules_genres_new": "rules_genres_new",
    "downloads_soundcloud_accounts": "downloads_soundcloud_accounts",
    "downloads_youtube_accounts": "downloads_youtube_accounts",
    "downloads_soundcloud_archive": "downloads_soundcloud_archive",
    "downloads_youtube_archive": "downloads_youtube_archive",
    "downloads_soundcloud_queue": "downloads_soundcloud_queue",
    "downloads_youtube_queue": "downloads_youtube_queue",
}

def rename_tables():
    host = os.getenv("DB_HOST", "192.168.1.27")
    port = os.getenv("DB_PORT", "3306")
    user = "root"
    password = "Paced-Splendid-Deuce-Negotiate3-Sappy-Define"
    db_name = os.getenv("DB_DB", "music-management")
    
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(url)
    
    with engine.connect() as conn:
        print("Uitzetten van foreign key checks...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        
        for old_name, new_name in RENAMES.items():
            print(f"Hernoemen van {old_name} naar {new_name}...")
            try:
                conn.execute(text(f"RENAME TABLE `{old_name}` TO `{new_name}`"))
            except Exception as e:
                print(f"Fout bij hernoemen van {old_name}: {e}")
        
        print("Aanzetten van foreign key checks...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
        print("Klaar!")

if __name__ == "__main__":
    rename_tables()
