# 🎵 Music Management System

[![pipeline develop](https://gitlab.example.com/muma/music-management/badges/develop/pipeline.svg?key_text=pipeline%20develop&key_width=104)](https://gitlab.example.com/muma/music-management/-/pipelines?ref=develop)
[![coverage develop](https://gitlab.example.com/muma/music-management/badges/develop/coverage.svg?key_text=coverage%20develop&key_width=110)](https://gitlab.example.com/muma/music-management/-/graphs/develop/charts)
[![pipeline master](https://gitlab.example.com/muma/music-management/badges/master/pipeline.svg?key_text=pipeline%20master&key_width=104)](https://gitlab.example.com/muma/music-management/-/pipelines?ref=master)
[![coverage master](https://gitlab.example.com/muma/music-management/badges/master/coverage.svg?key_text=coverage%20master&key_width=110)](https://gitlab.example.com/muma/music-management/-/graphs/master/charts)
[![license](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

A comprehensive, modular system for automated music library management, featuring a unified "Spotify-style" UI, automated downloading, rule-based tagging, ML analysis, and Subsonic-compatible playback.

## 🧩 Modular System Architecture

The project is built as a set of specialized services that work together to manage the full music lifecycle.

### Core Services
- **`frontend`**: A unified Svelte-based "Spotify UI" that handles both playback and system management.
- **`music-manager`**: The central hub and "Source of Truth". Manages metadata, ratings, scrobbling, and coordinates background tasks.
- **`music-management-server`**: The high-performance C++ playback engine. Provides audio streaming and the Subsonic API.

### Specialized Workers
- **`muma-scanner`**: High-performance library scanning and database synchronization.
- **`muma-tagger`**: Rule-based metadata enforcement and genre inference engine.
- **`muma-downloader`**: Automated fetches from YouTube and SoundCloud.
- **`muma-telegram`**: Dedicated worker for Telegram-based music discovery.
- **`muma-importer`**: Archive extraction and automated file movement.
- **`muma-ml-analyzer`**: Machine learning pipeline for BPM, key, and mood detection.

---

## 🏗 Project Modules

### 1. Unified Frontend (`services/frontend`)
A modern, responsive Svelte application that provides:
- **Playback Control**: Integrated player with queue management.
- **System Management**: Dedicated "Systeembeheer" (System Management) dashboard for Tagger, Scanner, User management, and Worker status.
- **Library View**: Rich browsing by artist, album, and genre.

### 2. Music Manager (`services/music_manager`)
A FastAPI service acting as the management backend:
- Consolidates ratings, scrobbling history, and stats.
- Manages the "Artist Image Fetcher" for metadata enrichment.
- Provides real-time notifications via `ntfy.sh`.

### 3. Music Management Server (`services/music-management-server`)
The core streaming component:
- Provides a stable Subsonic-compatible API for mobile apps like Ultrasonic.
- Handles high-performance audio streaming.
- Integrated directly into the management ecosystem.

### 4. Mobile Client: Ultrasonic
The ecosystem includes a dedicated mobile experience via the **Ultrasonic** Android app:
- **Subsonic API**: Connects to the Music Management Server for streaming.
- **Settings Sync**: Automatically synchronizes application settings (themes, bookmarks, player preferences) to the Music Manager API.
- **Rating Integration**: Ratings changed in the app are propagated back to the central database.
- **Update Management**: Distributed via a built-in APK Hoster for easy updates.

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
2. Run `./install.sh` to setup your environment (installs Docker and creates `.env`).
3. Configure your `.env` file with your paths, database credentials, and optional remote host settings.
4. Build and deploy the system:
   ```bash
   ./install.sh
   ```

### Building and Deployment
If you are modifying the code and need to rebuild and redeploy the system:

- **Full pipeline (Build + Publish + Deploy)**: `./install.sh`
  - Uses `scripts/affected.sh` to detect which modules have changed if no modules are specified.
  - Skips builds and pushes for unedited modules to save time.
  - Automatically deploys the updated stack to production.
  - **New**: Use `--semi-remote` to offload heavy builds (`app`, `ml`, `tools`) to the remote LXC container (192.0.2.40).
  - **New**: Use `--remote` to perform the entire build on the remote LXC container.
  - **New**: Use `--app=<app>` or positional arguments to target specific modules (e.g., `./install.sh --app=user rating`).
  - **New**: Use `./install.sh manager` to view music library statistics from the terminal.
- **Individual steps**:
  - Build: `./build.sh`
  - Publish: `./publish.sh`
  - Deploy: `./deploy.sh`

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
- **Music Management Server (Spotify UI)**: Port 5082
- **Music Manager (API)**: Port 8000
- **phpMyAdmin**: Port 8002 (to inspect the database)

### User Management

You can manage users via the Systeembeheer dashboard in the frontend. 
If you need to set or reset a user's password via the command line, use the provided script:

```bash
./scripts/set_user_password.sh <username>
```

The script will prompt you for a password and confirmation. You can also provide the password directly with `--password <pass>`, but this is less secure as it might be stored in your shell history.

---

## 🛠 Docker Stack Management

The system is split into modular Docker Compose files for better resource management:

1. **`docker-compose.yml`**: Core infrastructure (MariaDB, phpMyAdmin, Music Management Server, Music Manager).
2. **`docker-compose.workers.yml`**: Background workers (Importer, YouTube/SoundCloud/Telegram downloaders, Tagger, Scanner).
3. **`docker-compose.tools.yml`**: Utility services (Fetchers, ML Analyzer, Firefox).

### Database Backups
A SQL dump of the MariaDB database is automatically created during every deployment. Manual backups can be triggered using:
```bash
./tools/backup_db.sh
```
Backups are stored in `/muma/backups` on the host machine. The script uses `docker exec` to perform the dump within the running database container.

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
├── services/               # System components
│   ├── frontend/           # Unified Svelte UI (Spotify UI + Management)
│   ├── music_manager/      # Management API, Ratings, Scrobbling
│   ├── music-management-server/ # Playback Engine & Subsonic API
│   ├── downloader/         # YouTube, SoundCloud, Telegram workers
│   ├── importer/           # File movement and extraction
│   ├── tagger/             # Rule-based tagging engine
│   ├── ml-analyzer/        # ML audio feature extraction
│   ├── scanner/            # Library scan and sync
│   ├── ultrasonic/         # Android mobile client
│   └── common/             # Shared logic and internal API
├── docs/                   # Detailed documentation and diagrams
└── tools/                  # Utility scripts
```

---

## 📖 Detailed Documentation

For specific information on each module, please refer to their respective READMEs:

- [Ecosystem Architecture](docs/architecture.md)
- [API Specification](docs/api-specification.md)
- [System Overview](docs/OVERVIEW.md)
- [Deployment Guide](docs/deployment.md)
- [Database Schema](docs/database-design.md)
- [Data Flow](docs/system-data-flow.md)
- [Style Guide](docs/styleguide.md)
- [Machine Learning Pipeline](docs/machine-learning.md)

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
