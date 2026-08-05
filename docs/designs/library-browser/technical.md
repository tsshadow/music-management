# Library Browser — Technical Design

Implements [`functional.md`](functional.md).

## Data Model

### `library_track_genres` — existing table, first writer

```sql
library_track_genres (
  track_id INT NOT NULL,   -- FK library_tracks(id) ON DELETE CASCADE
  genre_id INT NOT NULL,   -- FK rules_genres(id)   ON DELETE CASCADE
  weight   FLOAT DEFAULT 1.0,
  PRIMARY KEY (track_id, genre_id)
)
```

The table exists in production with zero rows. No code writes to it — `library.py`, `stats.py` and
`users.py` only read it, and the migration tools only rename it. This design adds the writer.

One index is missing for the access pattern this design introduces. The primary key `(track_id, genre_id)`
serves lookups by track, but genre distribution and the genre facet scan by `genre_id`:

```sql
ALTER TABLE library_track_genres ADD INDEX idx_genre_id (genre_id);
```

`weight` stays at its default. Nothing produces a meaningful weight today, and a column nothing writes is
precisely the failure mode this design exists to correct.

### `library_track_audio_features` — no schema change

`/api/library/advanced` currently selects `musical_key`, `energy`, `danceability`, `valence` and
`popularity`. None of these columns exist in production. They appear in the `CREATE TABLE IF NOT EXISTS`
statement in `services/common/db_init.py`, but the table predates them and that statement is a no-op against
an existing table; there is no `ALTER TABLE` anywhere. Every request therefore fails:

```
ERROR 1054 (42S22): Unknown column 'af.musical_key' in 'SELECT'
```

These columns are removed from the query rather than added to the table. Nothing writes them, and adding
them would recreate the same divergence between schema and reality.

The columns that do carry data, measured against a production copy of 2026-07-11 (90,158 rows):

| Column | Populated | Use |
|---|---|---|
| `tempo` | 89,430 | BPM, preferred over `bpm_tag` |
| `bpm_tag` | 66,001 | BPM fallback |
| `duration` | 89,433 | unused; `library_tracks.duration_secs` is authoritative |
| `release_year` | 89,308 | year facet and histogram |
| `label_name` | 89,732 | unused; `library_track_labels` is authoritative |
| `genre_tag` | 47,951 | superseded by `library_track_genres` |
| `mean_rms`, `mfcc_*`, `mean_chroma`, spectral | 89,433 | not surfaced; model features |
| `source_platform` | 426 | too sparse to use; source comes from `library_track_labels` |

Against 265,785 tracks in `library_tracks`, audio features cover roughly 34 percent. That is what the
coverage indicator reports.

### Required indexes for the filter combinations

```sql
ALTER TABLE library_track_labels ADD INDEX idx_label_id (label_id);   -- label facet
ALTER TABLE library_tracks       ADD INDEX idx_created_at (created_at); -- default sort
```

Each is added only if absent. `library_artists.name` and `library_tracks.title` are already indexed, and
`library_track_audio_features.track_id` carries a unique key.

## Genre write path

`ScannerManager.process_file()` in `services/music_manager/routers/scanner.py` already reads every file's
tags through `ReadonlySong` and writes artists, label, title and duration to the database. It never reads
the genre tag, although `BaseSong.genres()` returns it. That single omission is why
`library_track_genres` is empty, and why LMS — which reads the same tags — knows genres the browser does
not.

Genre resolution reuses `services/common/Helpers/GenreRulesHelper.py` rather than reimplementing curation
semantics:

```python
genre_ids = []
for raw in song.genres():
    for part in genre_helper.split_composite(raw):
        decision = genre_helper.resolve(part)
        if decision.state == BLACK:
            continue
        for value in decision.values:
            row = genre_helper.get_row(value)
            if row is not None:
                genre_ids.append(row.id)
```

| `resolve()` state | Handling |
|---|---|
| `WHITE` | Indexed under the curated name; `rules_genre_expansions` may yield several targets, all indexed |
| `BLACK` | Skipped |
| `UNKNOWN` | Indexed under the raw name, uncanonicalised |

Unknown genres already have a `rules_genres` row: `ResolveGenreRule` in the tagger calls `record_unknown()`
whenever it meets an undecided genre. The scanner therefore only reads `rules_genres` and never inserts into
it — curation stays owned by the tagger and the curation page.

Writes follow the pattern already used for `library_track_artists` in the same function: delete the track's
rows, then `INSERT IGNORE` each genre, inside the existing transaction.

The scanner's early-exit on unchanged `file_mtime` and `file_size` means a normal incremental scan will not
backfill existing tracks. A one-off `POST /api/scanner/scan/all?force=true` populates the table for the whole
library. Each run logs how many tracks were indexed and how many genre strings resolved to `BLACK`.

## API Contract

### New router — `services/music_manager/routers/analytics.py`, prefix `/api/analytics`

All endpoints accept the same filter parameters, parsed by one shared FastAPI dependency
`build_filter() -> (where_sql: str, params: list)`:

| Parameter | Type | Meaning |
|---|---|---|
| `q` | str | Free text over title, artist and label. A bare number in 50–300 is read as BPM ±2 |
| `artist` | repeated str | Match any of the named artists |
| `genre` | repeated str | Match any of the named genres, via `library_track_genres` |
| `label` | repeated str | Match any of the named labels |
| `bpm_min`, `bpm_max` | float | Range over `COALESCE(af.tempo, af.bpm_tag)` |
| `year_min`, `year_max` | int | Range over `af.release_year` |
| `analyzed` | bool | Restrict to tracks having an audio-features row |

Repeated values are OR within a parameter and AND across parameters. Building the clause in one place is
what lets the browser and a later player page pose identical questions.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/analytics/summary` | shared filters | `{tracks, artists, labels, genres, total_duration_secs, coverage: {bpm, genre, artist, analyzed}}` — coverage as fractions of `tracks` | 401 missing/invalid key; 422 unparseable filter value; 500 database unavailable |
| `GET /api/analytics/genre-distribution` | shared filters, `limit` (default 50) | `[{genre, state, count}]`, descending | as above |
| `GET /api/analytics/bpm-histogram` | shared filters, `bucket` (default 5, 1–50) | `[{bucket_start, count}]`, raw uncorrected values | as above; 422 bucket out of range |
| `GET /api/analytics/year-histogram` | shared filters | `[{year, count}]` ascending, years 1950–2100 only | as above |
| `GET /api/analytics/top-artists` | shared filters, `limit` (default 20, max 200) | `[{artist, count}]` | as above |
| `GET /api/analytics/top-labels` | shared filters, `limit` (default 20, max 200) | `[{label, count}]` | as above |
| `GET /api/analytics/artist-search` | `q` (min 2 chars), `limit` (default 20, max 100) | `[{artist, count}]` prefix-first | 422 when `q` shorter than 2 |

An empty result is HTTP 200 with an empty array. Only a genuine failure produces a non-2xx.

Later reuse from a player page needs no new endpoint:
`GET /api/analytics/bpm-histogram?artist=Angerfist`.

### Changed — `GET /api/library/advanced`

Breaking change to the response shape, with the frontend changing in the same commit (AGENTS.md rule 7).

Removed from the response: `musical_key`, `energy`, `danceability`, `valence`, `popularity` — every one of
them backed by a column that does not exist.

Added: `duration_secs` (from `library_tracks`; the frontend already renders `track.duration_secs`, which the
query never selected, so the duration column has always shown `-`), `release_year`, `genres` as a list, and
`file_path`.

Filtering moves to the shared `build_filter`, so `/advanced` and `/api/analytics/*` cannot drift apart.
`page` is honoured — the frontend currently never sends it.

### Changed — `GET /api/library/genres`

Returns `[]` today: it joins `rules_genres` against the empty `library_track_genres`. After the write path
exists the join yields rows. The response becomes `[{genre, state, count}]` restricted to `state IN
('white', 'unknown')`, so the sidebar can group approved genres separately from those awaiting curation and
show counts.

### Changed — `GET /api/stats`

Response shape is unchanged; the consumer moves from the Stats tab to Overview. `top_genres` stops unioning
`library_track_ml_labels.ml_genre` and counts `library_track_genres` alone, so each track contributes once
per genre it actually carries. The existing semicolon-splitting in Python becomes unnecessary — genres are
already one row each in `library_track_genres` — and is removed with it.

## Frontend

`AdvancedLibraryTab.svelte` becomes the single Library Browser. `LibraryTab.svelte` and `StatsTab.svelte`
are deleted and their entries removed from `Management.svelte`; the surviving route id is `library`.

Carried over from `LibraryTab`: the `rerun-parse` and `redownload` actions and their confirmation dialogs,
relocated into the inspector.

Carried over from `StatsTab` into `OverviewTab`: total scrobbles, match rate, unmatched listens, recently
added, and the fetch-artist-images action.

Removed as unbacked: the key/Camelot grid, mood buttons, vocals checkboxes, audio-feature bars, lyrics
panel, tag chips, the "Favorites Only" / "Recently Added" / "Needs Review" checkboxes, and both hardcoded
distribution charts. Also removed: `total_albums` (no album table exists — `stats.py` returns a literal 0),
`total_duration_hours` (computed as `total_tracks * 3.5 / 60`, an invented average) and `avg_rating`
(hardcoded 4.3 against 21 real ratings).

Every `fetch` checks `res.ok` and surfaces the failure. The current code checks only for a thrown exception,
so an HTTP 500 leaves `tracks` at `[]` and renders "No tracks found" — which is how a completely broken
endpoint stayed invisible.

Facet fetches are debounced and issued as one batch per filter change, so a click does not fire seven
requests.

## Cross-App Impact

**Frontend** — must change in the same commit as `/api/library/advanced`; it is that endpoint's only
consumer. No LMS, muma-proxy or MuMa Mobile code references `/api/library/advanced` or
`/api/library/genres`.

**Dynamic playlist preview (`users.py`) — behavioural change, no code change.** Playlist genre rules match
`library_track_genres` OR `library_track_ml_labels.ml_genre`. With the first table empty they run entirely on
ML predictions, covering about 52,000 tracks; populating it makes the first branch live and the preview will
match substantially more tracks. The blast radius is one screen: the query lives only in
`GET /{user_id}/dynamic-playlists/{playlist_id}/tracks`, whose sole caller is `PlaylistsTab.svelte` in the
web UI. MuMa Mobile calls only the list, create and delete endpoints
(`MumaAPIDefinition.kt:34-45`), `POST /dynamic-playlists/sync` stores a playlist definition without
resolving tracks, and the C++ server references neither `library_track_genres` nor `dynamic_playlists`. The
Android app's playlists are resolved elsewhere and are unaffected. The seeded default playlists are being
retired separately.

**`GET /api/stats` — changed output, requires a code change.** Its `top_genres` query unions
`library_track_genres` with `ml_genre` and counts both, so once the first table has rows a track carrying the
same genre in its tag and its ML prediction would be counted twice. Rather than deduplicate the union, the
`ml_genre` branch is dropped: `top_genres` counts `library_track_genres` alone. That matches the decision to
keep early-stage ML predictions out of curated-genre figures, and makes the number Overview shows mean one
thing. Genre counts will change when this ships, since they are currently derived from ML predictions only.

## Technical Acceptance Criteria

1. `GET /api/library/advanced` returns HTTP 200 against a schema built from `services/common/db_init.py`,
   and its response contains none of `musical_key`, `energy`, `danceability`, `valence`, `popularity`.
2. A test executes every `/api/library/*` and `/api/analytics/*` query against a freshly created schema and
   fails on any reference to a non-existent column. This is the regression guard for the defect class: the
   `musical_key` bug survived because that SQL never ran against a real schema in any test.
3. `build_filter` has unit tests for each parameter alone, for repeated values within a parameter producing
   OR, for several parameters producing AND, and for no parameters producing an unrestricted clause.
4. Every `/api/analytics/*` endpoint returns identical filtering for identical parameters, verified by
   asserting that `summary.tracks` equals the `total` from `/api/library/advanced` under the same filters.
5. Scanner genre resolution has unit tests for `WHITE` yielding the canonical name, `BLACK` yielding
   nothing, `UNKNOWN` yielding the raw name, an expansion yielding several genres, and a composite
   `A/B` splitting only when undecided.
6. After `process_file()` runs on a fixture with a multi-genre tag, `library_track_genres` holds one row per
   resolved genre, and re-running it does not duplicate or accumulate rows.
7. A track whose only tag genre is `BLACK` ends with no rows in `library_track_genres` and does not appear
   under any genre filter.
8. `GET /api/library/genres` returns a non-empty list with counts once the table is populated, and excludes
   `state = 'black'`.
9. `bpm-histogram` returns raw bucket counts with no half or double-time correction applied.
10. `artist-search` with fewer than 2 characters returns 422; with a valid query it returns matches ordered
    prefix-first.
11. Every endpoint returns 401 without a valid API key, matching the existing routers' behaviour.
12. A filter matching no tracks returns HTTP 200 with empty arrays, never a 4xx or 5xx.
13. Frontend tests assert that a non-ok response renders an error message rather than the empty-result view.
14. `GET /api/stats` derives `top_genres` from `library_track_genres` alone, counts each track once per
    genre it carries, and its result contains no genre that exists only as an ML prediction.
15. The added indexes exist, and a combined genre + label + BPM-range query over the full 265k-track dataset
    returns within one second.

## Related Docs

- [Genre curation](../genre-curation/functional.md) — the white/black/unknown model and `GenreRulesHelper`
  semantics this design reuses
- [Artist curation](../artist-curation/functional.md) — artist-name pollution affecting the artist facet
- [Database design](../../database-design.md)
- [Bug report 021](../../bug-reports/021-genre-migration-never-shipped.md) — prior instance of the same
  class, a genre migration that never ran
