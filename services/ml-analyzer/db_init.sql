-- ML tabellen voor track analyse

CREATE TABLE IF NOT EXISTS library_track_ml_labels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    track_id VARCHAR(255) NOT NULL,
    ml_genre VARCHAR(100),
    ml_review_status ENUM('unreviewed', 'human_verified', 'borderline', 'do_not_train') DEFAULT 'unreviewed',
    approved_for_training BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX (track_id)
);

CREATE TABLE IF NOT EXISTS library_track_audio_features (
    id INT AUTO_INCREMENT PRIMARY KEY,
    track_id VARCHAR(255) NOT NULL,
    internal_track_id INT,
    file_path TEXT,
    tempo FLOAT,
    duration FLOAT,
    mean_spectral_centroid FLOAT,
    mean_spectral_rolloff FLOAT,
    mean_rms FLOAT,
    mean_zcr FLOAT,
    mfcc_1 FLOAT,
    mfcc_2 FLOAT,
    mfcc_3 FLOAT,
    mfcc_4 FLOAT,
    mfcc_5 FLOAT,
    mean_chroma FLOAT,
    -- Metadata features
    artist_name VARCHAR(255),
    label_name VARCHAR(255),
    release_year INT,
    source_platform VARCHAR(50),
    bpm_tag FLOAT,
    genre_tag VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY (track_id)
);

CREATE TABLE IF NOT EXISTS library_track_ml_predictions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    track_id VARCHAR(255) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    predicted_genre VARCHAR(100),
    confidence_genre FLOAT,
    predicted_subgenre VARCHAR(100),
    confidence_subgenre FLOAT,
    predictions_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX (track_id)
);
