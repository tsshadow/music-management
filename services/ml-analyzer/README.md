# 🧠 ML Analyzer Service

> **DEPRECATED — disabled since 2026-09-25, code kept. See [DEPRECATED.md](DEPRECATED.md).**
> Nobody is working on it, it was never deployed, and it would not work if it ran: the
> already-analysed check reads the wrong key, the `library_track_ml_labels` key has bug report
> 028's stale-join shape, and the predict pipeline does not match what the trainer builds. It is
> not built, deployed, dependency-audited or tested by default; its tests only run in the manual CI
> job `backend:ml-analyzer-unit`. Its tables and their data stay, and the features that read them
> keep showing what is there — new tracks just get no analysis. DEPRECATED.md has the details, with
> file and line, and the checklist for bringing it back.

This service analyzes audio files and extracts musical features for machine learning purposes.

## ⚙️ Functionality

- **Audio Loading**: Supports various formats via FFmpeg integration.
- **Basic Feature Extraction**:
    - Tempo (BPM)
    - Loudness (RMS)
    - Spectral Centroid (timbre/brightness)
    - Duration
- **Not implemented**: mel-spectrograms, pretrained embeddings (musicnn, MuQ) and Essentia
  descriptors were once planned; nothing in this directory computes them.

## 🛠 Tech Stack

- **Python 3.14** in the image (`python:3.14-slim`).
- **Librosa** (with NumPy): audio feature extraction.
- **scikit-learn**, **pandas**, **joblib**: the genre classifier (`trainer.py`, `predict.py`).
- **SQLAlchemy** / **mysql-connector-python**: database interaction.

No PyTorch and no Essentia: neither is in `requirements.txt` or imported anywhere here.

## 📊 What do the results mean?

The analyzer currently extracts the following features:

1.  **Tempo (BPM)**: the speed of the track.
    *   *ML use*: helps tell genres apart (e.g. Hardcore > 160 vs Hardstyle ~150).
    *   *Note*: the analyzer is tuned for faster music (150+ BPM) so the tempo is not detected at
        half speed by accident.
2.  **Duration**: the length of the file.
    *   *ML use*: helps filter short samples or radio edits from extended mixes.
3.  **Spectral Centroid**: the "brightness" or "timbre" of the sound.
    *   *ML use*: harder styles with a lot of distortion (distorted kicks/leads) often score higher.
4.  **Spectral Rolloff**: the frequency below which a given share (e.g. 85%) of the spectral
    energy lies.
    *   *ML use*: helps separate dull from bright sound.
5.  **RMS**: the average loudness (energy).
    *   *ML use*: indicates the intensity and compression of the track.
6.  **Zero Crossing Rate (ZCR)**: how often the signal crosses zero.
    *   *ML use*: an indicator of percussiveness and noise. Hardcore kicks often have a distinctive
        ZCR signature.
7.  **MFCCs (Mel-frequency cepstral coefficients)**: a compact representation of the spectral shape.
    *   *ML use*: the "gold standard" for timbre recognition and genre classification.
8.  **Chroma Features**: the distribution of harmonic energy over the 12 pitch classes.
    *   *ML use*: helps recognise key and melodic patterns.

## 🚀 Usage

### Via Docker

There is no running container to `docker exec` into: the service is commented out of
`docker/docker-compose.yml`. To try it, build `services/ml-analyzer/Dockerfile` (from the
repository root, as the build context) and run it against a music mount and the database
environment (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_DB`). The image's default command is
`python services/ml-analyzer/analyzer.py --all --save --repeat --sleeptime 3600`; the script
lives at `services/ml-analyzer/analyzer.py` inside the image, so pass that path for a one-off run:

```bash
# A single track
python services/ml-analyzer/analyzer.py /mnt/music/path/to/track.mp3

# A whole folder, saved to the database
python services/ml-analyzer/analyzer.py /mnt/music/path/to/folder --save

# A folder, analysed in parallel (faster)
python services/ml-analyzer/analyzer.py /mnt/music/path/to/folder --save --parallel

# The whole collection (like the tagger)
python services/ml-analyzer/analyzer.py --all --save --parallel
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

*Note: `librosa` decodes through FFmpeg for most formats, so FFmpeg has to be installed on the system.*

#### 2. Configuration

The database connection comes from the environment: `DB_HOST` (default `db`), `DB_PORT` (`3306`),
`DB_USER`, `DB_PASS` and `DB_DB`; `MUSIC_PATH` (default `/mnt/music`) and `EPS_PATH` choose what
`--all` scans. There is no `.env.example` in this directory — use the repository's root `.env`.
Without `--save` the features are only printed to stdout.

#### 3. Run

Analyse one file:
```bash
python analyzer.py /path/to/your/music/file.mp3
```

Analyse a folder and save to the database:
```bash
python analyzer.py /path/to/folder --save
```

Analyse the whole collection in parallel (`MUSIC_PATH`/`EPS_PATH`):
```bash
python analyzer.py --all --save --parallel
```

## 📅 Future Roadmap

From [docs/machine-learning.md](../../docs/machine-learning.md), which is an unbuilt proposal:

1. **Audio Chunking**: Splitting library_tracks into smaller fragments for better training data.
2. **Genre Classification**: Training custom models based on the high-quality labeled library.
3. **Kick-type Recognition**: Specialized models for identifying different kick drum styles in electronic music.
