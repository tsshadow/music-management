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

### Internal Workflow (Pipeline)

1. **`Extractor`**:
    - Scans `import_folder_path` for files.
    - Uses `patoolib.extract_archive` to unpack them.
    - Deletes original archive after extraction (`os.remove`).
2. **`Renamer`**:
    - Scans folders in `import_folder_path`.
    - Regex searches for `(CATID)` in folder names.
    - Renames folders to `CATID - FolderName` using `os.rename`.
3. **`Mover`**:
    - Extracts `catid` from folder name (first space-separated part, cleaned of non-alphanumeric chars).
    - Queries `rules_catid_label` for the `label`.
    - Moves folder to `eps_folder_path / label / FolderName` using `shutil.move`.
    - Triggers `post_processing_songs(path)`.
4. **Post-Processing (`LabelSong`)**:
    - Walks the new directory.
    - For each audio file, instantiates `LabelSong(path)`.
    - `LabelSong.parse()` applies metadata rules and writes tags using `mutagen`.
    - Calls `notification_service.notify()` with `str(song)` summary.

## Cross-App Impact

- **`music-manager`**: Shares the same MariaDB database and `rules_catid_label` table.
- **`tagger`**: The `importer` directly imports and uses `LabelSong` from `services/tagger`. Any changes to `LabelSong` or its underlying rules will immediately affect the importer.
- **`ntfy.sh`**: Relies on the external notification service for mobile alerts.

## Technical Acceptance Criteria

1. **Archive Support**: `Extractor` successfully processes `.zip` and `.rar` files using `patoolib`.
2. **Atomic Renaming**: `Renamer` handles `FileExistsError` by removing the source folder if the destination name already exists (avoiding partial/corrupt states).
3. **Regex Robustness**: `get_cat_id` correctly handles both full IDs (e.g., `SCAN123`) and short codes (e.g., `SCAN`) by extracting the prefix before the numeric part.
4. **Metadata Integrity**: `LabelSong` correctly infers `PUBLISHER` from the label subdirectory and `CATALOG_NUMBER` from the folder prefix.
5. **Notification Flow**: `Mover` successfully calls `notification_service.notify` with a non-empty string derived from the `LabelSong` object.
6. **Test Coverage**:
    - `test_importer_basic.py`: Verifies metadata extraction from various path depths.
    - `test_importer_mover.py`: Verifies that notifications are triggered during post-processing.
    - `test_importer_artist_rules.py` & `test_importer_genre_rules.py`: Verify that `LabelSong` correctly applies global tagging rules.

## Related Docs

- [docs/architecture.md](../../docs/architecture.md) — System-wide module responsibilities.
- [docs/database-design.md](../../docs/database-design.md) — Schema details for `rules` domain.
- [AGENTS.md](../../AGENTS.md) — Development guidelines and monorepo structure.
