# Tagger — Technical Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This document implements the already-agreed [functional.md](functional.md).

## Data Model

The Tagger interacts with several tables in the MariaDB `music_management` database to facilitate artist normalization and genre inference. These are managed via `TableHelper` and `FilterTableHelper` in `services/common/Helpers/`.

| Table | Purpose | Fields Used |
|---|---|---|
| `library_artists` | Master list of known artists. | `name` |
| `rules_ignored_artists` | Artists to be ignored or automatically corrected. | `name`, `corrected_name` |
| `rules_genres` | Master list of allowed genres. | `name`, `corrected_genre` |
| `rules_ignored_genres` | Genres to be stripped from tracks. | `name` |
| `rules_genre_backlog` | Unknown genres found during tagging, for manual review. | `genre` |
| `artist_genres` (via helper) | Mapping of artists to their primary genres. | N/A (Abstraction) |
| `subgenres` (via helper) | Mapping of subgenres to main genres. | N/A (Abstraction) |

## API Contract

The Tagger API is hosted by the `music-manager` service on port 8000.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/tagger/health` | None | `{ "status": "OK", "busy": boolean }` | None |
| `POST /api/tagger/tag/all` | None | `{ "message": "Full tagging run started in background" }` | `409 Conflict`: A tagging operation is already in progress. |
| `POST /api/tagger/tag/stop` | None | `{ "message": "Stop request sent to tagger" }` | None (Returns 200 even if no run is active). |
| `POST /api/tagger/tag/file` | `?path=string` | `{ "message": "Tagging for <path> completed" }` | `404 Not Found`: File does not exist. <br> `500 Internal Server Error`: Parsing failed. |

## Cross-App Impact

- **`music-manager`**: Primary host of the tagger logic and API.
- **`downloader`**: Passes metadata to `TagSingleFile` via `extra_info` after downloading a track.
- **`importer`**: Calls the tagger to enforce standards on imported label promo pools.
- **`scanner`**: Often triggered after a tagging run to synchronize updated file metadata back to the main library database.

## Technical Acceptance Criteria

1. **Auto-detection**: `TagSingleFile` correctly identifies `SongTypeEnum` based on the file's absolute path relative to `eps_folder_path` and `music_folder_path` settings.
2. **Rule Execution**: `BaseSong.run_all_rules()` executes all registered `TagRule` objects in sequence; rules must not interfere with each other's intermediate state unless intended (e.g., `CleanTagsRule` running multiple times).
3. **File Support**: The system correctly reads and writes tags for MP3 (EasyID3), FLAC, WAV, M4A (MP4), and OPUS using the `mutagen` library.
4. **Concurrency**: The `TaggerManager` in `music-manager` uses a `threading.Lock` to ensure only one full tagging run or single-file tagging operation occurs at a time, preventing file access conflicts.
5. **Unicode Normalization**: `ReplaceInvalidUnicodeRule` identifies and replaces zero-width spaces, non-breaking spaces, and other problematic characters with their standard ASCII/UTF-8 equivalents.
6. **Error Handling**: Failed tagging operations for individual files are logged and added to the `broken_song_helper` (persisted to `broken-files.log`) without stopping the entire batch run.
7. **Idempotency**: Running the tagger multiple times on the same file with no rule changes results in no changes to the file's modification time (mtime) after the first successful pass, handled via `ProcessedFilesHelper`.

## Related Docs

- [docs/architecture/responsibilities.md](../../architecture/responsibilities.md) — Data boundaries between services.
- [docs/api-specification.md](../../api-specification.md) — Full API reference for `music-manager`.
- [services/tagger/README.md](../../../services/tagger/README.md) — Detailed list of tagging rules and their logic.
