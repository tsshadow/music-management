# 🎵 MuMa Importer – Overview

**MuMa Importer** (formerly Music Importer) is the automated downloading and tagging engine
inside MuMa. It takes care of moving new files from your watch folders into an organised
library with clean metadata.

Whether you're a DJ, a collector, or just someone with a messy `Downloads` folder, MuMa
Importer keeps your collection tidy with minimal manual work. The module lives in
`modules/importer` inside the repository and can be developed independently from the other
MuMa services.

---

## 🚀 What Does It Do?

MuMa Importer automates the following stages:

1. **Download**
   * YouTube channel/playlist harvesting.
   * SoundCloud artist/track downloads with throttle management.
   * Manual archive ingestion (ZIP/RAR sources such as 1gabba).
2. **Unpack**
   * Extracts `.zip`/`.rar` archives, flattens nested folders, and normalises file names.
3. **Tag**
   * Writes MP3/FLAC/M4A tags (title, artist, genre, year, BPM, etc.).
   * Detects track length and applies smart rules to fill in missing info.
   * Supports custom metadata dictionaries for remixers, genres, and labels.
4. **Move**
   * Places tagged files into a clean folder hierarchy while preventing duplicates.
5. **Archive**
   * Maintains a download archive database for supported platforms.

---

## 🔧 Built With

* Python 3
* `yt-dlp` for downloading
* `mutagen` for audio tagging
* `librosa` for BPM detection
* MariaDB or SQLite for archive and metadata storage

---

## 🔐 Security

The API restricts cross-origin requests to trusted origins through CORS middleware. For
production deployments place the service behind a reverse proxy (e.g. Nginx) and enable HTTP
Basic Authentication.

Set the `API_KEY` environment variable to require clients to include the key via the
`X-API-Key` header (REST) or `api_key` query parameter (WebSocket).

---

## 👨‍💻 Who Is It For?

* Personal automation workflows.
* Power users who regularly import music from multiple sources.

---

## ⚙️ Configuration

The importer now reads configuration from a centralized store that merges environment variables, persisted JSON, and live updates from the web UI.

### Environment variables

Environment variables still provide the bootstrap defaults when running in containers:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8001` | HTTP port for the API and static frontend |
| `DB_HOST` | – | Database host name |
| `DB_PORT` | `3306` | Database port |
| `DB_USER` | – | Database user |
| `DB_PASS` | – | Database password |
| `DB_DB` | – | Database name |
| `API_KEY` | – | Optional shared secret required by clients |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed origins |

Other variables exist for downloaders (Discogs, Spotify, Telegram, YouTube). Set them in your `.env` file or container definition to provide initial values.

### Web configurator

Configuration is also editable at runtime through the REST API and Svelte UI:

* `GET /api/config` returns the schema (group, type, description) and current values.
* `PATCH /api/config` validates updates, writes them to `data/config.json`, and notifies listeners so downloaders immediately pick up the new settings.

The dashboard includes a **Configuration** panel with grouped forms. Update folder paths, API tokens, or feature flags, press **Save changes**, and the backend switches to the new values without restarts.

---

## 🐳 Running with Docker

Build the production image and expose it on the desired port:

```bash
docker build -t muma-importer .
docker run -p 8001:8001 \
  -e DB_HOST=db -e DB_PORT=3306 -e DB_USER=muma_importer \
  -e DB_PASS=muma_importer -e DB_DB=muma_importer \
  muma-importer
```

### docker-compose example

```yaml
version: "3.9"
services:
  db:
    image: mariadb:11
    environment:
      MARIADB_ROOT_PASSWORD: rootpass
      MARIADB_DATABASE: muma_importer
      MARIADB_USER: muma_importer
      MARIADB_PASSWORD: muma_importer
    volumes:
      - db_data:/var/lib/mysql

  importer:
    build: .
    depends_on:
      - db
    environment:
      DB_HOST: db
      DB_PORT: 3306
      DB_USER: muma_importer
      DB_PASS: muma_importer
      DB_DB: muma_importer
      # API_KEY: choose-a-secret
    ports:
      - "${PORT:-8001}:${PORT:-8001}"

volumes:
  db_data:
```

Use the `PORT` variable to run multiple instances side-by-side and override any other
variables as needed for your setup.
