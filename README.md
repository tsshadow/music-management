# Scrobbler

Scrobbler is a FastAPI-based service that ingests listens from LMS/Open Subsonic compatible clients and provides analytics with a lightweight Svelte frontend.

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│     Frontend        │     │      Backend        │
│  Vite + Svelte      │◀──▶ │  FastAPI + SQLA     │
│  (static assets)    │     │  MariaDB / SQLite   │
└─────────────────────┘     └─────────────────────┘
          ▲                            ▲
          │ REST API                   │ Async SQLAlchemy
          ▼                            ▼
                            ┌─────────────────────┐
                            │   MariaDB Database  │
                            └─────────────────────┘
```

## Getting started

### Prerequisites

* Python 3.11+
* Node 20+
* MariaDB 11+ (or SQLite for development/tests)

### Backend (development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install poetry
poetry install
uvicorn backend.app.main:app --reload
```

Set `SCROBBLER_DB_DSN` to point to your MariaDB instance, e.g. `mysql+asyncmy://user:pass@localhost:3306/music-scrobbler`. By default the app uses SQLite (`sqlite+aiosqlite:///./scrobbler.db`).

### Frontend (development)

```bash
cd frontend
npm install
npm run dev
```

The dev server runs on <http://localhost:5173>. Configure `SCROBBLER_CORS_ORIGINS=http://localhost:5173` when running the backend.

### Running tests

```bash
pytest
```

To run integration tests against MariaDB, set `IT_MARIADB_DSN` and provide a running database.

### Docker

Build and run with Docker Compose:

```bash
docker-compose up --build
```

This starts both MariaDB and the FastAPI service (serving the built frontend). The backend listens on port 8080.

### API

* `POST /api/v1/scrobble` – ingest JSON payloads
* `GET /rest/scrobble.view` – Subsonic-compatible scrobble
* `GET /api/v1/listens/recent?limit=10` – last listens
* `GET /api/v1/listens/count` – total count
* `DELETE /api/v1/listens` – remove all stored listens
* `GET /api/v1/stats/*` – analytics endpoints
* `GET/PUT /api/v1/config` – configuration
* `POST /api/v1/import/listenbrainz` – import ListenBrainz history

OpenAPI docs are available at `/docs`.

### Configuration keys

* `default_user`
* `api_key`
* `lms_source_name`
* `listenbrainz_user`
* `listenbrainz_token`

Values are persisted in the database via `/api/v1/config`.

### ListenBrainz import

Trigger an initial ListenBrainz import via:

```bash
curl -X POST http://localhost:8080/api/v1/import/listenbrainz \
  -H 'Content-Type: application/json' \
  -d '{"user": "listenbrainz-user", "page_size": 200}'
```

If `listenbrainz_user` and `listenbrainz_token` are set in `/api/v1/config` you may omit them in the payload. Imports are idempotent;
re-running the command skips previously stored listens.

To wipe the listen history and start a fresh import, call `DELETE /api/v1/listens`. Exporting data back to ListenBrainz is not supported yet.

### Verifying ListenBrainz genres

If you want to double-check whether a listen actually has genre tags upstream, see [`docs/listenbrainz_genre_endpoints.md`](docs/listenbrainz_genre_endpoints.md) for ready-to-run API calls against ListenBrainz (and the underlying MusicBrainz data) that surface the `additional_info.tags` values used during imports.

### Example JSON scrobble

```json
{
  "user": "user",
  "source": "lms",
  "listened_at": "2024-01-01T12:00:00Z",
  "position_secs": 148,
  "duration_secs": 312,
  "track": {
    "title": "My Track",
    "album": "My Album",
    "album_year": 2024,
    "track_no": 3,
    "disc_no": 1
  },
  "artists": [
    { "name": "Main Artist", "role": "primary" },
    { "name": "DJ X", "role": "remixer" }
  ],
  "genres": ["Uptempo Hardcore", "Hardcore"]
}
```

### Subsonic scrobble

```
GET /rest/scrobble.view?u=alice&id=track123&time=1712516400000&t=Song&a=Artist&al=Album&g=Chill
```

### Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `SCROBBLER_DB_DSN` | `sqlite+aiosqlite:///./scrobbler.db` | Database DSN |
| `SCROBBLER_API_KEY` | *(empty)* | Optional API key to require via `X-Api-Key` |
| `SCROBBLER_LOG_LEVEL` | `INFO` | Logging level |
| `SCROBBLER_CORS_ORIGINS` | *(empty)* | Comma separated origins |
| `SCROBBLER_LISTENBRAINZ_BASE_URL` | `https://api.listenbrainz.org/1` | ListenBrainz API endpoint |
| `SCROBBLER_MUSICBRAINZ_BASE_URL` | `https://musicbrainz.org/ws/2` | MusicBrainz API endpoint for fallback tags |
| `SCROBBLER_MUSICBRAINZ_USER_AGENT` | `scrobbler/1.0 (+https://github.com/)` | User agent for MusicBrainz requests |

## Project layout

See repo structure for backend, frontend, and Docker artefacts. Built frontend assets are copied into `backend/app/static` during the Docker build.

## License

MIT
