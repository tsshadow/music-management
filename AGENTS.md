# 🤖 Agent Information & System Workflow

This document provides a high-level overview of the Music Management System's internal logic, module interactions, and external integrations for AI agents and developers.

## 🏗 Core Modules & Responsibilities

The system is split into specialized services, each handling a specific part of the music lifecycle:

### 1. `downloader` (`services/downloader`)
- **Sources**: SoundCloud, YouTube, and Telegram.
- **Technology**: Uses `yt-dlp` for SoundCloud/YouTube and a custom Telegram implementation.
- **Logic**: Downloads tracks, extracts metadata (uploader, title, tags), and passes them to the `tagger` for normalization.
- **Service**: Managed via `downloader_service.py` with different `--step` flags for each source.

### 2. `importer` (`services/importer`)
- **Purpose**: Processes incoming music from external sources (e.g., label promo pools, manual downloads).
- **Functionality**:
    - **Extraction**: Unpacks `.zip` and `.rar` archives.
    - **Metadata Extraction**: Infers Publisher and Catalog Number from the folder structure (e.g., `/Labels/Scantraxx/SCAN123/`).
    - **Tagging**: Uses `LabelSong` to apply rule-based metadata.
- **Workflow**: `Monitor` -> `Extract` -> `Tag` -> `Move` to the final library destination.

### 3. `tagger` (Integrated in `music-manager`)
- **Engine**: The core metadata enforcement system.
- **Features**:
    - **Auto-Detection**: `TagSingleFile(path)` automatically detects the song type (SoundCloud, YouTube, Label, etc.) based on its file location and applies appropriate tagging rules.
    - **REST API**: Integrated into `music-manager` (Port 8000) under `/api/tagger`:
        - `POST /api/tagger/tag/all`: Runs the full tagging pipeline in background.
        - `POST /api/tagger/tag/file?path=...`: Tags a single file with auto-detection.
        - `GET /api/tagger/health`: Health check and status.
- **Song Types**:
    - `SoundcloudSong`: Specialized in SoundCloud metadata (e.g., handling "Premiere" prefixes).
    - `YoutubeSong`: Splitting "Artist - Title" strings and handling channel attribution.
    - `LabelSong`: Mapping folder structures to Publisher/Catalog tags and copyright strings.
- **Rules**: A flexible rule engine (`services/tagger/Song/rules/`) that handles:
    - Genre inference based on artists or subgenres.
    - Artist normalization (casing, splitting featured artists).
    - Remixer extraction from titles and assignment to `REMIXER` tag.
    - Cleanup of invalid characters (e.g., zero-width spaces).
- **Background Task**: Managed via a background thread in `music-manager`.

### 4. `scanner` (Integrated in `music-manager`)
- **Role**: Synchronizes the filesystem with the database.
- **Features**:
    - **Metadata Extraction**: Reads tags from audio files and updates the `library_tracks`, `library_artists`, etc., tables.
    - **REST API**: Integrated into `music-manager` (Port 8000) under `/api/scanner`:
        - `POST /api/scanner/scan/all`: Runs a full library scan in background.
        - `POST /api/scanner/scan/file?path=...`: Scans a single file and updates its database record.
        - `GET /api/scanner/health`: Health check and status.
    - **Redownload Service**: Allows triggering redownloads for tracks that originated from SoundCloud or YouTube.
        - Automatically matches library tracks to original source URLs using the download archive.
        - `POST /api/library/tracks/{id}/redownload`: Starts a background redownload task.

### 5. `music-manager` (`services/music_manager`)
- **Role**: The "Source of Truth" and central hub.
- **Backend**: FastAPI service managing:
    - User authentication (synchronizing with `lms.db`).
    - Song ratings and scrobbling history.
    - Real-time notifications via `ntfy.sh`.
    - Dashboard API for the Svelte frontend.
    - **Integrated Services**: Now hosts the `tagger` and `scanner` logic and APIs.
- **Background Listeners**:
    - Streams notifications and events (e.g., from `ntfy.sh` or LMS webhooks).
    - Periodic tagging and scanning tasks.

### 5. `ml-analyzer` (`services/ml-analyzer`)
- **Purpose**: Audio analysis for advanced metadata.
- **Features**: Detects BPM, Musical Key, and Mood using machine learning models.

---

## 🔄 System Workflow

1. **Ingestion**: A new track enters via `downloader`, `importer`, or `telegram`.
2. **Standardization**: The `tagger` service applies site-specific or label-specific rules to ensure metadata consistency.
3. **Database Update**: Metadata and tracking information are saved to the MariaDB `music_management` database.
4. **Library Placement**: The file is moved to its permanent location in the music library.
5. **LMS Sync**: Logitech Media Server rescans the library, making the music available for playback.
6. **Notification**: A success message (formatted via `BaseSong.__str__`) is sent to the user's mobile device via `ntfy.sh`.

---

## 🔗 External Integrations

The system is designed to work in tandem with other projects in the developer's ecosystem:

### KMS(`~/git/lms`)
- **Playback Engine**: The primary server for audio streaming and library management.
- **Data Sync**:
    - `music-manager` directly mounts and interacts with `lms.db` (SQLite) to synchronize users and permissions.
    - Synchronizes song ratings bidirectionally between the local database and LMS.
    - Uses the Subsonic API provided by LMS for client authentication and playback.

### Ultrasonic (`~/git/ultrasonic`)
- **Mobile Client**: An Android application for interacting with the music collection on the go.
- **Settings Backup**: Ultrasonic synchronizes its application settings (stored as JSON) to the `music-manager` API, providing a server-side backup.
- **Interactions**: Ratings changed within Ultrasonic are propagated to LMS and subsequently synced to the central `music-manager` database.

---

## 🧪 Testing & Stability

To maintain high code quality, the system employs an automated test suite:
- **Location**: `services/downloader/*/tests/` and `services/importer/tests/`.
- **Mocking**: Uses a unified `mock_base.py` to provide an isolated environment (mocking `mutagen`, `yt-dlp`, and database helpers).
- **Enforcement**: 
    - **Build Check**: `build.sh` executes the full test suite and aborts the container build if any tests fail.
    - **Pre-commit Hook**: A Git `pre-commit` hook ensures all tests pass before allowing a commit to be finalized.

---

## 🚀 Running Locally

To run services locally with the same environment as in Docker, you can use the following targets:

### 1. Shell Script
Use `scripts/run_local.sh` to launch any service with the correct `PYTHONPATH` and environment variables:
```bash
./scripts/run_local.sh importer
./scripts/run_local.sh soundcloud
./scripts/run_local.sh youtube
```

### 2. PyCharm Run Configurations
Pre-configured "Run Configurations" are available in the `.run/` directory. These will appear automatically in your IDE:
- **Importer Worker**: Runs `importer_service.py` with repeat enabled.
- **SoundCloud Worker**: Runs `downloader_service.py` for SoundCloud.
- **YouTube Worker**: Runs `downloader_service.py` for YouTube.

These configurations automatically load environment variables from your `.env` file and set the correct `PYTHONPATH`.

---

## 🔌 API Specification
The full API specification for the `music-manager` service can be found in [docs/api-specification.md](docs/api-specification.md).

---

## 📜 Development Guidelines

To ensure consistency and reliability, all contributions must adhere to these rules:

1. **Code must be tested**: Every new feature or bug fix must include corresponding tests in the relevant `tests/` directory.
2. **Code must be linted**: Follow PEP 8 guidelines and ensure `pylint` passes with a score above 8.5.
3. **Code must be documented**: Use clear function/class docstrings and update `AGENTS.md`, `README.md`, or the `docs/` folder if system behavior changes.
4. **Release notes / changelog should be written**: Document significant changes in `CHANGELOG.md` or `RELEASE_NOTES.md` before merging.

## Production

Production info can be found at .production