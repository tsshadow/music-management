# 🎵 Music Management System

A comprehensive, modular system for automated music library management, including downloading, rule-based tagging, and listening history tracking (scrobbling).

## 🏗 Project Architecture

This project is composed of several specialized modules and services that work together to maintain a high-quality music library.

### 1. Music Importer & Tagger (`services/` & `modules/music-management`)
The core of the system that handles the lifecycle of music files:
- **Downloaders**: Automated fetching from YouTube, SoundCloud, and Telegram.
- **Importer**: Monitors incoming files, extracts archives, and moves them to the library.
- **Tagger**: A rule-based engine that cleans metadata, guesses missing tags (artist, title, genre) from filenames, and enforces library standards.
- **Common**: Shared utilities and the internal API.

### 2. Scrobbler (`modules/scrobbler`)
A service for tracking listening history:
- Ingests "listens" from compatible players (Open Subsonic, LMS).
- Links listening events to the canonical media library.
- Provides a dashboard with statistics and trends.
- Integrates with ListenBrainz for import/export.

### 3. Frontends (`frontend/`)
- **Music Management UI**: Dashboard for monitoring import/tagging jobs.
- **Scrobbler UI**: Dashboard for listening history and library analytics.

### 4. Artist Image Fetcher (`services/artist_image_fetcher`)
A pipeline for enriching the library with high-quality artist images:
- Fetches images from Spotify, SoundCloud, and Last.fm.
- Uses MusicBrainz for metadata and external ID matching.
- Implements a confidence-based matching system.
- Caches images and thumbnails locally for the LMS player.
- Provides a stable path convention for player integration.

### 5. Control Center (`services/management-api`)
A central dashboard for the system:
- View high-level release notes and technical changelogs.
- Track system version and module status.
- Centralized access to documentation and maintenance features.

---

## 🚀 Getting Started

The easiest way to run the entire stack is using Docker Compose.

### Prerequisites
- Docker and Docker Compose
- Current user in the `docker` group (for building images)
- Docker Hub account and `docker login` (if pushing images to the registry)
- `sshpass` (optional, for automated remote deployment)
- A MariaDB/MySQL database (included in compose)

### Quick Start
1. Clone the repository.
2. Run `./install.sh` to install dependencies and create a `.env` file.
3. Configure your `.env` file with your paths, database credentials, and optional remote host settings.
4. Start the services:
   ```bash
   docker-compose -f work-context/docker-compose.yml up -d
   ```

### Building and Deployment
If you are modifying the code and need to rebuild and redeploy the system:

- **Build all images**: `./build.sh`
- **Publish all images**: `./publish.sh`
- **Deploy to remote**: `./deploy.sh`
- **Full pipeline (Build + Publish + Deploy)**: `./build_and_publish.sh`

#### Remote Deployment Options
You can configure deployment in `.env`:
1. **Portainer Webhook**: Set `PORTAINER_WEBHOOK_URL`.
   - **Business Edition**: Supports "Stack Webhooks" (triggers a full stack redeploy).
   - **Community Edition**: Supports "Service Webhooks" (trigger per service). If you have multiple services, you might prefer the SSH method.
2. **SSH**: Set `REMOTE_HOST`, `REMOTE_USER`, etc. The script will automatically discover your Docker Compose configuration (even if managed by Portainer), transfer it securely, and redeploy the stack. If the stack does not exist yet, it will be created using the local `docker-compose.yml` template. This method is highly recommended for multi-host setups and Community Edition users.

**Tip**: Use `DEPLOY_TARGET_NAME` in `.env` to give your deployment target a friendly name (e.g., "Production Stack"). The system now uses this to automatically manage stack naming and discovery across different repositories.

You can also target specific components with `build.sh` and `publish.sh`:
- `./build.sh ml` (ML Analyzer only)
- `./build.sh tools` (Tools only)
- `./build.sh app` (Main Application only)

The following services will be available:
- **Control Center (Release Notes)**: Port 8003
- **Music Management API**: Port 7001 (if enabled)
- **Scrobbler API**: Port 8080
- **phpMyAdmin**: Port 8002 (to inspect the database)
- **Firefox (GUI)**: Port 7003

---

## 🛠 Docker Stack Management

The system is split into modular Docker Compose files for better resource management:

1. **`docker-compose.yml`**: Core infrastructure (MariaDB, phpMyAdmin, Control Center).
2. **`docker-compose.workers.yml`**: Background workers (Importer, YouTube/SoundCloud/Telegram downloaders, Tagger).
3. **`docker-compose.tools.yml`**: Utility services (Fetchers, ML Analyzer, Firefox).

### Common Commands:

**Start the entire stack:**
```bash
docker-compose -f docker-compose.yml -f docker-compose.workers.yml -f docker-compose.tools.yml up -d
```

**Start only core services:**
```bash
docker-compose up -d
```

**View logs for a specific service:**
```bash
docker-compose -f docker-compose.yml -f docker-compose.workers.yml logs -f importer_worker
```

---

## 📂 Repository Structure

```text
├── services/               # Backend microservices
│   ├── downloader/         # YouTube, SoundCloud, Telegram workers
│   ├── importer/           # File movement and archive extraction
│   ├── tagger/             # Rule-based metadata tagging engine
│   ├── artist_image_fetcher/ # Artist image enrichment pipeline
│   └── common/             # Shared logic and internal API
├── modules/                # Larger functional modules
│   ├── music-management/   # Legacy/Core logic for the importer
│   └── scrobbler/          # Listening history tracking service
├── frontend/               # Svelte-based web interfaces
├── docs/                   # Detailed documentation and diagrams
└── work-context/           # Docker Compose and environment configuration
```

---

## 📖 Detailed Documentation

For specific information on each module, please refer to their respective READMEs:

- [Music Importer](services/importer/README.md)
- [Music Downloader](services/downloader/README.md)
- [Music Tagger](services/tagger/README.md)
- [Scrobbler](modules/scrobbler/README.md)
- [Database Schema](docs/database-design.md)
- [Data Flow](docs/system-data-flow.md)

---

## 👨‍💻 Development

This project is primarily designed for personal use, tailored to specific workflows for electronic music (Hardcore, Hardstyle, etc.).

### Tools
Check the `tools/` directory for utility scripts like `process_genres.py`.

### Testing
Run tests using pytest:
```bash
pytest
```
