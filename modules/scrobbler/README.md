# Scrobbler

Scrobbler is a FastAPI-based service that ingests listens from LMS/Open Subsonic compatible clients and provides analytics with a lightweight Svelte frontend.

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│     Frontend        │     │   Scrobbler API     │
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

### Scrobbler API (development)

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

The dev server runs on <http://localhost:5173>. Configure `SCROBBLER_CORS_ORIGINS=http://localhost:5173` when running the Scrobbler API.

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

This starts MariaDB, phpMyAdmin, and the FastAPI service (serving the built frontend). The Scrobbler API listens on port 8080 and phpMyAdmin is available at <http://localhost:8081>.

Docker images are published for every commit. The `latest` tag always tracks the current `main` branch while `latest-beta` is updated on every successful build (including pull requests). Use the `latest-beta` tag if you want to automatically roll out the most recent build.

#### Automatic updates with Watchtower

The included `docker-compose.yml` defines a [Watchtower](https://containrrr.dev/watchtower/) service that monitors the Scrobbler containers and upgrades them whenever a new image tagged `latest-beta` is available. Watchtower prunes superseded images (`--cleanup`) and polls for updates every five minutes. Disable the service or remove the `com.centurylinklabs.watchtower.enable=true` labels if you prefer to manage updates manually.

### Analyzer background jobs

Large media libraries can take longer than the default RQ timeout (three minutes) to scan. Set `SCROBBLER_ANALYZER_SCAN_JOB_TIMEOUT` to the number of seconds the `scan_library_job` may run (defaults to six hours). Increase the value if your library scan routinely exceeds the default window. The same timeout can be overridden at runtime by storing an `analyzer_scan_job_timeout` value (in seconds) through `/api/v1/config`. Enable the `split_paths` flag when calling `/api/v1/analyzer/library/scan` to enqueue one job per root path so multiple workers can process the library in parallel. See `docs/analyzer-jobs.md` for a walkthrough of the scan workflow and tuning options.

### API

* `POST /api/v1/scrobble` – ingest JSON payloads
* `GET /rest/scrobble.view` – Subsonic-compatible scrobble
* `GET /api/v1/listens/recent?limit=10` – last listens
* `GET /api/v1/listens/count` – total count
* `DELETE /api/v1/listens` – remove all stored listens
* `GET /api/v1/stats/*` – analytics endpoints
* `GET/PUT /api/v1/config` – configuration
* `POST /api/v1/enrichment` – queue analyzer enrichment for stored listens
* `POST /api/v1/import/listenbrainz` – import ListenBrainz history
* `POST /api/v1/export/listenbrainz` – export stored listens to ListenBrainz

New listens automatically queue the analyzer's enrichment job so freshly imported
scrobbles are merged with the media library. The scrobble endpoint returns an
`enrich_job_id` when a job is queued, and ListenBrainz imports include the
timestamp of the earliest newly created listen alongside the queued job id.
You can also trigger an enrichment pass manually from the UI or by calling
`POST /api/v1/enrichment`.

OpenAPI docs are available at `/docs`.

### Configuration keys

* `default_user`
* `api_key`
* `lms_source_name`
* `listenbrainz_user`
* `listenbrainz_token`
* `analyzer_scan_job_timeout`

Values are persisted in the database via `/api/v1/config`.

### ListenBrainz import

Trigger an initial ListenBrainz import via:

```bash
curl -X POST http://localhost:8080/api/v1/import/listenbrainz \
  -H 'Content-Type: application/json' \
  -d '{"user": "listenbrainz-user", "page_size": 200}'
```

If `listenbrainz_user` and `listenbrainz_token` are set in `/api/v1/config` you may omit them in the payload. Imports are idempotent;
re-running the command skips previously stored listens and links the original rows to the media library when matching metadata becomes available.

For existing datasets you can call the backend `DeduplicationService` to merge duplicate listens that share a timestamp and preserve the best available metadata. The service is registered on the FastAPI application state as `deduplication_service` for use in scripts or admin endpoints.

To wipe the listen history and start a fresh import, call `DELETE /api/v1/listens`.

### ListenBrainz export

You can push listens back to ListenBrainz using:

```bash
curl -X POST http://localhost:8080/api/v1/export/listenbrainz \
  -H 'Content-Type: application/json' \
  -H 'X-Api-Key: $API_KEY' \
  -d '{"listen_type": "import", "batch_size": 100}'
```

The API reuses the configured `listenbrainz_user` and `listenbrainz_token` unless overridden in the payload. Listens are exported in chronological batches (up to 100 per request by default) and the response reports how many entries were submitted and skipped.

### Verifying ListenBrainz genres

If you want to double-check whether a listen actually has genre tags upstream, see [`docs/listenbrainz_genre_endpoints.md`](docs/listenbrainz_genre_endpoints.md) for ready-to-run API calls against ListenBrainz (and the underlying MusicBrainz data) that surface the `additional_info.tags` values used during imports.

### Example JSON scrobble

```json
{
  "user": "teun",
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

GNU-AGPL 3.0
