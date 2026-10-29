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

0. A tempo set by hand (`library_track_bpm_manual`, bug report 140) wins: `source = 'manual'`,
   confidence `high`, `approximate = false`. See [bpm-octave/technical.md](../bpm-octave/technical.md).
1. A `library_track_bpm` row with `status = 'ok'` wins, taken as stored (the worker already chose its
   octave, and its confidence already includes how sure that choice is). Confidence `high` at or
   above `bpm_reliable_confidence` (config, default 75%), else `medium`. `approximate = false`.
2. Else `bpm_tag`, else `tempo`, each only when 40-500 (a zero tag or a mis-parsed 1500 is noise).
   The value is folded into the band of the track's genres (`bands.fold_into_band`).
   `approximate = true`. Confidence `medium` only when the source is the tag, the analyzer's tempo
   agrees with it within 2 BPM after folding both, the track has a genre band, and the tag already
   sat inside it without folding; otherwise `low`.

"Betrouwbaar" in the page is `min_confidence=medium`.

### Octave folding (`services/music_manager/bpm/bands.py`)

> **Since bug report 140 this is no longer how a measurement's octave is decided**: the worker
> weighs half, as-measured and double on learned label/artist/genre priors, the path and the comb
> scores ([bpm-octave/technical.md](../bpm-octave/technical.md)). The bands below remain the
> fallback prior for a genre without enough measurements of its own, and still fold the old
> analyzer's tags and tempos in `resolve()`.

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

## Effective BPM in SQL (issue #141)

The browse was the only reader of the rule. The library table's BPM column and sort, its BPM
filter and bare-number search term (`analytics_filters`), `/api/library/tracks`, the analytics
coverage and histogram, the feeds' `bpm` column (displayed, and the last fallback of a track's
hardness) and the player's track details all read `COALESCE(af.tempo, af.bpm_tag)` -- the old
analyzer first, never the measurement, never folded. So one track showed three tempos.

Folding is Python, and those readers are SQL over the whole library (the table sorts all 328k
tracks), so they cannot call `resolve()` per row; writing the rule again in SQL (a genre-band table
in a CASE) is the duplication this design exists to avoid. Instead the result is **materialised**:

- `library_track_effective_bpm` (migrate_v51, db_init, schema test): `track_id` (PK, FK to
  `library_tracks` ON DELETE CASCADE), `bpm` DECIMAL(5,2), `source`, `confidence`, `approximate`,
  `folded`, `updated_at`; index on `bpm`. One row per track that has a usable tempo -- every form, so
  a set's tag still shows in the table (the browse leaves sets out, as before).
- `bpm/effective_table.py` `sync()` reads the same inputs as the index (`index.INPUTS_SQL`, which
  `INDEX_SQL` is now the track-only variant of), resolves each row through
  `effective.resolve_row` (the one column-to-argument mapping, also used by the index), compares with
  the table and writes only the difference: upserts in batches of 1000, deletes for tracks that lost
  every source. The inputs stream through an unbuffered cursor, so memory holds only the table's
  current ~300k small tuples.
- The **bpm-analyzer worker** runs it: in full every `EFFECTIVE_SYNC_SECONDS` (30 min; also while the
  analysis is paused or off, and first thing after a start), which picks up changed genres, a changed
  `bpm_reliable_confidence` (now also read by the worker) and deleted tracks; and for just the batch's
  tracks right after each round stores its measurements, so a measurement reaches the table within the
  round. A failed sync is logged and never stops the analysis; a failed full sync is retried after
  five minutes. The status file gains `effective_synced_at` and `effective_tracks`.
- `analytics_filters.EFFECTIVE_BPM_JOIN` (`LEFT JOIN library_track_effective_bpm eb ON eb.track_id =
  t.id`) is part of the shared `FROM_CLAUSE`, and `EFFECTIVE_BPM_SQL` (`eb.bpm`) is what every filter,
  sort and aggregate reads. The feeds read it as a primary-key scalar subquery.
- **Track details** (`/api/library/tracks/by-path`) resolve live instead: one track, three
  primary-key probes, and a measurement shows the moment it is stored.

Staleness: a new measurement is in the table within its round; a genre change within 30 minutes; a
rebuilt library (new track ids) is empty for the tables' readers until the next full sync. Without a
running worker (the test stack) the table stays empty and those readers show no BPM; the browse and
the details sheet, which resolve for themselves, are unaffected. Measured on production (2026-09-30,
read-only): the full input query takes 3.4 s for 148k rows today and will read ~290k once the backlog
is done, so about 6 s of reading every half hour.

**The library table's sort.** `/api/library/advanced` sorted the full selection with the per-track
subqueries (label, genres, file) in the select list, and MariaDB evaluated them for every track before
the sort: sorting by BPM took **7.5 s** on production. The query now picks the page first (an inner
query over the joined tables with only narrow columns, `ORDER BY ... LIMIT`), and the outer query adds
the subqueries for that page alone. Measured on production with a stand-in for
`library_track_effective_bpm` (a second, non-unique `library_track_audio_features` join; the real
table joins on its primary key, so this is an upper bound): the whole BPM-sorted page **1.5 s**, the
narrow sort alone 0.9 s; the date sort, which has an index, stays under a millisecond. The count query
beside it went from 0.44 s to 0.65 s with the stand-in; with the real table MariaDB's table
elimination drops the join entirely from any query that reads no `eb` column, since it is a LEFT JOIN
on a primary key.
Tracks without a BPM sort last in both directions (`eb.bpm IS NULL, eb.bpm <dir>`), ties broken on the
id so pages neither repeat nor skip a track.

**Display.** Every client prints the effective BPM through `bpmFormat.formatBpm`: "150" for a
measurement, "≈152" otherwise (`/advanced` and `/tracks` return `bpm_approximate` as 0/1, the details
answer `bpm_approximate` as a boolean plus `bpm_source`, `bpm_confidence`, `bpm_folded`). The
analytics caveat under the histogram now says what the tempo is instead of "raw detection".

## API Contract

Router `services/music_manager/routers/bpm.py`, mounted at `/api/library/bpm`, any valid API key
(`verify_api_key`). The first merge request changed no existing endpoint. Issue #141 changes what the
existing BPM fields *mean* -- additively, no field is removed or retyped:

| Endpoint | Change |
|---|---|
| `GET /api/library/advanced` | `bpm` is the effective BPM; new `bpm_approximate` (0/1, null without a BPM); `sort=bpm` sorts on it, missing last, ties by id; `bpm_min`/`bpm_max` and a bare-number `q` filter on it. |
| `GET /api/library/tracks` | `bpm` is the effective BPM; new `bpm_approximate`. |
| `GET /api/library/tracks/by-path` | `bpm` is the effective BPM, resolved live; new `bpm_source`, `bpm_confidence`, `bpm_approximate`, `bpm_folded` (all null without a BPM). |
| `GET /api/analytics/*` | The BPM filters, `summary.coverage.bpm` and `bpm-histogram` read the effective BPM. |
| `GET /api/feeds/{slug}` | Each track's `bpm` is the effective BPM; new `bpm_approximate`. |

No client reads a changed field in a way the new values break: the web UI is updated in the same
change, and MuMa Mobile's native code reads none of them.

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

The estimator and the worker that fill `library_track_bpm`; they ship in the second merge request.

### Choosing the estimator

Measured with `tools/bpm_eval.py` on 399 production files copied read-only to
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

### Worker (`services/music_manager/bpm/worker.py`, container `muma-bpm-analyzer`)

**Where it runs.** Its own long-running service in docker/docker-compose.yml, from the tools image,
with `python -m services.music_manager.bpm.worker`. Not a thread in music-manager, for two reasons:
music-manager's image has no ffmpeg, and 74,568 library files are `.m4a`, which libsndfile cannot
decode; and CPU-heavy work in the API process has starved the API before (the tagger and scan-lock
incidents). The container has `cpus: 2` (`MUMA_CPUS_BPM`) and `mem_limit: 768m`
(`MUMA_MEM_LIMIT_BPM`), the usual hardening (all capabilities dropped but the four file ones,
`pids_limit: 256`), and every analysis process runs at nice 19 and in the idle I/O class. The music
share is mounted read-only; the analyzer writes no tags (the tagger does, since issue #139:
[bpm-tag-writeback](../bpm-tag-writeback/technical.md)).

**Settings** (Beheer → Config → BPM, all re-read every round from music-manager's `config.json`,
which the container mounts read-only -- ConfigStore reads its file once per process, which is
wrong for a process that lives for weeks): `bpm_analysis_enabled` (default on),
`bpm_analysis_paused`, `bpm_analysis_workers` (2, 1-8), `bpm_analysis_excerpt_seconds` (60, 20-180),
`bpm_analysis_skip_forms` (`set,liveset,podcast,interview,preview`), `bpm_analysis_max_minutes` (15).

**A round.** `DUE_SQL` picks up to 48 tracks with no current `library_track_bpm` row, highest
`library_tracks.id` first: new downloads and imports get the highest ids, so they are measured in
the next round (at most `IDLE_SECONDS` = 5 minutes after the scanner indexed them once the backlog is
done) without a separate announce path. A row is current while `method` equals `estimator.METHOD`
and the file's `file_mtime`/`file_size` match what was measured; a failure is retried after seven
days, at most three times, or at once when the file changed. For each track the pool decodes
`ffmpeg -ss <30% in> -t 60 -i <file> -ac 1 -ar 11025 -f f32le` (a container seek: only the excerpt
crosses the CIFS mount) and runs the estimator. The main process chooses each estimate's octave on
the track's evidence (`octave.choose_octave`; until bug report 140 it folded into the band of the
track's genres, or of its primary artist's commonest genre -- which is what put André Hazes at 256)
and upserts the batch with the raw estimate, both confidences and the comb scores.
Resumable by construction: the queue is whatever has no current row, so a restart, pause or crash
continues where it stopped.

**Progress.** An INFO summary every ten minutes ("analysed N, failed M since start, R remaining,
X/h") under source `bpm-analyzer`, and a JSON status file (`/app/state/status.json` in the worker,
`/app/data/bpm-analyzer/status.json` in music-manager) with state, counters, rate and ETA. `/health`
reports it as `bpm_analysis` and as a `bpm-analyzer` entry in `heartbeats`, but **not** in
`threads`: `threads` decides the status code, which is also music-manager's own container
healthcheck, and another container being down must not make music-manager look unhealthy (or get
it restarted).

**Expected duration** (measured 2026-09-29, read-only). The queue on production is about 267,000
tracks (form `track`, at most 15 minutes). Reading a 60 s excerpt over the CIFS mount took 0.06 s
median (0.09 s p90, 55 random files, from the music-manager container). The estimator took 0.15-0.30 s
per excerpt on the production CPU at nice 19 (0.08 s on the workstation). ffmpeg's decode of a 60 s
MP3 excerpt with resampling measured 0.4 s on a heavily loaded workstation; call it 0.3-0.8 s on the
production host. So one worker needs roughly 0.5-1.2 s per track, two workers 1.7-4 tracks a second:
**the whole backlog takes roughly one to two days** (18-44 hours) with the defaults, after which only
new tracks are measured, within minutes of arriving. The status file's `rate_per_hour`/`eta_hours`
give the real number after the first hour. Doubling `bpm_analysis_workers` roughly halves it, at the
cost of a second core that the overcommitted host may not have to spare.

## Cross-App Impact

- music-manager: new tables/router/config, no change to an existing endpoint.
- frontend (the web player, and the phone app, which renders the same web UI): the BPM page and the
  pill in `TrackList`.
- LMS: none (`getSongsByPath` already exists).
- Deployment: a new `bpm-analyzer` service in docker/docker-compose.yml (tools image), started by the
  normal deploy; `MUMA_CPUS_BPM` / `MUMA_MEM_LIMIT_BPM` override its ceilings (muma-ops docs/deployment-production.md).
- MuMa Mobile native (Android Auto browse tree): none in this change; the BPM folder followed in
  issue #140 ([android-auto-bpm](../android-auto-bpm/technical.md)), on these two endpoints unchanged.
- Issue #141: a new table (migrate_v51) that the bpm-analyzer fills; the web UI's library table,
  inspector, analytics caveat and track details sheet print the effective BPM with "≈". LMS: none --
  it reads BPM from the file tags itself and MuMa passes it nothing.

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
7. The estimator measures synthetic click tracks at 150.0, 155.0, 172.5 and 210.0 BPM within
   0.1-0.15 BPM, a 75 BPM track folds to 150 in the hardstyle band, noise gets low confidence, and
   too little audio or the wrong sample rate is refused (`test_bpm_estimator.py`).
8. The worker reads its settings from the config file over the environment and clamps them; skips
   the configured forms and long files; queues newest first; does nothing while paused or off and
   resumes where it stopped; resizes its pool when the worker count changes; survives a failed
   round; writes a status file /health reports without changing the status code
   (`test_bpm_worker.py`, `test_health.py`); and its queue, counts, genre fallback and upsert run on
   a real MariaDB, including the retry of a failure and the re-measurement of a replaced file
   (`BpmBrowseSqlTest`).

9. Issue #141: `effective_table.sync` writes only the difference, deletes rows whose track lost its
   tempo, and narrows to given ids (`test_bpm_effective_table.py`); the worker syncs in full every
   interval also while paused, syncs a round's tracks right after it, and survives a failed sync
   (`test_bpm_worker.py`); the filters, sort and histogram read `eb.bpm` only
   (`test_analytics_filters.py`, `test_library_advanced.py`); by-path resolves live
   (`test_library_router.py`); and on a real MariaDB the synced table drives the table's order (missing
   last in both directions, stable paging), filter, search term, `/tracks`, the histogram, the
   coverage and the details (`BpmBrowseSqlTest.test_the_effective_bpm_table_feeds_every_sql_reader`).
   The table, inspector and details sheet print "≈" for a value that is not measured (`bpm.test.js`,
   `trackTable.test.js`, `trackInspector.test.js`, `trackFile.test.js`).

## Related Docs

- [docs/api-specification.md](../../api-specification.md), "Browse by BPM".
- [services/ml-analyzer/DEPRECATED.md](../../../services/ml-analyzer/DEPRECATED.md) -- where the old
  values came from.
- [docs/designs/feeds/](../feeds/) -- the `library_path` + `getSongsByPath` pattern this reuses.
