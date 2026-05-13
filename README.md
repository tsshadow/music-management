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

---

## 🚀 Getting Started

The easiest way to run the entire stack is using Docker Compose.

### Prerequisites
- Docker and Docker Compose
- A MariaDB/MySQL database (included in compose)

### Quick Start
1. Clone the repository.
2. Copy `.env.example` to `.env` and configure your paths and database credentials.
3. Start the services:
   ```bash
   docker-compose -f work-context/docker-compose.yml up -d
   ```

The following services will be available:
- **Music Management API**: Port 7001
- **Scrobbler API**: Port 8080
- **phpMyAdmin**: Port 8002 (to inspect the database)

---

## 📂 Repository Structure

```text
├── services/               # Backend microservices
│   ├── downloader/         # YouTube, SoundCloud, Telegram workers
│   ├── importer/           # File movement and archive extraction
│   ├── tagger/             # Rule-based metadata tagging engine
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
