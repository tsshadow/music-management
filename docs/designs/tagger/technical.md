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

## Tag Mapping and Multi-Value Splitting

- **Per-format keys** live in `services/tagger/constants.py` (`MP3Tags`, `FLACTags`, `OPUSTags`,
  `WAVTags`, `MP4Tags`); `TagCollection` reads through the reversed maps, `BaseSong.set_tag` writes
  through the forward ones.
- **m4a atoms.** Standard tags use the iTunes atoms (`©nam`, `©ART`, `©alb`, `aART`, `©gen`, `©day`,
  `cprt`). mutagen writes any atom name outside the `----:` freeform namespace as exactly 4 bytes, so
  every custom name longer than that (`REMIXER`, `ORIGINAL_TITLE`, and every unmapped name via the
  fallback in `_set_m4a_tag`) is a freeform atom `----:com.apple.iTunes:<NAME>`, stored as UTF-8
  bytes and decoded on read. `LEGACY_MP4_ATOMS` lists where older versions wrote four tags (`REMI`,
  `ORIG`, `TALB`, freeform `ALBUM`); they are read when the correct atom is missing and deleted on the
  next save, so files migrate on their next retag (bug report 037).
- **Splitting.** A tag value is split on ';' for every tag. It is split on '/' only for `GENRE`
  (`Tag.SLASH_SPLIT_TAGS`): 'AC/DC' is one artist and 'Live 24/7' one title.
- **Order is identity.** The scanner takes the first artist as the primary one and hashes it into
  `track_uid`, so rules must correct an artist in place (`Tag.replace`), never by appending the
  correction and removing the original.
- **Real-mutagen tests.** `services/tests/mock_base.py` stubs mutagen for all of `services/`; what
  lands on disk is tested in `tests/unit/test_tagger_idempotence.py`, in a child interpreter.

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
