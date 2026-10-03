# Tagger — Functional Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This is the functional (user-observable) half of the tagger feature; the implementation contract is in [technical.md](technical.md).

## Overview

The Tagger is the core metadata enforcement engine of the Music Management System. It ensures that every track added to the library follows consistent naming and tagging standards, regardless of its source (SoundCloud, YouTube, Label promo pools, etc.). It automatically detects the type of song based on its file location and applies source-specific rules to clean up titles, infer missing information like artists and genres, and normalize technical tags like BPM and Unicode characters.

## User Stories

- As a library manager, I want my music files to have consistent and clean metadata, so that my library is easy to browse and search.
- As a user downloading music from SoundCloud or YouTube, I want the system to automatically strip "premiere" prefixes and channel names from the title, so that the metadata reflects the actual song info.
- As a user importing label promo pools, I want the system to automatically extract the Publisher and Catalog Number from the folder structure, so I don't have to enter them manually.
- As a power user, I want the system to automatically infer the genre of a track based on the artist or subgenre, so that my library is automatically categorized.
- As a system administrator, I want to trigger a full library tagging run in the background, so that I can ensure all files are up to date with the latest rules without manual intervention.

## Functional Flows

### Auto-Detection and Source-Specific Tagging

| Situation | Observable outcome |
|---|---|
| A file is located in the `Soundcloud` folder | The system identifies it as a SoundCloud track. It sets the Publisher to "Soundcloud", sets the Album to "Soundcloud (uploader name)", and applies SoundCloud-specific cleanup rules (e.g., removing "PREMIERE" from titles). |
| A file is located in the `Youtube` folder | The system identifies it as a YouTube track. It sets the Publisher to "Youtube", sets the Album to "Youtube (channel name)", and attempts to split the title into "Artist - Title" if it's currently just a single string. |
| A file is located in the Labels/Promo pool folder | The system identifies it as a Label track. It extracts the Publisher (label name) and Catalog Number from the folder names and applies them to the file's tags. |
| A label track's Catalog Number holds the whole release folder name, as the tagger wrote it before bug report 145 | The tagger replaces it with the folder's `<number> - ` prefix, or else with the number in the folder name's brackets when the release's `.nfo` states the same number. With neither, it clears the tag. A value that is not the folder name stays (issue #172). |
| A file is located elsewhere in the library | The system identifies it as a "Generic" track and applies standard cleanup rules (Unicode normalization, title cleaning, BPM analysis) without source-specific overrides. |

### Metadata Inference and Cleanup

| Situation | Observable outcome |
|---|---|
| A track title contains "(Artist Remix)" or "[Artist Remix]" | The "Remix" part is removed from the title, and the artist is added to the `REMIXER` tag. |
| A track title contains "feat. Artist" | The featured artist is extracted and added to the `ARTIST` tag (as a list of artists). |
| A track's genre is unknown but the artist has a known genre in the database | The system automatically assigns the artist's primary genre to the track. |
| A track has zero-width spaces or other "invisible" invalid characters in its tags | These characters are automatically stripped to prevent display issues in players. |
| BPM analysis is enabled for a track | The system analyzes the audio and saves the detected BPM to the `BPM` tag. |

### API Operations

| Situation | Observable outcome |
|---|---|
| A user triggers a "Tag All" operation | The system starts a background process that visits every file in the library and applies the appropriate tagging rules. The operation can be monitored via the health endpoint. |
| A user triggers tagging for a specific file | The system immediately processes that file and returns a success message once complete. |
| A user requests to stop a background tagging run | The system gracefully stops the ongoing process as soon as it finishes its current file. |

## Acceptance Criteria

1. Every file processed by the tagger, regardless of source, has its Unicode characters normalized and invalid/invisible characters removed.
2. SoundCloud tracks always have their Publisher set to "Soundcloud" and their Album set to a consistent format including the uploader name.
3. YouTube tracks with "Artist - Title" in the filename or title tag have these fields correctly split into separate Artist and Title tags.
4. Label tracks correctly inherit their Publisher and Catalog Number from their parent directory names.
5. Inferred metadata (Remixers, Featured Artists, Genres) is correctly added to the appropriate tags without duplicating existing information.
6. The system never overwrites manually set tags if the rule-based inference results in less specific information (e.g., it won't replace a specific genre with a generic one).
7. A full tagging run can be started and stopped via the API without crashing the service or leaving files in a corrupted state.

## Open Questions / Not Yet Decided

- **Manual Overrides**: Should there be a way to "lock" certain tags so the auto-tagger never touches them? (Currently, it seems to mostly add missing info or clean up format, but doesn't have a "strict" vs "lax" mode).
- **Genre Multi-mapping**: When an artist maps to multiple genres, how does the system choose which one to apply if none are currently set? (Current code seems to add all matched genres to the list).
- **User Input in Web API**: The `AddMissingArtistToDatabaseRule` has logic for asking the user for input via `stdin`. This obviously doesn't work when running as a background service via the REST API. How should "missing information" prompts be handled in the UI? (Currently they are likely ignored/skipped in background mode).
- **Re-tagging Frequency**: Should the system automatically re-tag files when rules change, or only on manual trigger/first import?
