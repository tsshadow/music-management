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
            "tempo": float(tempo),
            "duration": float(librosa.get_duration(y=y, sr=sr)),
            "mean_spectral_centroid": float(np.mean(spectral_centroids)),
            "mean_rms": float(np.mean(rms))
        }
        
        return features

    def analyze_track(self, file_path):
        y, sr = self.load_audio(file_path)
        if y is not None:
            features = self.extract_basic_features(y, sr)
            return features
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python analyzer.py <path_to_audio_file>")
        sys.exit(1)

    file_path = sys.argv[1]
    analyzer = TrackAnalyzer()
    results = analyzer.analyze_track(file_path)
    
    if results:
        print("\nAnalyse resultaten:")
        for k, v in results.items():
            print(f"  {k}: {v}")
    else:
        print("Analyse mislukt.")
