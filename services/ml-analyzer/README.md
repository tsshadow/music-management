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

## 📊 Wat betekenen de resultaten?

De analyzer haalt momenteel de volgende kenmerken uit je muziek:

1.  **Tempo (BPM)**: De snelheid van de track. 
    *   *ML nut*: Helpt bij het onderscheiden van genres (bijv. Hardcore > 160 vs Hardstyle ~150).
2.  **Duration**: De lengte van het bestand.
    *   *ML nut*: Helpt bij het filteren van korte samples of radio edits vs extended mixes.
3.  **Mean Spectral Centroid**: De "helderheid" of het "timbre" van het geluid. 
    *   *ML nut*: Hardere stijlen met veel vervorming (distorted kicks/leads) hebben vaak een hogere waarde.
4.  **Mean RMS**: De gemiddelde luidheid (energie).
    *   *ML nut*: Geeft een indicatie van de intensiteit en compressie van de track.

## 🚀 Usage

### Via Docker

The service is included in the main `docker-compose.yml` (located in `work-context/`).

Build and start:
```bash
docker-compose up -d ml-analyzer
```

Manually analyze a track or folder:
```bash
# Enkele track
docker exec -it muma-ml-analyzer python analyzer.py /mnt/music/path/to/track.mp3

# Hele map en opslaan in database
docker exec -it muma-ml-analyzer python analyzer.py /mnt/music/path/to/folder --save
```

### Local (Native Python)

You can also run the analyzer directly on your host machine without Docker.

#### 1. Install Dependencies

It is recommended to use a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
# If you encounter a ReadTimeoutError, use a higher timeout:
pip install --default-timeout=100 -r requirements.txt
```

*Note: `essentia-tensorflow` is a large package (~300MB) and is currently not required for the basic `analyzer.py`. You can comment it out in `requirements.txt` if you have a slow connection and want to start with basic features.*

*Note: `essentia-tensorflow` might require specific system libraries (like FFmpeg) to be installed on your system.*

#### 2. Configuration

Ensure you have a `.env` file in this directory with the correct database credentials (see `.env.example`). If you only want to see the output in the console and not save to the DB, the script will work as long as `DB_PASS` is empty or the connection fails gracefully (currently it prints features to stdout).

#### 3. Run

Analyseer een bestand:
```bash
python analyzer.py /path/to/your/music/file.mp3
```

Analyseer een map en sla op in DB:
```bash
python analyzer.py /path/to/folder --save
```

## 📅 Future Roadmap (as per machine-learning.md)

1. **Database Integration**: Automatically save extracted features to MariaDB.
2. **Audio Chunking**: Splitting tracks into smaller fragments for better training data.
3. **Genre Classification**: Training custom models based on the high-quality labeled library.
4. **Kick-type Recognition**: Specialized models for identifying different kick drum styles in electronic music.
