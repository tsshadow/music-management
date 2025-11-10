# MuMa – Music Management

MuMa (Music Management) combines the original Scrobbler and Music Importer projects into a
single monorepo. The goal is to provide a cohesive toolchain for collecting, analysing,
organising, and tagging music libraries.

## Repository layout

```
modules/
  importer/      # Automated downloading and importing pipeline (former Music Importer)
  scrobbler/     # Scrobbling API, web UI, and analyzer worker
```

Planned modules that will join later:

* `modules/analyzer` – shared analysis jobs that power recommendations and tagging.
* `modules/tagger` – dedicated tagging utilities lifted from the Music Importer project.

## Continuous integration

GitHub Actions (`.github/workflows/muma-ci.yml`) orchestrates the shared CI pipeline:

* Python unit and integration tests for the Scrobbler backend.
* Frontend build for the Scrobbler web application.
* Python unit tests (with coverage) for the Importer.
* Vitest suite for the Importer frontend.
* Multi-platform Docker builds for each deployable module. Images are tagged for GitHub
  Container Registry, and optionally Docker Hub when credentials are provided.

Every job runs from its module directory so individual dependency managers continue to work
unchanged inside the monorepo.

## Developing MuMa locally

Each module retains its native tooling.

### Importer module

```bash
cd modules/importer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m unittest
```

The Importer web UI lives in `modules/importer/frontend` and is a SvelteKit project managed
with pnpm.

### Importer configuration

The importer exposes a runtime configuration service backed by a persisted store.

* `GET /api/config` returns the available fields with metadata, defaults, and current values.
* `PATCH /api/config` validates updates, saves them to `data/config.json`, and notifies listeners so downloaders pick up changes immediately.

The Svelte dashboard contains a **Configuration** panel that consumes these endpoints. Adjusting values in the UI lets you tweak paths, downloader credentials, or feature flags without bouncing the importer process.

### Scrobbler module

```bash
cd modules/scrobbler
poetry install
poetry run pytest
```

The frontend for Scrobbler is inside `modules/scrobbler/frontend` and uses pnpm.

### Docker builds

Each module ships its own Dockerfile. From the repository root run, for example:

```bash
docker build -f modules/scrobbler/docker/Dockerfile -t muma-scrobbler modules/scrobbler
docker build -f modules/importer/Dockerfile -t muma-importer modules/importer
```

## Documentation

Module specific documentation lives alongside the source code:

* `modules/scrobbler/README.md`
* `modules/importer/README.md`

These guides were updated to reflect the MuMa naming and directory layout.
