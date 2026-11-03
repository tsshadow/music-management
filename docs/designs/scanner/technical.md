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
- **`library_track_channels`**: The channel (SoundCloud/YouTube/Telegram account) a file arrived
  through, read from its path.

### Label and channel links are recomputed, not accumulated
`process_file` replaces a track's `library_track_labels` and `library_track_channels` rows with the
set its files support today: the file being scanned, plus every other `library_media_files` row of
the same track (the other files' tags are read, their channel comes from their path). A file that
is gone from disk supports nothing. A file that exists but cannot be read might still name a label,
so then label links are only added, never removed. Until bug report 042 these were INSERT IGNORE
only, and a corrected publisher kept its old label link for good.

### Relink rule: a file that moves to another track row
`track_uid` changes with the title and the primary artist, so a retag gives the same file a new
track row. When `process_file` repoints a media file from track A to track B:

- If A still has another media file, A stays; only its label/channel links are recomputed.
- Otherwise `track_relink.relink_track` merges A into B and deletes A, in one explicit transaction
  together with the media-file repoint (the pool runs `autocommit=True`, so `conn.begin()` is what
  makes it one unit). Since bug report 062 that transaction is opened for every scanned file, not only
  a moving one, and also covers the delete-and-reinsert of the artist, genre, label and channel links
  (`database.transaction`, see [the transactions design](../db-transactions/technical.md)):
  - `rating_tracks` rows keyed on A's `track_uid` move to B's; when a user rated both, the row with
    the newer `updated_at` wins. `updated_at` is preserved, not bumped.
  - `scrobble_listens.track_id` moves with UPDATE IGNORE; a listen B already has at the same
    `listened_at` is a duplicate and is dropped. `listened_at` is preserved explicitly.
  - `library_track_audio_features.internal_track_id` and `library_track_ml_labels`
    (`internal_track_id`, and `track_id` which holds the `track_uid`) follow.
  - A work pinned to A is pinned to B with its canonical cleared, so the song-version worker's next
    pass decides after assigning B a work; a work whose computed canonical was A is recomputed at once.
  - The junction tables cascade with A. `radio_timeline` (LMS ids) and `feeds_snapshot` (a daily
    cache) are deliberately not touched.
- The song-version worker only ever picks a track that has a media file as canonical.

Rows orphaned before this rule existed are repaired by `POST /api/scanner/relink-orphans`
(`track_relink.relink_orphaned_tracks`). An orphan is relinked only when exactly one track with a
file has the same normalised title and duration (within 0.5 s) and either the same primary artist
or the same set of artists (the metadata key). Failing that, the file-name key applies: the
orphan's title is exactly the basename-without-extension of the files of one single track. The
first scan in May 2026 stored the raw file name as title with no artist or duration, and that name
is the one thing that still identifies those rows (bug report 104). The stem index is built once
per run from `library_media_files`. A stem that several tracks share is ambiguous and never
guessed at. `?dry_run=1` counts per key without writing.

What neither key matches is handled by `POST /api/scanner/purge-orphans`
(`orphan_purge.purge_orphaned_tracks`). It deletes an orphan only when no listen, no rating, no
work pin and no reviewed ml label points at it, in batches of 1000 with every guard re-checked
under `FOR UPDATE`. Referenced orphans are listed for a person. Neither endpoint ever runs
automatically.

### Vanished files: the media row of a file gone from disk
A release folder that moves or is deleted used to leave its `library_media_files` rows behind, with
the right hash and no file: 8,372 of 354,222 rows on production on 2026-10-03 (GitLab issue #170).
After every full walk, still inside the scan lock, `run_full` calls
`vanished_media.drop_vanished_media(conn, music_path, seen)`. `seen` is every file path the walk
met, scanned or not.

1. Candidates: every row whose hash is `SHA2(file_path, 256)` and whose path is under the music
   root, and that the walk did not see. A row with a wrong hash is bug report 093's, and
   `stale_media_rows.py` folds it into its live track instead.
2. A listing of each candidate's folder decides if the file is gone
   (`services/common/vanished_files.gone_paths`, shared with that script's `--gone` pass). A
   hidden folder the walk skips is settled here too.
3. Guards. Each raises `LibraryUnreadable`, the pass logs a WARNING, and nothing is deleted:
   - a library folder (the first folder below the music root) is missing or empty;
   - a folder cannot be listed for any reason except that it does not exist;
   - more than `MAX_GONE_SHARE` (10%) of the rows under the root are gone.
4. Per track, in one transaction: each gone row is locked (`FOR UPDATE`), re-checked (same path,
   nothing at that path, `os.path.lexists`) and deleted. The track row is never deleted here.
5. A track that loses its last file is relinked at once when the metadata key of
   `relink-orphans` finds exactly one successor (`track_relink.find_relink_target`, index built
   once per pass, tracks the same pass leaves fileless excluded). That is a file moved and retagged
   in one go. Any other fileless track stays for `relink-orphans` and `purge-orphans`.

A move with unchanged tags needs no relink: the walk gives the new path a row on the same track
(same `track_uid`) before the pass runs, so the track keeps a file. One INFO line (an event) is
logged when a row was deleted or a track failed.

The pass is off by default (`scanner_drop_vanished_media`, config). The first deploy removes
nothing. The 8,372-row backlog goes through `merge-stale-media-rows.sh --gone`
first, because that script writes a JSON backup and the scanner does not. After that, a curator
switches the pass on in Management > Configuration.

### Downloader Domain (for Redownload)
- **`downloads_soundcloud_archive`**: Checked by filename to find original SoundCloud URLs.
- **`downloads_youtube_archive`**: Checked by filename to find original YouTube URLs.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/scanner/health` | N/A | `{"status": "OK", "busy": bool}` | |
| `POST /api/scanner/scan/all` | Query: `force: bool` | `{"message": "Full library scan started..."}` | `409 Conflict`: If another scan is already running. |
| `POST /api/scanner/scan/file` | Query: `path: str`, `force: bool` | `{"message": "Scan for ... completed"}` | |
| `POST /api/scanner/relink-orphans` | Admin key; query `dry_run: bool` | `{"message": "...", "dry_run": bool, "last": {...}\|null}` | `403`: not an admin.<br>`409`: a scan, relink or purge is running. |
| `GET /api/scanner/relink-orphans` | Admin key | `{"running": bool, "keys": [...], "dry_run_supported": true, "progress": {...}\|null, "last": {...}\|null}` | `403`: not an admin. |
| `POST /api/scanner/purge-orphans` | Admin key; query `dry_run: bool` | `{"message": "...", "dry_run": bool, "last": {...}\|null}` | `403`: not an admin.<br>`409`: a scan, relink or purge is running. |
| `GET /api/scanner/purge-orphans` | Admin key | `{"running": bool, "progress": {...}\|null, "last": {...}\|null}` (`last.kept_list` names the kept orphans) | `403`: not an admin. |
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
