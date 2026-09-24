# Importer — Technical Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This document
implements the already-agreed [functional.md](functional.md).

## Data Model

The importer relies on the `rules` domain of the database for its mapping logic.

### `rules_catid_label`
This table maps short catalog ID prefixes to their canonical record label (Publisher) names.

| Column | Type | Description |
|---|---|---|
| `catid` | VARCHAR | The short code prefix (e.g., `SCAN`, `DWX`). Primary Key. |
| `label` | VARCHAR | The full name of the label (e.g., `Scantraxx`, `Dirty Workz`). |

## Service Contract

The importer is a standalone Python service (`services/importer/importer_service.py`) that runs as a background worker. It does not expose a REST API; instead, it operates directly on the filesystem and database.

### Command Line Interface

`python services/importer/importer_service.py [OPTIONS]`

| Option | Type | Default | Description |
|---|---|---|---|
| `--sleeptime` | INT | 300 | Seconds to wait between runs when in repeat mode. |
| `--repeat` | FLAG | False | If set, the service runs in an infinite loop. |

### Configuration (via `ConfigStore`)

| Key | Environment Variable | Description |
|---|---|---|
| `import_folder_path` | `import_folder_path` | Source directory to monitor for new archives. |
| `eps_folder_path` | `eps_folder_path` | Destination base directory for processed music. |
| `delimiter` | `delimiter` | System path separator (default: `os.sep`). |
| `dryrun` | `dryrun` | If true, logs actions without modifying the filesystem. |
| `import_settle_minutes` | `import_settle_minutes` | How long a release folder must sit unchanged before the flattener, renamer or mover acts on it (default 5; 0 switches the wait off). |
| `quarantine_folder_path`, `quarantine_retention_days` | same | Where discarded archives and duplicate releases are parked, and for how long. |

### Internal Workflow (Pipeline)

1. **`Extractor`**:
    - Scans `import_folder_path` for files, skipping downloads still in flight (`.crdownload`, `.part`,
      `.partial`, `.tmp`).
    - **Extracts into a staging folder**: every attempt (patool's own backend, then `unar`, then `7z`)
      gets a fresh `.muma-extract-*` folder inside `import_folder_path` -- the same filesystem, so
      moving the result in is a rename. A backend that fails halfway has its staging folder deleted,
      so the next backend starts from nothing and a partial extraction never reaches the import
      folder. Only a complete extraction is moved in; a name already taken by the same release
      (`is_same_release`) is dropped from the staging copy, a name taken by anything else leaves the
      archive in place for a human. Staging folders a killed run left behind are removed at the
      start of the step. The flattener, renamer and mover skip the `.muma-extract-` prefix.
    - **Split RAR sets**: only the first volume (`name.part1.rar`, or `name.rar` beside
      `name.r00`...) is opened; the other volumes are never extracted on their own. A set waits while
      any of its volumes is still in flight, and once extracted all volumes are quarantined together.
    - Quarantines the archive after a successful extraction (`Quarantine.put`, category
      `extracted-archive`); `Quarantine.sweep` removes it after `quarantine_retention_days`.
2. **`Flattener`**: lifts the releases of a multipack out of the wrapper folder the archive extracted
   into. Only a settled wrapper is flattened.
3. **`Renamer`**:
    - Scans folders in `import_folder_path`, skipping unsettled ones.
    - Regex searches for `(CATID)` in folder names.
    - Renames folders to `CATID - FolderName` using `os.rename`.
4. **`Mover`**:
    - Skips folders that are not settled.
    - Extracts `catid` from folder name (first space-separated part, cleaned of non-alphanumeric chars).
    - Queries `rules_catid_label` for the `label`.
    - Moves folder to `eps_folder_path / label / FolderName` (checked before the move, never into an
      existing folder; see the duplicate rule below).
    - Triggers `post_processing_songs(path)`, then sends **one** push for the release.
    - A folder it cannot place is recorded in `rules_label_proposals` via `label_resolver.resolve`,
      which reads the tags of every track. That is done once per folder per process: the Mover keeps
      `{folder: newest mtime}` in memory and resolves again only when something in the folder changed.
      A decision on the proposal is not held up by this -- confirming one with a catalogue number
      writes the `rules_catid_label` row the lookup above finds, and confirming one without moves the
      folder from the API.
5. **Post-Processing (`LabelSong`)**:
    - Walks the new directory.
    - For each audio file, instantiates `LabelSong(path)`.
    - `LabelSong.parse()` applies metadata rules and writes tags using `mutagen`.
    - Records an `INFO` event per file (`Track Imported`, `str(song)`) **without** a push.
    - The Mover then emits one `Import Complete` event with `push=True` per release: folder name,
      label, catalogue number, number of tracks tagged.

### Settle rule

A release folder is **settled** once nothing inside it -- no file and no sub-directory, Synology's
`@eaDir` aside -- has a modification time within the last `import_settle_minutes` (default 5). The
flattener, renamer and mover leave an unsettled folder alone (logged at DEBUG) and look again next
cycle, so a release still being copied into `__TODO` over SMB is never renamed or moved half-copied.
Directories count as well as files because a copy tool that restores each file's own date as it
closes it leaves finished files looking old. Modification time and not change time, so a freshly
extracted archive -- whose backend restores the dates stored in the archive -- is usually placed in
the same cycle; where a backend leaves a folder dated "now", that release waits one settle window.
Implemented in `services/importer/settle.py`.

### Duplicate rule

When the destination of a rename or move already exists, `is_same_release(src, dst)`
(`services/common/Helpers/ReleaseFolder.py`) decides whether the source is a duplicate download:
both folders must hold the same **track list** (every audio file by relative path) and every track
must have the same **length** according to mutagen (`info.length`), within
`DURATION_TOLERANCE_SECONDS` (1 s). Byte sizes are not compared: the library copy has been retagged
by `LabelSong` since it arrived, so a later download of the same release no longer matches it byte
for byte. Non-audio files (`.nfo`, `.sfv`, covers) are ignored. A track whose length neither side can
read is compared by size; one readable and one unreadable is a difference. A duplicate is quarantined
(`duplicate-release`); anything else is left in place with a warning for a human.

## Cross-App Impact

- **`music-manager`**: Shares the same MariaDB database and `rules_catid_label` table.
- **`tagger`**: The `importer` directly imports and uses `LabelSong` from `services/tagger`. Any changes to `LabelSong` or its underlying rules will immediately affect the importer.
- **`ntfy.sh`**: Relies on the external notification service for mobile alerts.

## Technical Acceptance Criteria

1. **Archive Support**: `Extractor` successfully processes `.zip` and `.rar` files using `patoolib`.
2. **Atomic Renaming**: when the destination name already exists, `Renamer` quarantines the source folder if it
   is the same release (duplicate rule above) and leaves both in place otherwise; it never deletes.
3. **Complete Extraction Only**: a backend that fails partway leaves nothing in the import folder, and the next
   backend extracts into an empty staging folder (`test_importer_extractor.py`).
4. **Settled Folders Only**: the flattener, renamer and mover do not act on a folder changed within
   `import_settle_minutes` (`test_importer_settle.py`).
5. **Regex Robustness**: `get_cat_id` correctly handles both full IDs (e.g., `SCAN123`) and short codes (e.g., `SCAN`) by extracting the prefix before the numeric part.
6. **Metadata Integrity**: `LabelSong` correctly infers `PUBLISHER` from the label subdirectory and `CATALOG_NUMBER` from the folder prefix.
7. **Notification Flow**: one push per imported release, summarising label, catalogue number and track count;
   every file is an `INFO` event without a push (`test_importer_mover_cycle.py`).
8. **Test Coverage**:
    - `test_importer_basic.py`: Verifies metadata extraction from various path depths.
    - `test_importer_mover.py`: Verifies that notifications are triggered during post-processing.
    - `tests/unit/test_release_compare_real_mutagen.py`: the duplicate rule against real mutagen and a
      retagged MP3.
    - `test_importer_artist_rules.py` & `test_importer_genre_rules.py`: Verify that `LabelSong` correctly applies global tagging rules.

## Related Docs

- [docs/architecture.md](../../docs/architecture.md) — System-wide module responsibilities.
- [docs/database-design.md](../../docs/database-design.md) — Schema details for `rules` domain.
- [AGENTS.md](../../AGENTS.md) — Development guidelines and monorepo structure.
