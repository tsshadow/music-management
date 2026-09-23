# Scanner — Functional Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This is the functional (user-observable) half of the library synchronization and redownload feature; the implementation contract is in [technical.md](technical.md).

## Overview

The "Scanner" feature is responsible for keeping the system's database in sync with the physical music library. It traverses the filesystem, extracts metadata from audio files, and populates the library tables (tracks, artists, labels, media files). Additionally, it provides a "Redownload" service that allows re-acquiring tracks from their original sources (SoundCloud or YouTube) if needed.

## User Stories

- As a library administrator, I want to trigger a full scan of my music collection, so that new additions are indexed and metadata updates are reflected in the database.
- As a library administrator, I want to scan a specific file immediately after I've updated its tags or moved it, so that the changes are instantly available in the management UI.
- As a user, I want to trigger a redownload of a track that I previously downloaded from SoundCloud or YouTube, so that I can recover a high-quality copy if the local file is corrupted or lost.
- As an administrator, I want to check the scanner's health and see if it's currently busy with a large scan, so I know when it's safe to trigger another operation.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A full scan is triggered via the API | The scanner starts walking the music directory in the background. New files are added to the library, and updated files (detected by size or modification time) have their metadata refreshed. |
| A full scan is triggered while another is already running | The request is rejected with a "busy" error message to prevent resource contention. |
| A single file scan is requested with a valid path | The scanner processes only that file. The database is updated immediately, and the result is returned in the response. |
| A single file scan is requested for a non-existent file | An error is logged, and the request fails gracefully (the file is not added/updated). |
| A redownload is requested for a track that has a matching entry in the download archive | A background task is started using the appropriate downloader (SoundCloud/YouTube) to re-acquire the track using its original source URL. |
| A redownload is requested for a track that was imported manually (no source URL found) | The request is refused with a clear message stating that the source URL could not be found in the system's history. |
| A file's metadata is updated on disk | During the next scan (full or single-file), the database record is updated to reflect the new title, artist, or label. |
| A retag changes a file's title or primary artist | The file lands on a new track row; its ratings and listening history move with it and the old, fileless row disappears. A label or channel the file no longer names is unlinked. |

## Acceptance Criteria

1. The scanner correctly identifies and processes new audio files in the designated music folder.
2. Metadata (Title, Artist, Label, Duration) is extracted from files and correctly mapped to the central track and artist records.
3. Multiple artists and labels for a single track are correctly handled, preserving their roles (e.g., primary vs featuring artists).
4. Redownload logic correctly identifies the source URL from the download history based on the current filename.
5. The system prevents concurrent full scans to protect database and filesystem performance.
6. Scanner state (busy/idle) is correctly reported via the health endpoint.

## Open Questions / Not Yet Decided

- **Handling of deleted files**: Currently, the scanner adds and updates records but does not remove entries from the database when a physical file is deleted from disk.
- **Moved files**: Moving a file currently creates a new media file record while leaving the old one orphaned. Detecting moves (e.g., via audio content hash) is not yet implemented.
- **Automatic triggers**: Besides the periodic loop (default 1 hour) and manual API calls, the scanner does not yet react automatically to filesystem events (e.g., inotify).
- **Broken files**: Files that are corrupted or have unsupported formats are logged but not explicitly flagged in the UI for user intervention.
