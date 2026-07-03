import os
import sys
import joblib
import pandas as pd
import numpy as np
from sqlalchemy import text
from analyzer import TrackAnalyzer

class GenrePredictor:
    def __init__(self, model_path='models/genre_classifier.joblib', encoder_path='models/label_encoders.joblib'):
        self.analyzer = TrackAnalyzer()
        self.model_path = model_path
        self.encoder_path = encoder_path
        self.model = None
        self.encoders = None
        
        if os.path.exists(model_path):
            self.model = joblib.load(model_path)
            self.encoders = joblib.load(encoder_path)
            print(f"Model geladen van {model_path}")
        else:
            print(f"Waarschuwing: Model niet gevonden op {model_path}. Train eerst een model met trainer.py")

    def predict(self, file_path, save=True):
        if self.model is None:
            return None

        # 1. Extraheer features (audio + metadata)
        print(f"Analyseren van {file_path}...")
        results = self.analyzer.analyze_track(file_path, save=False)
        if not results:
            return None

        # 2. Voorbereiden van features voor model
        audio_features = [
            'tempo', 'mean_spectral_centroid', 'mean_spectral_rolloff', 
            'mean_rms', 'mean_zcr', 'mfcc_1', 'mfcc_2', 'mfcc_3', 'mfcc_4', 'mfcc_5', 'mean_chroma'
        ]
        
        # Audio features DataFrame
        X_audio = pd.DataFrame([results])[audio_features].fillna(0)
        
        # Metadata features voorbereiden (gebruik encoders)
        X_meta = pd.DataFrame()
        for col in ['artist_name', 'label_name', 'source_platform']:
            val = str(results.get(col, 'Unknown'))
            le = self.encoders.get(col)
            
            # Handling voor ongeziene library_labels (simpel: map naar Unknown)
            if val not in le.classes_:
                val = 'Unknown'
            
            X_meta[col] = le.transform([val])
        
        X_meta['release_year'] = float(results.get('release_year') or 0)
        
        # Combineer
        X = pd.concat([X_audio, X_meta], axis=1)
        
        # 3. Voorspelling
        genre_pred = self.model.predict(X)[0]
        probs = self.model.predict_proba(X)[0]
        confidence = float(np.max(probs))
        
        print(f"Voorspeld genre: {genre_pred} (confidence: {confidence:.2f})")
        
        # 4. Opslaan in database
        if save:
            self.save_prediction(file_path, genre_pred, confidence)
            
        return genre_pred, confidence

    def save_prediction(self, file_path, genre, confidence):
        track_hash, internal_id = self.analyzer.get_track_info(file_path)
        track_id = str(internal_id) if internal_id else track_hash
        
        if self.analyzer.engine is None:
            return

        query = """
            INSERT INTO library_track_ml_predictions (track_id, model_version, predicted_genre, confidence_genre)
            VALUES (:tid, :ver, :genre, :conf)
            ON DUPLICATE KEY UPDATE 
                predicted_genre = VALUES(predicted_genre),
                confidence_genre = VALUES(confidence_genre),
                created_at = CURRENT_TIMESTAMP
        """
        
        try:
            with self.analyzer.engine.begin() as conn:
                conn.execute(text(query), {
                    "tid": track_id,
                    "ver": "v1.0-rf",
                    "genre": genre,
                    "conf": confidence
                })
            print(f"Voorspelling opgeslagen voor track_id: {track_id}")
        except Exception as e:
            print(f"Fout bij opslaan voorspelling: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python predict.py <path_to_audio_file>")
        sys.exit(1)
        
    predictor = GenrePredictor()
    predictor.predict(sys.argv[1])
