# Analyzer module

The analyzer normalizes the local music library, stores structured metadata for
artists/albums/tracks and exposes background jobs that enrich listens with the
best matching track data. Filesystem scans feed into a shared relational schema
that is also consumed by the live scrobbling pipeline.

## Supported media types

The filesystem scanner processes audio files with the following extensions:

- `.mp3`
- `.flac`
- `.m4a`
- `.ogg`
- `.wav`
- `.opus`

Each file that is discovered stores its path, file size, modification time and
the raw metadata payload extracted during the scan.

## Captured tags

In addition to the filesystem metadata, the analyzer persists the following tags
when scrobbles or enrichment jobs provide them:

- Track title, album title and release year
- Primary artist and featured artists (with roles)
- Track number, disc number and duration (in seconds)
- MusicBrainz identifiers (MBID) and ISRC codes when available
- Genre assignments and record labels linked to each track
- Catalog numbers (CATALOGUSNUMBER) and festival tags captured as analyzer attributes

The analyzer API exposes queueable jobs to scan libraries, enrich listens and
reindex track identifiers. The `/api/v1/analyzer/summary` endpoint surfaces a
dashboard-ready overview with file counts, song/long-form splits, and the top
artists and genres detected so far.
