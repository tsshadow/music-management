import os
import argparse
import pandas as pd
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import classification_report
import joblib
from analyzer import TrackAnalyzer

def _prepare_metadata(df):
    X_meta = pd.DataFrame()
    le_dict = {}
    for col in ['artist_name', 'label_name', 'source_platform']:
        le = LabelEncoder()
        X_meta[col] = le.fit_transform(df[col].fillna('Unknown').astype(str))
        le_dict[col] = le
    X_meta['release_year'] = df['release_year'].fillna(0)
    X_meta['tempo'] = df['tempo'].fillna(0)
    return (X_meta, le_dict)

def _prepare_audio_features(df, audio_features):
    X_audio = df[audio_features].fillna(0)
    scaler = StandardScaler()
    X_audio_scaled = pd.DataFrame(scaler.fit_transform(X_audio), columns=audio_features, index=df.index)
    return (X_audio_scaled, scaler)

def _apply_genre_hierarchy(df, analyzer):
    print('Verwerken van genres (splitsen en hiërarchie toepassen)...')
    df['ml_genre_split'] = df['ml_genre'].str.split(';')
    hierarchy = analyzer.get_subgenre_hierarchy()

    def apply_hierarchy(genres_list):
        if not genres_list:
            return []
        extended = set(genres_list)
        for g in genres_list:
            if g in hierarchy:
                for parent in hierarchy[g]:
                    extended.add(parent)
        return list(extended)
    df['ml_genre_split'] = df['ml_genre_split'].apply(apply_hierarchy)
    return df.explode('ml_genre_split')

def _filter_genres(df_flat, min_samples=5):
    counts = df_flat['ml_genre_split'].value_counts()
    to_keep = counts[counts >= min_samples].index
    if len(to_keep) < 2:
        print(f'Te weinig data na splitsen (minimaal {min_samples} samples per genre nodig).')
        print('Beschikbare genres en aantal samples:')
        print(counts)
        return df_flat
    print(f'Genres na splitsen: {len(to_keep)} unieke genres met >= {min_samples} samples.')
    return df_flat[df_flat['ml_genre_split'].isin(to_keep)]

def _prepare_final_features(df_flat, le_dict, scaler, audio_features):
    X_flat_meta_list = []
    for col in ['artist_name', 'label_name', 'source_platform']:
        le = le_dict[col]
        encoded_col = le.transform(df_flat[col].fillna('Unknown').astype(str))
        X_flat_meta_list.append(pd.Series(encoded_col, name=col, index=df_flat.index))
    X_flat_meta = pd.concat(X_flat_meta_list, axis=1)
    X_flat_meta['release_year'] = df_flat['release_year'].fillna(0)
    X_flat_meta['tempo'] = df_flat['tempo'].fillna(0)
    X_weighted_meta = X_flat_meta.copy()
    for col in ['artist_name', 'label_name', 'tempo']:
        for i in range(2):
            X_weighted_meta[f'{col}_boost_{i}'] = X_flat_meta[col]
    X_flat_audio = df_flat[audio_features].fillna(0)
    X_flat_audio_scaled = pd.DataFrame(scaler.transform(X_flat_audio), columns=audio_features, index=df_flat.index)
    X_final = pd.concat([X_weighted_meta, X_flat_audio_scaled], axis=1)
    y_final = df_flat['ml_genre_split']
    return (X_final, y_final)

def train_model(test_mode=False):
    analyzer = TrackAnalyzer()
    print('Ophalen van training data...')
    if test_mode:
        print('MODUS: Test (gebruik alle data, inclusief unapproved)')
        df = analyzer.get_training_data(include_unapproved=True)
    else:
        df = analyzer.get_training_data(min_quality='human_verified')
    if df is None or len(df) < 10:
        print("Onvoldoende data voor training. Zorg dat library_tracks zijn geanalyseerd en gelabeld in 'library_track_ml_labels'.")
        return
    print(f'Data geladen: {len(df)} library_tracks.')
    audio_features = ['duration', 'mean_spectral_centroid', 'std_spectral_centroid', 'mean_spectral_bandwidth', 'std_spectral_bandwidth', 'mean_spectral_rolloff', 'std_spectral_rolloff', 'mean_rms', 'std_rms', 'mean_zcr', 'std_zcr', 'mean_spectral_contrast', 'std_spectral_contrast', 'mean_chroma', 'std_chroma']
    for i in range(1, 14):
        audio_features.append(f'mfcc_{i}')
        audio_features.append(f'std_mfcc_{i}')
    _, le_dict = _prepare_metadata(df)
    _, scaler = _prepare_audio_features(df, audio_features)
    df_flat = _apply_genre_hierarchy(df, analyzer)
    df_flat = _filter_genres(df_flat)
    X_final, y_final = _prepare_final_features(df_flat, le_dict, scaler, audio_features)
    print('Splitsen van data (gebaseerd op track_id)...')
    unique_tracks = df_flat['track_id'].unique()
    train_ids, test_ids = train_test_split(unique_tracks, test_size=0.2, random_state=42)
    train_mask = df_flat['track_id'].isin(train_ids)
    test_mask = df_flat['track_id'].isin(test_ids)
    X_train = X_final[train_mask]
    X_test = X_final[test_mask]
    y_train = y_final[train_mask]
    y_test = y_final[test_mask]
    print(f'Trainen van Random Forest model op {len(X_train)} samples ({len(train_ids)} unieke tracks)...')
    param_grid = {'n_estimators': [200, 300], 'max_depth': [15, 20, 25], 'min_samples_split': [2, 5], 'max_features': ['sqrt', 'log2'], 'class_weight': ['balanced', 'balanced_subsample']}
    rf = RandomForestClassifier(random_state=42)
    grid_search = GridSearchCV(estimator=rf, param_grid=param_grid, cv=3, n_jobs=-1, scoring='f1_weighted')
    grid_search.fit(X_train, y_train)
    clf = grid_search.best_estimator_
    print(f'Beste parameters: {grid_search.best_params_}')
    y_pred = clf.predict(X_test)
    print('\n' + '=' * 50)
    print('MODEL EVALUATIE RAPPORT\n' + '=' * 50)
    print(classification_report(y_test, y_pred, zero_division=0))
    print('=' * 50)
    importances = clf.feature_importances_
    feature_names = X_final.columns
    feature_importance_df = pd.DataFrame({'feature': feature_names, 'importance': importances})
    print('\nTop 10 belangrijkste features:')
    print(feature_importance_df.sort_values(by='importance', ascending=False).head(10))
    if test_mode:
        print('\nTEST MODUS: Model en scalers worden NIET opgeslagen.')
    else:
        os.makedirs('models', exist_ok=True)
        joblib.dump(clf, 'models/genre_classifier.joblib')
        joblib.dump(le_dict, 'models/label_encoders.joblib')
        joblib.dump(scaler, 'models/feature_scaler.joblib')
        print("\nModel en bijbehorende scalers opgeslagen in 'models/'")
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train het genre classificatie model.')
    parser.add_argument('--test', action='store_true', help='Test modus: gebruikt alle data en slaat niets op.')
    args = parser.parse_args()
    train_model(test_mode=args.test)