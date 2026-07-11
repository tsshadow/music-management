import os
import argparse
import joblib
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def get_prediction(model, encoders, scaler, track_data):
    """Berekent een voorspelling voor de track data."""
    if not model or not encoders or (not scaler):
        return (None, 0)
    try:
        audio_features = ['duration', 'mean_spectral_centroid', 'std_spectral_centroid', 'mean_spectral_bandwidth', 'std_spectral_bandwidth', 'mean_spectral_rolloff', 'std_spectral_rolloff', 'mean_rms', 'std_rms', 'mean_zcr', 'std_zcr', 'mean_spectral_contrast', 'std_spectral_contrast', 'mean_chroma', 'std_chroma']
        for i in range(1, 14):
            audio_features.append(f'mfcc_{i}')
            audio_features.append(f'std_mfcc_{i}')
        X_audio = pd.DataFrame([track_data])[audio_features].fillna(0)
        X_audio_scaled = pd.DataFrame(scaler.transform(X_audio), columns=audio_features)
        X_meta = pd.DataFrame()
        for col in ['artist_name', 'label_name', 'source_platform']:
            val = str(track_data.get(col, 'Unknown'))
            le = encoders.get(col)
            if not le:
                continue
            if val not in le.classes_:
                val = 'Unknown'
            X_meta[col] = le.transform([val])
        X_meta['release_year'] = float(track_data.get('release_year') or 0)
        X_meta['tempo'] = float(track_data.get('tempo') or 0)
        X_weighted_meta = X_meta.copy()
        for col in ['artist_name', 'label_name', 'tempo']:
            for i in range(2):
                X_weighted_meta[f'{col}_boost_{i}'] = X_meta[col]
        X = pd.concat([X_weighted_meta, X_audio_scaled], axis=1)
        genre_pred = model.predict(X)[0]
        probs = model.predict_proba(X)[0]
        confidence = float(np.max(probs))
        return (genre_pred, confidence)
    except Exception:
        return (None, 0)

def _get_db_url():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        host = os.getenv('DB_HOST', 'db')
        port = os.getenv('DB_PORT', '3306')
        user = os.getenv('DB_USER', 'music-management')
        password = os.getenv('DB_PASS', '')
        db_name = os.getenv('DB_DB', 'music-management')
        if password:
            db_url = f'mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db_name}'
    return db_url

def _process_single_track(conn, track, model_data):
    model, encoders, scaler = model_data
    track_id, file_path, artist, label, genre_tag, ml_genre, tempo, rms, _, year, centroid, _, _, _, rolloff, _, contrast, std_contrast, *mfccs_and_more = track
    m1 = mfccs_and_more[0]
    zcr = mfccs_and_more[26]
    chroma = mfccs_and_more[28]
    platform = mfccs_and_more[30]
    duration = mfccs_and_more[31]
    review_status = mfccs_and_more[32]
    approved_for_training = mfccs_and_more[33]
    genre_to_approve = ml_genre or genre_tag
    track_data = {'artist_name': artist, 'label_name': label, 'release_year': year, 'tempo': tempo, 'mean_rms': rms, 'std_rms': track[8], 'mean_spectral_centroid': centroid, 'std_spectral_centroid': track[11], 'mean_spectral_bandwidth': track[12], 'std_spectral_bandwidth': track[13], 'mean_spectral_rolloff': rolloff, 'std_spectral_rolloff': track[15], 'mean_spectral_contrast': contrast, 'std_spectral_contrast': std_contrast, 'mean_zcr': zcr, 'std_zcr': mfccs_and_more[27], 'mean_chroma': chroma, 'std_chroma': mfccs_and_more[29], 'source_platform': platform, 'duration': duration}
    for i in range(1, 14):
        track_data[f'mfcc_{i}'] = mfccs_and_more[i - 1]
        track_data[f'std_mfcc_{i}'] = mfccs_and_more[i + 12]
    pred_genre, confidence = get_prediction(model, encoders, scaler, track_data)
    print('-' * 50)
    print(f'Song:   {os.path.basename(file_path)}')
    print(f'Artist: {artist} | Label: {label} | Year: {year}')
    print(f'Tempo:  {tempo:.1f} BPM | RMS: {rms:.4f} | ZCR: {zcr:.4f}')
    print(f'Spectral: Centroid={centroid:.0f}, Rolloff={rolloff:.0f}')
    print(f'MFCCs:  {m1:.2f}, {mfccs_and_more[1]:.2f}, {mfccs_and_more[2]:.2f}...')
    print(f'Chroma: {chroma:.4f}')
    if pred_genre:
        print(f'AI Guess: {pred_genre} ({confidence * 100:.1f}% sure)')
    else:
        print('AI Guess: Geen voorspelling mogelijk')
    print('-' * 50)
    print(f'Proposed ML Genre: {ml_genre} (Current Tag: {genre_tag})')
    print(f'Status: {review_status} | Approved: {bool(approved_for_training)}')
    print(f'\nShould be genre: {genre_to_approve}')
    choice = input('Approve? (y/n/s=skip/q=quit): ').lower()
    if choice == 'y':
        conn.execute(text("UPDATE library_track_ml_labels SET approved_for_training = 1, ml_review_status = 'human_verified' WHERE id = :id"), {'id': track_id})
        conn.commit()
        print('Approved!')
    elif choice == 'n':
        new_genre = input('Enter correct genre (or leave empty to mark as do_not_train): ')
        if new_genre:
            conn.execute(text("UPDATE library_track_ml_labels SET ml_genre = :genre, approved_for_training = 1, ml_review_status = 'human_verified' WHERE id = :id"), {'id': track_id, 'genre': new_genre})
        else:
            conn.execute(text("UPDATE library_track_ml_labels SET approved_for_training = 0, ml_review_status = 'do_not_train' WHERE id = :id"), {'id': track_id})
        conn.commit()
        print('Updated!')
    return choice

def approve_tracks():
    parser = argparse.ArgumentParser(description='Interatieve tool om tracks goed te keuren voor ML training.')
    parser.add_argument('--redo', action='store_true', help='Herhaal beoordeling voor alle tracks')
    parser.add_argument('--limit', type=int, default=100, help='Aantal tracks om te laden')
    args = parser.parse_args()
    load_dotenv()
    db_url = _get_db_url()
    if not db_url:
        print('Geen database configuratie gevonden')
        return
    engine = create_engine(db_url)
    model_data = (None, None, None)
    if all((os.path.exists(f'models/{p}.joblib') for p in ['genre_classifier', 'label_encoders', 'feature_scaler'])):
        try:
            model_data = (joblib.load('models/genre_classifier.joblib'), joblib.load('models/label_encoders.joblib'), joblib.load('models/feature_scaler.joblib'))
            print('ML Model en scalers geladen voor previews.\n')
        except Exception:
            pass
    where_clause = "WHERE l.approved_for_training = 0 AND l.ml_review_status = 'unreviewed'"
    if args.redo:
        where_clause = ''
        print('MODUS: Redo (beoordeel alle tracks opnieuw)')
    query = f'\n        SELECT\n            l.id, f.file_path, f.artist_name, f.label_name, f.genre_tag, l.ml_genre,\n            f.tempo, f.mean_rms, f.std_rms, f.release_year,\n            f.mean_spectral_centroid, f.std_spectral_centroid,\n            f.mean_spectral_bandwidth, f.std_spectral_bandwidth,\n            f.mean_spectral_rolloff, f.std_spectral_rolloff,\n            f.mean_spectral_contrast, f.std_spectral_contrast,\n            f.mfcc_1, f.mfcc_2, f.mfcc_3, f.mfcc_4, f.mfcc_5, f.mfcc_6, f.mfcc_7, f.mfcc_8, f.mfcc_9, f.mfcc_10, f.mfcc_11, f.mfcc_12, f.mfcc_13,\n            f.std_mfcc_1, f.std_mfcc_2, f.std_mfcc_3, f.std_mfcc_4, f.std_mfcc_5, f.std_mfcc_6, f.std_mfcc_7, f.std_mfcc_8, f.std_mfcc_9, f.std_mfcc_10, f.std_mfcc_11, f.std_mfcc_12, f.std_mfcc_13,\n            f.mean_zcr, f.std_zcr, f.mean_chroma, f.std_chroma, f.source_platform,\n            f.duration,\n            l.ml_review_status, l.approved_for_training\n        FROM library_track_ml_labels l\n        JOIN library_track_audio_features f ON l.track_id = f.track_id\n        {where_clause}\n        ORDER BY RAND()\n        LIMIT :limit\n    '
    try:
        with engine.connect() as conn:
            tracks = conn.execute(text(query), {'limit': args.limit}).fetchall()
            if not tracks:
                print('Geen tracks gevonden die wachten op goedkeuring.')
                return
            print(f'Gevonden: {len(tracks)} tracks om te beoordelen.\n')
            for track in tracks:
                choice = _process_single_track(conn, track, model_data)
                if choice == 'q':
                    print('Stopping...')
                    break
    except Exception as e:
        print(f'Fout bij uitvoeren van approval script: {e}')
if __name__ == '__main__':
    approve_tracks()