# MuMa – Music Management

MuMa (Music Management) now ships as a consolidated application: a single FastAPI backend that
powers importer automation and scrobbler/analyzer features, and a unified SvelteKit control centre
for operations. The legacy module directories remain for reference, but the `apps/` folder contains
all actively maintained code.

## Repository layout

```
apps/
  api/   # Shared FastAPI application with importer + scrobbler routers
  web/   # SvelteKit dashboard that talks to the combined backend
modules/
  importer/   # Historical importer implementation (kept for reference/tests)
  scrobbler/  # Historical scrobbler implementation and docs
```

## Running the stack

The recommended way to start MuMa locally is via Docker Compose:

```bash
docker compose build
docker compose up
```

* Backend & frontend: <http://localhost:8000>

The frontend expects `VITE_API_BASE` to point at the API container. The Compose file wires this up
for you. If you run things manually set `VITE_API_BASE=http://localhost:8000/api` before executing
`npm run dev` inside `apps/web`.

## Local development

### Backend

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn apps.api.main:app --reload
```

The importer endpoints now live under `/api/importer` – for example
`POST /api/importer/downloads` queues a new download batch while
`POST /api/importer/tagging` schedules metadata updates. Scrobbler routes keep their `/api/v1`
prefix (for example `/api/v1/stats/overview`).

### Frontend

```bash
cd apps/web
npm install
npm run dev -- --open
```

The dashboard shares a global layout, navigation and theme defined in `src/lib/theme.css` and
`src/lib/ui`. Components are reused across the overview, importer and scrobbler pages to keep the
experience consistent.

### Tests

```bash
# Backend unit tests
cd apps/api
pytest

# Frontend lint/tests
cd apps/web
npm run lint
npm run test
```

## Configuration highlights

* Importer configuration values are exposed via `GET /api/importer/config` and
  `PATCH /api/importer/config`.
* Download batches are created through `POST /api/importer/downloads` with a list of download tasks.
* Tagging runs are created through `POST /api/importer/tagging` with a tagging request payload.
* Job state can be queried via `GET /api/importer/jobs` and streamed with
  `GET /api/ws/jobs/{job_id}`.

## Documentation

Historical documentation for the importer and scrobbler projects is still available under
`modules/importer/README.md` and `modules/scrobbler/README.md`. The combined stack is documented in
this file and the inline component/service docstrings.
