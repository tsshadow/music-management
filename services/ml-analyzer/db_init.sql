-- ML tabellen voor track analyse

CREATE TABLE IF NOT EXISTS track_ml_labels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    track_id VARCHAR(255) NOT NULL,
    ml_genre VARCHAR(100),
    ml_subgenre VARCHAR(100),
    ml_kick_type VARCHAR(100),
    ml_energy FLOAT,
    ml_has_vocal BOOLEAN,
    ml_is_liveset BOOLEAN,
    ml_review_status ENUM('unreviewed', 'human_verified', 'borderline', 'do_not_train') DEFAULT 'unreviewed',
    approved_for_training BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX (track_id)
);

CREATE TABLE IF NOT EXISTS track_audio_features (
    id INT AUTO_INCREMENT PRIMARY KEY,
    track_id VARCHAR(255) NOT NULL,
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY (track_id)
);

CREATE TABLE IF NOT EXISTS track_ml_predictions (
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
