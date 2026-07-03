import os
import re

RENAMES = {
    "library_track_audio_features": "library_track_audio_features",
    "library_track_ml_labels": "library_track_ml_labels",
    "library_track_ml_predictions": "library_track_ml_predictions",
    "library_track_artists": "library_track_artists",
    "library_track_genres": "library_track_genres",
    "library_track_labels": "library_track_labels",
    "library_broken_song_artist_lookup": "library_broken_song_artist_lookup",
    "library_artist_aliases": "library_artist_aliases",
    "library_media_files": "library_media_files",
    "library_tagged_files": "library_tagged_files",
    "library_broken_songs": "library_broken_songs",
    "library_tracks": "library_tracks",
    "library_artists": "library_artists",
    "library_labels": "library_labels",
    "rules_artist_genre": "rules_artist_genre",
    "rules_label_genre": "rules_label_genre",
    "rules_subgenre_hierarchy": "rules_subgenre_hierarchy",
    "rules_ignored_artists": "rules_ignored_artists",
    "rules_ignored_genres": "rules_ignored_genres",
    "rules_catid_label": "rules_catid_label",
    "rules_festival_data": "rules_festival_data",
    "rules_genre_backlog": "rules_genre_backlog",
    "rules_genres_new": "rules_genres_new",
    "rules_genres": "rules_genres",
    "downloads_soundcloud_accounts": "downloads_soundcloud_accounts",
    "downloads_youtube_accounts": "downloads_youtube_accounts",
    "downloads_soundcloud_archive": "downloads_soundcloud_archive",
    "downloads_youtube_archive": "downloads_youtube_archive",
    "downloads_soundcloud_queue": "downloads_soundcloud_queue",
    "downloads_youtube_queue": "downloads_youtube_queue",
}

# We sorteren op lengte van de key (langste eerst) om deel-vervangingen te voorkomen
SORTED_KEYS = sorted(RENAMES.keys(), key=len, reverse=True)

EXTENSIONS = ('.py', '.sql', '.md', '.txt', '.sh', '.yml', '.yaml')
EXCLUDE_DIRS = ('.git', '__pycache__', '.venv', 'node_modules', 'backup')

def replace_in_file(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    original_content = content
    
    for key in SORTED_KEYS:
        # We gebruiken regex om alleen hele woorden te vervangen of woorden in quotes
        # om te voorkomen dat we per ongeluk variabelen hernoemen die toevallig zo heten
        # MAAR in SQL queries zijn het vaak gewoon woorden.
        # We proberen een balans te vinden.
        pattern = r'\b' + re.escape(key) + r'\b'
        content = re.sub(pattern, RENAMES[key], content)
        
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    count = 0
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(EXTENSIONS):
                path = os.path.join(root, file)
                if replace_in_file(path):
                    print(f"Aangepast: {path}")
                    count += 1
    print(f"Klaar! {count} bestanden aangepast.")

if __name__ == "__main__":
    main()
