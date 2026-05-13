# 🧠 ML Analyzer Service

This service is responsible for analyzing audio files and extracting musical features for machine learning purposes.

## ⚙️ Functionality

- **Audio Loading**: Supports various formats via FFmpeg integration.
- **Basic Feature Extraction**:
    - Tempo (BPM)
    - Loudness (RMS)
    - Spectral Centroid (timbre/brightness)
    - Duration
- **Advanced Extraction Ready**:
    - Mel-spectrograms
    - Pretrained embeddings (musicnn, MuQ)
    - Essentia descriptors

## 🛠 Tech Stack

- **Python 3.10+**
- **PyTorch**: Deep learning framework.
- **Librosa**: Audio and music analysis.
- **Essentia**: Music-specific feature extraction.
- **SQLAlchemy**: Database interaction.

## 🚀 Usage

### Via Docker

The service is included in the main `docker-compose.yml` (located in `work-context/`).

Build and start:
```bash
docker-compose up -d ml-analyzer
```

Manually analyze a track:
```bash
docker exec -it muma-ml-analyzer python analyzer.py /mnt/music/path/to/track.mp3
```

## 📅 Future Roadmap (as per machine-learning.md)

1. **Database Integration**: Automatically save extracted features to MariaDB.
2. **Audio Chunking**: Splitting tracks into smaller fragments for better training data.
3. **Genre Classification**: Training custom models based on the high-quality labeled library.
4. **Kick-type Recognition**: Specialized models for identifying different kick drum styles in electronic music.
