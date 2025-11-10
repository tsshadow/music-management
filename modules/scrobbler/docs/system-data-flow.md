# Analyzer and Scrobbler Data Flow

This document summarizes how the analyzer and scrobbler modules interact with the data layer. The services can operate on dedicated schemas (`medialibrary` and `listens`) that isolate ownership while keeping cross-links through foreign keys. Set `SCROBBLER_MEDIALIBRARY_SCHEMA` / `SCROBBLER_LISTENS_SCHEMA` to enable the physical split; leaving them blank keeps both domains inside the connection's default schema.

## Analyzer responsibilities

- The analyzer scans configured filesystem paths, walking through directories, filtering supported audio extensions, and recording file metadata. Each discovered media file is registered through the `LibraryService`, which persists entries in the library tables inside the `medialibrary` schema (`media_files`, `tracks`, `artists`, `genres`, etc.).【F:analyzer/ingestion/filesystem.py†L1-L46】【F:analyzer/services/library_service.py†L14-L93】【F:docs/database-design.md†L7-L119】
- Analyzer jobs enrich canonical metadata (artists, albums, tracks, genres) and update analyzer dashboards that query the normalized library content (e.g., `/api/v1/analyzer/summary`). These dashboards only surface rows that have associated track records in `medialibrary` tables.【F:analyzer/db/repo.py†L500-L610】【F:docs/database-design.md†L121-L150】【F:frontend/src/routes/Analyzer.svelte†L1-L67】

## Scrobbler responsibilities

- The scrobbler ingests ListenBrainz (or similar) payloads. During ingestion it normalizes artist, album, genre, and track metadata, looks up matching rows in `medialibrary`, and records listens inside the `listens` schema with the resolved identifiers (or raw strings when no canonical match exists).【F:backend/app/services/ingest_service.py†L1-L88】【F:backend/app/db/maria.py†L116-L219】【F:docs/database-design.md†L74-L87】
- Scrobbler UI pages focus on listening history, pulling listen records and aggregations from the tables scoped to the `listens` schema (`listens`, `listen_artists`, `listen_genres`, etc.).【F:frontend/src/routes/Scrobbler.svelte†L1-L105】【F:docs/database-design.md†L133-L150】

## Combined behavior

- Running only the analyzer populates library metadata in `medialibrary` but does not create listen events because no ingestion job is performed.【F:analyzer/services/library_service.py†L14-L93】【F:docs/database-design.md†L121-L150】
- Running only the scrobbler stores listens tied to existing library entries when possible and falls back to the raw metadata when the analyzer has not populated a matching track yet.【F:backend/app/services/ingest_service.py†L1-L88】【F:backend/app/db/maria.py†L429-L520】【F:docs/database-design.md†L74-L87】
- When both services run, listens and library metadata share track identifiers, enabling enriched listening history that links to canonical metadata throughout the UI. Maintaining the `listens.listens.track_id → medialibrary.tracks.id` relationship preserves this linkage during and after the migration.【F:backend/app/services/ingest_service.py†L39-L81】【F:analyzer/db/repo.py†L500-L610】【F:docs/database-design.md†L133-L150】
- Newly ingested listens (via scrobbles or ListenBrainz imports) queue the analyzer's `enrich_listens_job` so unmatched entries are merged with the media library without manual intervention.【F:backend/app/api/routes_scrobble.py†L1-L32】【F:backend/app/api/routes_import.py†L1-L59】【F:backend/app/services/enrichment_queue_service.py†L1-L24】
- Operators can manually trigger the same enrichment job through `/api/v1/enrichment`, which exposes a lightweight endpoint for the UI to re-queue reconciliation whenever desired.【F:backend/app/api/routes_enrichment.py†L1-L28】【F:frontend/src/routes/Scrobbler.svelte†L1-L176】
