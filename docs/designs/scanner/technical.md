# Scanner — Technical Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This document implements the already-agreed [functional.md](functional.md).

## Data Model

The scanner interacts with the following MariaDB tables in the `music_management` database:

### Library Domain
- **`library_tracks`**: Central entity for a song.
    - `track_uid`: SHA-256 hash of `title-duration-primary_artist_id` for de-duplication across different files.
- **`library_media_files`**: Links physical files to tracks.
    - `file_path_hash`: SHA-256 hash of the absolute file path (Primary Key).
    - `file_mtime`, `file_size`: Used for change detection.
- **`library_artists`**: Stores canonical artist names.
- **`library_labels`**: Stores canonical label names.
- **`library_track_artists`**: Junction table for many-to-many artist relationships.
    - `role`: Either `primary` or `featuring`.
    - `position`: Integer indicating the order of artists.
- **`library_track_labels`**: Junction table for many-to-many label relationships.

### Downloader Domain (for Redownload)
- **`downloads_soundcloud_archive`**: Checked by filename to find original SoundCloud URLs.
- **`downloads_youtube_archive`**: Checked by filename to find original YouTube URLs.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/scanner/health` | N/A | `{"status": "OK", "busy": bool}` | |
| `POST /api/scanner/scan/all` | Query: `force: bool` | `{"message": "Full library scan started..."}` | `409 Conflict`: If another scan is already running. |
| `POST /api/scanner/scan/file` | Query: `path: str`, `force: bool` | `{"message": "Scan for ... completed"}` | |
| `POST /api/library/tracks/{id}/redownload` | Path: `track_id: int` | `{"status": "ok", "message": "Redownload started..."}` | `404 Not Found`: Track ID not in media files.<br>`400 Bad Request`: Source URL not found in archives. |
| `POST /api/library/tracks/rerun-parse-path` | Query: `path: str` | `{"status": "ok", "message": "..."}` | Proxies to `scanner_manager.scan_single`. |

## Cross-App Impact

- **`music-manager`**: Contains the `ScannerManager` class (in `routers/scanner.py`) which implements the recursive walk and metadata extraction using `ReadonlySong`.
- **`frontend`**: Uses the scanner API to trigger manual scans and display library sync status.
- **LMS (Logitech Media Server)**: The custom Svelte UI in LMS uses the `rerun-parse-path` endpoint to ensure the management database stays in sync with file updates made through the UI.

## Technical Acceptance Criteria

1. `ScannerManager.run_full` recursively traverses the `music_folder_path` and correctly ignores hidden files/directories.
2. `ScannerManager.process_file` avoids redundant database updates by comparing the current file's `mtime` and `size` against the `library_media_files` record (unless `force=True`).
3. `ReadonlySong` (inheriting from `BaseSong`) is used to read metadata without any risk of writing back to the files during a scan.
4. The `ScannerManager` uses a `threading.Lock` to ensure only one scan operation (full or single) runs at a time.
5. Redownload tasks are passed to `BackgroundTasks` to ensure the API remains responsive while `yt-dlp` or the SoundCloud downloader runs.
6. Database connections are reliably returned to the pool via `finally` blocks, even if metadata extraction fails for a specific file.
7. The `POST /api/scanner/scan/file` endpoint is verified by the `tests/contracts/test_listen_scrobble_flow.py` contract test, which uses it to prepare the environment.

## Related Docs

- `docs/architecture.md` (Domain definitions)
- `docs/database-design.md` (Table schemas)
- `services/music_manager/routers/scanner.py` (Core implementation)
- `services/music_manager/routers/library.py` (Redownload logic)
- `services/scanner/Song/ReadonlySong.py` (Metadata extraction)
