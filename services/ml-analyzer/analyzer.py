import os
import sys
import librosa
import numpy as np
import torch
import torchaudio
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

class TrackAnalyzer:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")
        self.engine = self._get_db_engine()

    def _get_db_engine(self):
        host = os.getenv("DB_HOST", "db")
        port = os.getenv("DB_PORT", "3306")
        user = os.getenv("DB_USER", "music-management")
        password = os.getenv("DB_PASS", "")
        db_name = os.getenv("DB_DB", "music-management")
        
        if not password:
            return None
            
        url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
        return create_engine(url)

    def load_audio(self, file_path):
        """Laad audio bestand in."""
        print(f"Loading track: {file_path}")
        try:
            # Librosa voor basis analyse
            y, sr = librosa.load(file_path, sr=None)
            return y, sr
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return None, None

    def extract_basic_features(self, y, sr):
        """Extraheer basis muziekelementen."""
        if y is None:
            return None

        print("Extracting features...")
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        
        # Spectrale kenmerken
        spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        
        # Gemiddelde loudness (RMS)
        rms = librosa.feature.rms(y=y)[0]
        
        features = {
            "tempo": float(np.mean(tempo)),
            "duration": float(librosa.get_duration(y=y, sr=sr)),
            "mean_spectral_centroid": float(np.mean(spectral_centroids)),
            "mean_rms": float(np.mean(rms))
        }
        
        return features

    def save_features(self, track_id, features):
        """Sla de geëxtraheerde features op in de database."""
        if self.engine is None:
            print("Geen database verbinding beschikbaar om features op te slaan.")
            return False

        from sqlalchemy import Table, MetaData, Column, Float, String
        from sqlalchemy.dialects.mysql import insert

        metadata = MetaData()
        # Handmatige definitie voor robuustheid (overeenkomstig met db_init.sql)
        track_audio_features = Table(
            'track_audio_features', metadata,
            Column('track_id', String(255), primary_key=True),
            Column('tempo', Float),
            Column('duration', Float),
            Column('mean_spectral_centroid', Float),
            Column('mean_rms', Float),
            extend_existing=True
        )

        with self.engine.begin() as conn:
            stmt = insert(track_audio_features).values(
                track_id=track_id,
                tempo=features['tempo'],
                duration=features['duration'],
                mean_spectral_centroid=features['mean_spectral_centroid'],
                mean_rms=features['mean_rms']
            )
            # Update bij duplicate key (track_id)
            on_duplicate_stmt = stmt.on_duplicate_key_update(
                tempo=stmt.inserted.tempo,
                duration=stmt.inserted.duration,
                mean_spectral_centroid=stmt.inserted.mean_spectral_centroid,
                mean_rms=stmt.inserted.mean_rms
            )
            conn.execute(on_duplicate_stmt)
            
        print(f"Features opgeslagen voor track_id: {track_id}")
        return True

    def get_track_id(self, file_path):
        """Probeer een track_id te vinden voor het gegeven bestandspad."""
        # Voor nu gebruiken we een hash van het pad als we geen match vinden in de media_library
        # Maar we kunnen proberen in de 'media_files' tabel te kijken als die bestaat
        import hashlib
        path_hash = hashlib.sha256(file_path.encode()).hexdigest()
        
        if self.engine is None:
            return path_hash

        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                # Probeer track_id uit media_files te halen
                result = conn.execute(
                    text("SELECT track_id FROM media_files WHERE file_path = :path OR file_path_hash = :hash"),
                    {"path": file_path, "hash": path_hash}
                ).fetchone()
                
                if result and result[0]:
                    return str(result[0])
        except Exception as e:
            print(f"Fout bij opzoeken track_id: {e}")
            
        return path_hash

    def analyze_folder(self, folder_path, save=False):
        """Analyseer alle ondersteunde audiobestanden in een map."""
        supported_extensions = ('.mp3', '.flac', '.wav', '.m4a', '.ogg')
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(supported_extensions):
                    file_path = os.path.join(root, file)
                    print(f"\n--- Analysing: {file} ---")
                    self.analyze_track(file_path, save=save)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python analyzer.py <path_to_audio_file_or_folder> [--save]")
        sys.exit(1)

    path = sys.argv[1]
    save_to_db = "--save" in sys.argv
    
    # Zoek het argument dat het pad is
    for arg in sys.argv[1:]:
        if arg != "--save":
            path = arg
            break

    analyzer = TrackAnalyzer()
    
    if os.path.isdir(path):
        analyzer.analyze_folder(path, save=save_to_db)
    else:
        results = analyzer.analyze_track(path, save=save_to_db)
        if results:
            print("\nAnalyse resultaten:")
            for k, v in results.items():
                print(f"  {k}: {v}")
        else:
            print("Analyse mislukt.")
