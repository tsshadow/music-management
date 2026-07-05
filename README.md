# 🎵 Music Management System

A comprehensive, modular system for automated music library management, including downloading, rule-based tagging, ML analysis, and listening history tracking (scrobbling).

## 🧩 Modular System Architecture

The project has been refactored into specialized, lightweight Docker containers sharing a common base image. This ensures high performance and easy maintenance.

### Core Images
- **`music-manager`**: The central "Music Manager" & "Control Center". Consolidates management, authentication, ratings, scrobbling, and stats into a single FastAPI service.
- **`muma-base`**: Shared foundation containing core music logic and common dependencies.

### Specialized Workers
- **`muma-scanner`**: High-performance library scanning and database synchronization.
- **`muma-tagger`**: Rule-based metadata enforcement and genre inference engine.
- **`muma-downloader`**: Automated fetches from YouTube and SoundCloud.
- **`muma-telegram`**: Dedicated worker for Telegram-based music discovery.
- **`muma-importer`**: Archive extraction and automated file movement.
- **`muma-ml-analyzer`**: Machine learning pipeline for BPM, key, and mood detection.

### Utility
- **`muma-tools`**: Collection of maintenance and database utility scripts.

---

## 🏗 Project Modules
The core of the system that handles the lifecycle of music files:
- **Downloaders**: Automated fetching from YouTube, SoundCloud, and Telegram.
- **Importer**: Monitors incoming files, extracts archives, and moves them to the library.
- **Tagger**: A rule-based engine that cleans metadata, guesses missing tags (artist, title, genre) from filenames, and enforces library standards.
- **Common**: Shared utilities and the internal API.

### 2. Music Manager (`services/music_manager`)
A central dashboard and API for the system:
- Consolidates management, authentication, ratings, scrobbling, stats, and artist image enrichment.
- Provides a unified API endpoint for frontends and external services.
- View release notes, track system versions, and manage system status.
- Integrates the **Artist Image Fetcher** for high-quality metadata enrichment.

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
  - **New**: Use `--semi-remote` to offload heavy builds (`app`, `ml`, `tools`) to the remote LXC container (192.168.1.40).
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
- **Music Manager / Control Center**: Port 8000 (main API) / 8003 (Dashboard)
- **phpMyAdmin**: Port 8002 (to inspect the database)
- **Firefox (GUI)**: Port 7003

---

## 🛠 Docker Stack Management

The system is split into modular Docker Compose files for better resource management:

1. **`docker-compose.yml`**: Core infrastructure (MariaDB, phpMyAdmin, Control Center).
2. **`docker-compose.workers.yml`**: Background workers (Importer, YouTube/SoundCloud/Telegram downloaders, Tagger).
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
├── services/               # Backend microservices
│   ├── music_manager/      # Consolidated Core API & Dashboard
│   │   ├── artist_image_fetcher/ # Artist image enrichment logic
│   │   └── frontend/       # Svelte-based Control Center
│   ├── downloader/         # YouTube, SoundCloud, Telegram workers
│   ├── importer/           # File movement and extraction
│   ├── tagger/             # Rule-based tagging engine
│   ├── ml-analyzer/        # ML audio feature extraction
│   ├── scanner/            # Library scan and sync
│   └── common/             # Shared logic and internal API
├── modules/                # Specialized/Standalone modules
├── docs/                   # Detailed documentation and diagrams
└── tools/                  # Utility scripts
```

---

## 📖 Detailed Documentation

For specific information on each module, please refer to their respective READMEs:

- [Ecosystem Architecture](docs/architecture.md)
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
