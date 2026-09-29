# Browse by BPM — Technical Design

Implements [functional.md](functional.md). Two merge requests, as Teun asked: the browse on existing
data first (this design's "Effective BPM", "The index", "API" and "Frontend" sections), then the
measurement worker that fills `library_track_bpm` ("Measurement"). The schema for the measurements
ships with the first, so the second adds no schema.

## Data Model

### What exists

- `library_track_audio_features` (one row per analysed track, linked through `internal_track_id`;
  89,869 rows on production, all linked): `bpm_tag` (the file's BPM tag when the ml-analyzer read
  it) and `tempo` (the ml-analyzer's own `librosa.beat.beat_track` estimate). The ml-analyzer is
  deprecated and switched off (issue #44), so this table no longer grows.
- `library_track_genres` → `rules_genres.name`: the genres a track carries (113k of the 267k tracks
  have at least one).
- `library_tracks.form`: `track`, `set`, `liveset`, `podcast`. Only `track` (and unclassified `NULL`)
  has one tempo.

Why the old values are coarse: librosa's tempo comes from an autocorrelation lag counted in whole
frames of 512 samples at 22,050 Hz, so it can only be `60 · 22050 / (512 · lag)` -- 152.0 at lag 17,
161.5 at lag 16. Measured on production: 104 distinct `tempo` values, 113 distinct `bpm_tag` values,
top tag values 152 (25.3k), 161 (7.6k), 99, 172, 103, 144. Exactly-150 tags: 73.

### New: `library_track_bpm` (migrate_v50_track_bpm.sql, db_init, schema test)

| Column | Type | Meaning |
|---|---|---|
| `track_uid` | VARCHAR(255) PK | The join key. `track_uid` survives a library rebuild and a file move; `library_tracks.id` does not. |
| `status` | ENUM('ok','failed') | A failed decode is recorded so it is not retried every round. |
| `bpm` | DECIMAL(5,2) NULL | The tempo after octave folding; NULL on failure. |
| `raw_bpm` | DECIMAL(5,2) NULL | What the estimator measured before folding. |
| `confidence` | DECIMAL(4,3) NULL | 0..1, the estimator's own. |
| `method` | VARCHAR(32) | Estimator and version (`acf-comb-v1`), so a better version can re-queue older rows. |
| `octave_corrected` | TINYINT(1) | 1 when folding changed the raw value. |
| `file_mtime`, `file_size` | DOUBLE, BIGINT | The file as measured; a replaced file is measured again. |
| `attempts`, `error` | INT, VARCHAR(255) | Failure bookkeeping. |
| `analyzed_at` | DATETIME | |

Indexes: `bpm`, and `(status, analyzed_at)` for the worker's retry scan. Nothing writes it in the
first merge request; the browse already reads it.

## Effective BPM (`services/music_manager/bpm/effective.py`)

One function, `resolve()`, decides a track's tempo. Nothing else chooses between the sources.

1. A `library_track_bpm` row with `status = 'ok'` wins, taken as stored (the worker already folded
   it). Confidence `high` at or above `bpm_reliable_confidence` (config, default 75%), else `medium`.
   `approximate = false`.
2. Else `bpm_tag`, else `tempo`, each only when 40-500 (a zero tag or a mis-parsed 1500 is noise).
   The value is folded into the band of the track's genres (`bands.fold_into_band`).
   `approximate = true`. Confidence `medium` only when the source is the tag, the analyzer's tempo
   agrees with it within 2 BPM after folding both, the track has a genre band, and the tag already
   sat inside it without folding; otherwise `low`.

"Betrouwbaar" in the page is `min_confidence=medium`.

### Octave folding (`services/music_manager/bpm/bands.py`)

`GENRE_BANDS` maps a genre name (lower-cased `rules_genres.name`) to `(low, high)` BPM, every band
narrower than an octave so at most one octave of a tempo fits: hardstyle 135-175, raw hardstyle
145-175, hardcore 150-245, uptempo 180-260, frenchcore 175-240, terror 200-350, drum 'n bass
160-185, techno 120-160, house 115-135, and so on. A track with several genres gets the intersection
of their bands (hardstyle + hardcore → 150-175), or the narrowest band when they do not overlap.
`fold_into_band` tries ×1, ×2, ×½, ×4, ×¼ and keeps the first that lands in the band; when none
does it keeps the nearest and says `in_band = false`. A track without a known genre uses
`DEFAULT_BAND` (88-250): only half-time readings below 88 are doubled, because in this collection a
75 is almost always a 150. The table is a proposed default from the genres' usual tempo ranges, not
curated data; curating it (an editable band per genre, inherited through the genre hierarchy like
hardness) is a possible follow-up.

## The index (`services/music_manager/bpm/index.py`)

Folding is a Python rule, so filtering on the effective BPM in SQL would mean writing the rule twice.
Instead `INDEX_SQL` reads, once, every `track`-form track that has any BPM source, with its genres
(one grouped query; ~88k rows on production), `BpmIndex.from_rows` resolves them, and the entries
are kept sorted by tempo. A request bisects to the window, filters confidence and genre in memory,
sorts, pages, and only then asks MariaDB for the details (title, artist, file) of the one page.

`IndexCache` keeps one index per process. The first request after a start builds it (about a
second); afterwards an index older than ten minutes is still served while a background thread
rebuilds it, and a failed rebuild keeps the old one. A new measurement therefore shows up within ten
minutes. Memory: ~90k small frozen dataclasses, a few tens of MB at most.

## API Contract

Router `services/music_manager/routers/bpm.py`, mounted at `/api/library/bpm`, any valid API key
(`verify_api_key`). No existing endpoint changes; nothing breaks.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/library/bpm/tracks` | `bpm` + optional `tol` (0-10, default `bpm_browse_tolerance` = 2), **or** `bpm_from` and/or `bpm_to` (40-500, inclusive); optional `min_confidence` (`low`/`medium`/`high`), `genre` (a name, case-insensitive), `limit` (1-500, default 100), `offset` | `{bpm_from, bpm_to, center, tolerance, min_confidence, genre, total, offset, next_offset, tracks: [{id, title, artist, duration_secs, work_id, genres, library_path, bpm, bpm_source, bpm_confidence, bpm_folded, bpm_approximate}]}`. With `bpm`: nearest first, then more trusted, then id. With a range: by tempo, then id. | 400: neither `bpm` nor a range bound; `bpm_from` > `bpm_to`. 422: a value outside its bounds, an unknown `min_confidence`. 401/403/503: the shared key check and database outage. |
| `GET /api/library/bpm/histogram` | optional `min_confidence`, `genre`, `bpm_from` (default 60), `bpm_to` (default 300) | `{bins: [{bpm, count, high, medium, low}], genres: [{name, count}] (top 40), default_tolerance, summary: {tracks, by_source, by_confidence}}` | as above |

Config (Beheer → Config → BPM): `bpm_browse_tolerance` (integer, default 2, clamped 0-10) and
`bpm_reliable_confidence` (integer percent, default 75).

## Frontend

- `src/lib/bpm.js`: the two fetches, `selectionParams` (a tempo with its tolerance, or a range, plus
  the filters), `loadBpmPage` (MuMa's page → LMS songs through `getSongsByPath`, reusing
  `feeds.js`' `chunkPaths`/`resolveFeedChunk`, the BPM attached to each song as `mumaBpm` by matching
  LMS's relative `path` to MuMa's `library_path`), `bpmContinuation` (the queue tops itself up with
  the next page, `listContinuation.js`), and the histogram helpers.
- `src/lib/bpmFormat.js`: `formatBpm` ("≈152" / "150"), on its own so `TrackList` does not pull in
  the API module.
- `src/lib/BpmView.svelte`: the page (lazy chunk `bpm`, route `/bpm`, `activeView === 'bpm'`).
- `navigation.js` `LIBRARY_SECTIONS` gets `bpm` after `lineups`, so the desktop sidebar and the
  phone's Bladeren grid both list it (they read the same list); `collections.js` `COLLECTION_MODES`
  limits it to songs mode.
- `TrackList.svelte` shows a small pill after the title when a row carries `mumaBpm`. No other list
  sets it, so no other list changes.

Styling follows docs/styleguide.md with existing tokens only (Design Backlog entry "Browse by BPM").

## Measurement (second merge request)

Not in the first merge request; recorded here so the schema above is justified.

### Choosing the estimator

Measured with `tools/bpm_eval.py` (second merge request) on 399 production files copied read-only to
the workstation: every track whose file tag is a whole number that the old analyzer cannot produce
(150, 155, 160, 200, 210, 130, 175, ...), so the tag cannot be the analyzer's own. Every method got the
same 60 s excerpt from 30% into the track. "Oracle octave" is the accuracy if the octave were always
chosen right -- the ceiling folding can reach.

| Method | ±0.5 BPM | ±1 BPM | Octave errors | ±1, oracle octave | s/track (analysis) |
|---|---|---|---|---|---|
| Autocorrelation comb (ours, `acf-comb-v1`) | 74.4% | 75.4% | 10.3% | 84.7% | 0.19 |
| Ours + genre-band folding | **83.0%** | **84.5%** | **0.3%** | 84.7% | 0.20 |
| Essentia RhythmExtractor2013 multifeature | 27.6% | 30.3% | 26.3% | 53.4% | 1.77 |
| Essentia RhythmExtractor2013 degara | 28.8% | 32.6% | 25.3% | 53.4% | 0.52 |
| Essentia PercivalBpmEstimator | 14.8% | 15.5% | 66.9% | 76.7% | 0.62 |
| librosa `beat_track` default (the old data) | 0.0% | 2.3% | 17.5% | 4.0% | 0.09 |
| librosa `beat_track`, hop 128, median beat interval | 21.3% | 47.1% | 27.3% | 72.9% | 0.78 |

Part of the remaining 15% is the tags themselves: a label's free DJ tools tagged 130 or 140 that
play at 210, an album tagged 155 throughout whose tracks every method measures at 157-161. On the 357
tracks where the tag agrees (within 3%, octave aside) with at least one of the four estimators, ours
with folding is 94.4% within ±1 and 92.7% within ±0.5. aubio has no wheel for Python 3.14 (it would
need a C build in the image) and was not measured. Essentia installs cleanly (a `cp314` manylinux
wheel exists) but is both less accurate on this music and slower, and it is AGPL-licensed.

The chosen method, in numpy only (no librosa import, ~150 MB less resident memory per worker):
log-magnitude spectral flux at 11,025 Hz with a 64-sample hop (172 frames/s), its autocorrelation
through the FFT, and for every candidate tempo on a 0.1 BPM grid (0.01 around the winner) the mean
autocorrelation at the first 12 whole multiples of the beat period, read between lags by linear
interpolation. Summing over multiples is what removes the grid: a one-frame error in the period
becomes twelve frames at the twelfth multiple. Confidence is the pulse strength, halved when the two
halves of the excerpt disagree; on the evaluation set 89% of estimates with confidence ≥ 0.75 were
right against the raw tags.

### Worker (planned, second merge request)

A small separate service from the tools image (which already has ffmpeg; music-manager's image has
none and 74,568 library files are `.m4a`, which libsndfile cannot decode), with a hard CPU and memory
ceiling from compose, `nice`/`ionice`, default 2 decode/analysis workers. It decodes a 60 s excerpt
per track with `ffmpeg -ss` (a seek, so a 10 MB file on the CIFS mount costs a fraction of its
size), newest tracks first, skips sets, podcasts and anything over 15 minutes, folds with the genre
band, and writes `library_track_bpm`. Settings on Beheer → Config → BPM: enabled, workers, excerpt
seconds, skipped forms, pause. Progress: a periodic INFO summary (analysed/failed/remaining) and a
heartbeat that music-manager's `/health` reports. The second merge request's own design update
fills in the measured backlog duration.

## Cross-App Impact

- music-manager: new tables/router/config, no change to an existing endpoint.
- frontend (the web player, and the phone app, which renders the same web UI): the BPM page and the
  pill in `TrackList`.
- LMS: none (`getSongsByPath` already exists).
- MuMa Mobile native (Android Auto browse tree): none in this change; a BPM folder is a follow-up.

## Technical Acceptance Criteria

1. `resolve()` prefers a measurement, then the tag, then the tempo; folds tag/tempo into the genre
   band and never refolds a measurement; returns None for values outside 40-500
   (`test_bpm_effective.py`).
2. Every band in `GENRE_BANDS` is narrower than an octave; overlapping genres intersect, disjoint
   ones take the narrowest (`test_bpm_effective.py`).
3. The index selects inclusively by tempo, sorts a picked tempo nearest-first then by confidence,
   filters by confidence and genre (case-insensitive), and serves a stale index while it rebuilds
   (`test_bpm_browse.py`).
4. `/api/library/bpm/tracks` and `/histogram` answer as in the contract, including 400/422, and ask
   the database nothing for an empty page (`test_bpm_browse.py`); both SQL statements run on a real
   MariaDB with a measurement, a tag, a folded tempo, a failed measurement and a set seeded
   (`tests/integration/test_router_sql.py` `BpmBrowseSqlTest`).
5. `library_track_bpm` is created by db_init and declared by migrate_v50 (`test_schema.py`).
6. The page sends the right request for a chip, a bar, the tolerance, the range, the genre and the
   reliability switch, shows "≈" for coarse values and the note once, and queues the list in order
   (`bpmView.test.js`, `bpm.test.js`).

## Related Docs

- [docs/api-specification.md](../../api-specification.md), "Browse by BPM".
- [services/ml-analyzer/DEPRECATED.md](../../../services/ml-analyzer/DEPRECATED.md) -- where the old
  values came from.
- [docs/designs/feeds/](../feeds/) -- the `library_path` + `getSongsByPath` pattern this reuses.
