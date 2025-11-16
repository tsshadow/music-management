# Analyzer Job Reference

## `scan_library_job`

`scan_library_job` is responsible for walking configured filesystem roots, extracting audio metadata, and registering media files inside the analyzer's library tables. The job creates an async SQLAlchemy engine, wires up the analyzer services, and delegates the filesystem walk to `scan_paths`. The helper yields track metadata for each supported audio file and stores the payload through the `LibraryService` so artists, releases, tracks, and the raw media file entry stay in sync.【F:analyzer/jobs/handlers.py†L41-L54】【F:analyzer/ingestion/filesystem.py†L23-L86】【F:analyzer/services/library_service.py†L14-L93】

Each run returns a JSON payload containing the number of media files registered in that scan. The job is idempotent: re-running a scan revisits the filesystem and updates metadata without creating duplicate library entries.【F:analyzer/jobs/handlers.py†L41-L54】【F:analyzer/ingestion/filesystem.py†L88-L147】

## Configuring timeouts

The job timeout defaults to six hours (`21,600` seconds) so large libraries are not cancelled prematurely. Operators can override the value via the `SCROBBLER_ANALYZER_SCAN_JOB_TIMEOUT` environment variable or by persisting an `analyzer_scan_job_timeout` key (in seconds) through `/api/v1/config`. The analyzer API resolves the database override on every enqueue, falling back to the environment default when no override is stored or when the value is invalid.【F:backend/app/core/settings.py†L23-L31】【F:backend/app/schemas/config.py†L6-L19】【F:analyzer/api/router.py†L47-L90】

## Parallelising scans

Trigger scans with `POST /api/v1/analyzer/library/scan`. Supplying multiple root paths queues a single job that handles all provided directories. Set `split_paths` to `true` in the request body to enqueue one job per path, allowing multiple workers to process separate root folders in parallel. The endpoint still enforces that at least one path is configured—either from the request payload or from the `SCROBBLER_ANALYZER_PATHS` default list—before queueing work.【F:analyzer/api/router.py†L24-L90】

Large deployments typically combine a generous timeout with `split_paths` to balance throughput and worker utilisation. Extremely large directories can also be split manually (for example, invoking the endpoint for `/music/A-M` and `/music/N-Z`) so each job finishes well within the configured timeout.
