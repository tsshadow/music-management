# Importer — Functional Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This is the
functional (user-observable) half of the music importer feature; the implementation contract is in
[technical.md](technical.md).

## Overview

The `importer` feature automates the ingestion of new music into the library. It is designed to handle
bulk downloads from label promo pools or manual downloads that often arrive as compressed archives.
The importer monitors a specific folder, extracts any archives found, standardizes the folder structure,
infers the correct publisher and catalog information, and moves the files to their final destination in
the library. Finally, it ensures every track is correctly tagged using rule-based logic and notifies the
user of the successful import.

## User Stories

- As a user, I want to drop compressed music archives into an import folder, so that they are automatically
  processed without manual extraction.
- As a user, I want the system to recognize the record label and catalog number from the folder name, so
  that my library remains organized without manual sorting.
- As a user, I want my music to be automatically tagged with consistent metadata (Publisher, Catalog Number,
  Copyright) during import, so that it matches the rest of my collection.
- As a user, I want to receive a notification on my mobile device when an import is complete, so that I know
  when new music is ready for playback.
- As an administrator, I want to see clear logs or warnings when an import fails or requires manual
  intervention, so that I can fix issues like missing label mappings.

## Functional Flows

### Automated Import Pipeline

| Situation | Observable outcome |
|---|---|
| A `.zip` or `.rar` archive is placed in the import folder | The archive is extracted into the same folder and then deleted. |
| An extracted folder contains a catalog ID in parentheses (e.g., `(SCAN123)`) | The folder is renamed to a standardized format: `SCAN123 - [Original Name]`. |
| A standardized folder is ready for moving | The system looks up the catalog ID prefix (e.g., `SCAN`) in its database to find the associated Label (e.g., `Scantraxx`). |
| The Label is found in the database | The folder is moved to the final library path: `/path/to/eps/[Label]/[Folder Name]`. |
| A folder is moved to its final destination | Every audio file inside is tagged with metadata and the user receives an "Import Complete" notification. |
| A folder's catalog ID is not recognized | The folder remains in the import folder, and a warning is logged: "Manual intervention required." |
| A destination folder already exists in the library | The source folder in the import directory is removed to avoid duplicates, and a warning is logged. |

### Error Handling

| Situation | Observable outcome |
|---|---|
| An archive is corrupt or unsupported | An error is logged, and the file is skipped (not deleted). |
| A file operation fails due to permissions or disk space | A clear error message is logged with technical details. |
| An audio file fails tagging logic | The error is logged, but the file remains in its destination; other files in the same folder continue processing. |

## Acceptance Criteria

1. The service supports at least `.zip` and `.rar` archive formats for extraction.
2. Archives are always deleted immediately after successful extraction to save space.
3. Folders are automatically renamed to include the catalog ID as a prefix if found in parentheses.
4. Folders are moved to the correct label-based subdirectory in the library based on database mappings.
5. Every imported audio file is tagged with at least `PUBLISHER`, `CATALOG_NUMBER`, and `COPYRIGHT` tags.
6. A mobile notification is sent for every successfully processed folder, summarizing the imported tracks.
7. Unrecognized folders or failed imports do not "disappear"; they remain in the import folder for manual review.

## Open Questions / Not Yet Decided

- **Partial Imports**: If a folder contains both music and non-music files (e.g., PDFs, JPGs), they are
  currently moved along with the music. Should the system filter only audio files?
- **Mapping Management**: Today, adding a new `catid -> label` mapping requires direct database access.
  Should there be a management UI in `music-manager` for this?
- **Conflict Strategy**: When a destination exists, the current behavior is to delete the source. Should it
  optionally merge or rename instead?
