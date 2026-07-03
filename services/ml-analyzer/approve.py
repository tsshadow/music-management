import os
import argparse
import joblib
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def get_prediction(model, encoders, scaler, track_data):
    """Berekent een voorspelling voor de track data."""
    if not model or not encoders or not scaler:
        return None, 0
    
    try:
        # 1. Audio features (moeten geschaald worden)
        audio_features = [
            'duration',
            'mean_spectral_centroid', 'std_spectral_centroid',
            'mean_spectral_bandwidth', 'std_spectral_bandwidth',
            'mean_spectral_rolloff', 'std_spectral_rolloff',
            'mean_rms', 'std_rms', 'mean_zcr', 'std_zcr',
            'mean_spectral_contrast', 'std_spectral_contrast',
            'mean_chroma', 'std_chroma'
        ]
        # Voeg MFCC's toe
        for i in range(1, 14):
            audio_features.append(f'mfcc_{i}')
            audio_features.append(f'std_mfcc_{i}')
            
        X_audio = pd.DataFrame([track_data])[audio_features].fillna(0)
        X_audio_scaled = pd.DataFrame(scaler.transform(X_audio), columns=audio_features)
        
        # 2. Metadata features
        X_meta = pd.DataFrame()
        for col in ['artist_name', 'label_name', 'source_platform']:
            val = str(track_data.get(col, 'Unknown'))
            le = encoders.get(col)
            if not le:
                continue
            
            # Handling voor ongeziene labels
            if val not in le.classes_:
                val = 'Unknown'
            X_meta[col] = le.transform([val])
        
        X_meta['release_year'] = float(track_data.get('release_year') or 0)
        X_meta['tempo'] = float(track_data.get('tempo') or 0)
        
        # 3. WEGING (dupliceren van kolommen zoals in trainer.py)
        X_weighted_meta = X_meta.copy()
        for col in ['artist_name', 'label_name', 'tempo']:
            for i in range(2):
                X_weighted_meta[f'{col}_boost_{i}'] = X_meta[col]
        
        # 4. Combineer in JUISTE volgorde (Metadata EERST, dan audio)
        X = pd.concat([X_weighted_meta, X_audio_scaled], axis=1)
        
        # 5. Predict
        genre_pred = model.predict(X)[0]
        probs = model.predict_proba(X)[0]
        confidence = float(np.max(probs))
        
        return genre_pred, confidence
    except Exception as e:
        # print(f"Prediction error: {e}")
        return None, 0

def approve_tracks():
    parser = argparse.ArgumentParser(description="Interatieve tool om tracks goed te keuren voor ML training.")
    parser.add_argument("--redo", action="store_true", help="Herhaal beoordeling voor alle tracks (ook reeds goedgekeurde)")
    parser.add_argument("--limit", type=int, default=100, help="Aantal tracks om te laden (default: 100)")
    args = parser.parse_args()

    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        # Fallback naar losse DB variabelen
        host = os.getenv("DB_HOST", "db")
        port = os.getenv("DB_PORT", "3306")
        user = os.getenv("DB_USER", "music-management")
        password = os.getenv("DB_PASS", "")
        db_name = os.getenv("DB_DB", "music-management")
        
        if password:
            db_url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}"
            
    if not db_url:
        print("Geen database configuratie gevonden (DATABASE_URL of DB_PASS ontbreekt in .env)")
        return

    engine = create_engine(db_url)
    
    # Probeer model te laden voor previews
    model_path = 'models/genre_classifier.joblib'
    encoder_path = 'models/label_encoders.joblib'
    scaler_path = 'models/feature_scaler.joblib'
    model = None
    encoders = None
    scaler = None
    if os.path.exists(model_path) and os.path.exists(encoder_path) and os.path.exists(scaler_path):
        try:
            model = joblib.load(model_path)
            encoders = joblib.load(encoder_path)
            scaler = joblib.load(scaler_path)
            print(f"ML Model en scalers geladen voor previews.\n")
        except:
            pass

    where_clause = "WHERE l.approved_for_training = 0 AND l.ml_review_status = 'unreviewed'"
    if args.redo:
        where_clause = ""
        print("MODUS: Redo (beoordeel alle tracks opnieuw)")

    query = f"""
        SELECT 
            l.id, f.file_path, f.artist_name, f.label_name, f.genre_tag, l.ml_genre,
            f.tempo, f.mean_rms, f.std_rms, f.release_year, 
            f.mean_spectral_centroid, f.std_spectral_centroid,
            f.mean_spectral_bandwidth, f.std_spectral_bandwidth,
            f.mean_spectral_rolloff, f.std_spectral_rolloff,
            f.mean_spectral_contrast, f.std_spectral_contrast,
            f.mfcc_1, f.mfcc_2, f.mfcc_3, f.mfcc_4, f.mfcc_5, f.mfcc_6, f.mfcc_7, f.mfcc_8, f.mfcc_9, f.mfcc_10, f.mfcc_11, f.mfcc_12, f.mfcc_13,
            f.std_mfcc_1, f.std_mfcc_2, f.std_mfcc_3, f.std_mfcc_4, f.std_mfcc_5, f.std_mfcc_6, f.std_mfcc_7, f.std_mfcc_8, f.std_mfcc_9, f.std_mfcc_10, f.std_mfcc_11, f.std_mfcc_12, f.std_mfcc_13,
            f.mean_zcr, f.std_zcr, f.mean_chroma, f.std_chroma, f.source_platform,
            f.duration,
            l.ml_review_status, l.approved_for_training
        FROM library_track_ml_labels l
        JOIN library_track_audio_features f ON l.track_id = f.track_id
        {where_clause}
        ORDER BY RAND()
        LIMIT :limit
    """
    
    try:
        with engine.connect() as conn:
            tracks = conn.execute(text(query), {"limit": args.limit}).fetchall()
            
            if not tracks:
                print("Geen tracks gevonden die wachten op goedkeuring.")
                return

            print(f"Gevonden: {len(tracks)} tracks om te beoordelen.\n")
            
            for track in tracks:
                (track_id, file_path, artist, label, genre_tag, ml_genre,
                 tempo, rms, std_rms, year, centroid, std_centroid, bandwidth, std_bandwidth,
                 rolloff, std_rolloff, contrast, std_contrast,
                 m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13,
                 s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12, s13,
                 zcr, std_zcr, chroma, std_chroma, platform, duration,
                 review_status, approved_for_training) = track
                genre_to_approve = ml_genre or genre_tag
                
                # Voorbereiden data voor predictie (ALLE features!)
                track_data = {
                    'artist_name': artist, 'label_name': label, 'release_year': year,
                    'tempo': tempo, 'mean_rms': rms, 'std_rms': std_rms,
                    'mean_spectral_centroid': centroid, 'std_spectral_centroid': std_centroid,
                    'mean_spectral_bandwidth': bandwidth, 'std_spectral_bandwidth': std_bandwidth,
                    'mean_spectral_rolloff': rolloff, 'std_spectral_rolloff': std_rolloff,
                    'mean_spectral_contrast': contrast, 'std_spectral_contrast': std_contrast,
                    'mean_zcr': zcr, 'std_zcr': std_zcr,
                    'mean_chroma': chroma, 'std_chroma': std_chroma,
                    'source_platform': platform, 'duration': duration
                }
                # Voeg MFCCs toe
                for i in range(1, 14):
                    track_data[f'mfcc_{i}'] = locals()[f'm{i}']
                    track_data[f'std_mfcc_{i}'] = locals()[f's{i}']
                
                pred_genre, confidence = get_prediction(model, encoders, scaler, track_data)

                print("-" * 50)
                print(f"Song:   {os.path.basename(file_path)}")
                print(f"Artist: {artist}")
                print(f"Label:  {label}")
                print(f"Year:   {year}")
                print("-" * 20 + " ML FEATURES " + "-" * 17)
                print(f"Tempo:  {tempo:.1f} BPM | RMS: {rms:.4f} | ZCR: {zcr:.4f}")
                print(f"Spectral: Centroid={centroid:.0f}, Rolloff={rolloff:.0f}")
                print(f"MFCCs:  {m1:.2f}, {m2:.2f}, {m3:.2f}, {m4:.2f}, {m5:.2f}")
                print(f"Chroma: {chroma:.4f}")
                
                if pred_genre:
                    print("-" * 20 + " AI PREDICTION " + "-" * 15)
                    print(f"AI Guess: {pred_genre} ({confidence*100:.1f}% sure)")
                else:
                    print("-" * 20 + " AI PREDICTION " + "-" * 15)
                    print("AI Guess: Geen voorspelling mogelijk (is het model getraind?)")

                print("-" * 50)
                print(f"Current Genre Tag: {genre_tag}")
                print(f"Proposed ML Genre: {ml_genre}")
                print(f"Status: {review_status} | Approved for training: {approved_for_training}")
                print(f"\nShould be genre: {genre_to_approve}")
                
                if approved_for_training == 1:
                    print("(Reeds goedgekeurd)")
                else:
                    print("Is nog niet goedgekeurd.")
                
                choice = input("Approve? (y/n/s=skip/q=quit): ").lower()
                
                if choice == 'y':
                    conn.execute(
                        text("UPDATE library_track_ml_labels SET approved_for_training = 1, ml_review_status = 'human_verified' WHERE id = :id"),
                        {"id": track_id}
                    )
                    conn.commit()
                    print("Approved!")
                elif choice == 'n':
                    new_genre = input("Enter correct genre (or leave empty to mark as do_not_train): ")
                    if new_genre:
                        conn.execute(
                            text("UPDATE library_track_ml_labels SET ml_genre = :genre, approved_for_training = 1, ml_review_status = 'human_verified' WHERE id = :id"),
                            {"id": track_id, "genre": new_genre}
                        )
                    else:
                        conn.execute(
                            text("UPDATE library_track_ml_labels SET approved_for_training = 0, ml_review_status = 'do_not_train' WHERE id = :id"),
                            {"id": track_id}
                        )
                    conn.commit()
                    print("Updated!")
                elif choice == 'q':
                    print("Stopping...")
                    break
                else:
                    print("Skipped.")
                    
    except Exception as e:
        print(f"Fout bij uitvoeren van approval script: {e}")

if __name__ == "__main__":
    approve_tracks()
