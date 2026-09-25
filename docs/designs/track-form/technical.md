# Track form and performance date — Technical Design

Implements [functional.md](functional.md).

## Data Model

### MuMa (MariaDB)

`library_tracks` gets two nullable columns (db_init `ALTER ... ADD COLUMN IF NOT EXISTS`,
`migrate_v42_track_form.sql`):

| Column | Type | Meaning |
|---|---|---|
| `form` | `VARCHAR(16) NULL`, indexed (`idx_tracks_form`) | `track` / `set` / `liveset` / `podcast`; NULL = not classified (no duration) |
| `performance_date` | `VARCHAR(10) NULL` | `YYYY-MM-DD`, only ever set when `form = 'liveset'` |

`VARCHAR(10)` like `release_date` (migrate_v24), so the two compare and COALESCE without casts.
The migration only adds columns and an index — no data is touched at deploy time. `ADD COLUMN` of a
nullable column is instant in MariaDB; the index build is online.

### LMS (SQLite)

`track` gets `form TEXT NOT NULL DEFAULT ''` and `performance_date TEXT NOT NULL DEFAULT ''`
(migration step 122, database version 123; mapped in `Track.hpp` so a fresh database gets them from
`createTables`). `scan_version` is not bumped: the columns say nothing about how a file is read.
Indexes in `Session::prepareTablesIfNeeded`: `track_form_idx ON track(form)`.

LMS never computes either value. The empty string is "MuMa has not said", and a form filter does
not match it.

## Derivation — one function

`services/common/track_form.py`:

```
derive_form(path, music_root, duration_secs, title, festivals, podcasts) -> str | None
derive_performance_date(form, path, title, festivals) -> str | None
```

Inputs are exactly what `library_tracks` + `library_media_files` hold (path, title, duration), so
the scanner and the hourly pass compute from the same facts and cannot flip-flop. `festivals` is a
`FestivalHelper`, `podcasts` a `PodcastHelper` — the objects the tagger's
`InferFestivalFromTitleRule` / `InferPodcastFromTitleRule` use, called the same way (festival: title,
then path with `require_year`; podcast: title + path). The tagger writes the FESTIVAL/PODCAST tags
from exactly these inputs, so reading the tags back would give the same answer while needing a file
read per track.

Order, first hit wins:

1. no duration → `None`
2. duration < 600 s → `track`
3. top folder `Livesets` or `Telegram` → `liveset`; `Podcasts` → `podcast`
4. approved podcast show in title + path → `podcast`
5. festival in title, or in path with a year → `liveset`
6. otherwise → `set`

Podcast before festival: "Defqon.1 Podcast #12" names a festival with no year and is an episode.

Performance date: only for `liveset`; the first festival match (same order as the tagger rule) that
has a year and an edition date for it.

## Writing it

- **Scanner** (`routers/scanner.py`, `process_file`): computes both for the file it is scanning and
  writes them with the track row. Helpers are reloaded per full run and per single scan, like the
  genre rules.
- **Hourly pass** (`services/music_manager/track_form_sync.py`, `classify_library`): walks
  `library_tracks` in id windows of 5,000 (the release-date sync's shape), recomputes, and
  `UPDATE`s only rows that differ. This is the backfill — the first pass after deploy writes the
  whole library in 70 short windows, later passes write only what a curation decision changed. It
  runs inside `run_lms_db_sync` before the per-server loop, so the push below sees fresh values.
  No file is touched, so the tagger queue is not involved.
- **Push to LMS** (`push_forms_to_server`, same module): per server, read-first/write-the-diff in
  batches of 100, reusing `song_version_sync`'s lock handling (`_write_batch` now takes the UPDATE
  statement). A server without the columns is skipped.

## Filtering

### LMS — both query builders

`Track::FindParameters` gains:

- `std::vector<std::string> forms` — `AND t.form IN (...)`
- `std::optional<int> year` — `AND substr(COALESCE(NULLIF(t.performance_date, ''), t.date), 1, 4) = ?`

`t.date` is what the `YEAR` cluster is built from (`TrackMetadataParser`), so for everything without
a performance date the answer is the one the cluster gave. Both `createQuery` (`find`, `findIds`,
radio) and `buildAdvancedQueryBody` (`find_advanced`, `countAdvanced`) implement both; tests in
`libs/database/test/Track.cpp` cover each builder so neither can drop the filter silently again.

### API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `getSpotifyTracks` (LMS) | new `form=<f>[,<f>...]`; `year=<yyyy>` now matches the performance date for live sets | unchanged | unknown form → `BadParameterGenericError` (Subsonic error 0, naming `form`) |
| `getSongs` (LMS) | new `form` (repeatable or comma-separated), new `year=<yyyy>` (same semantics); the `YEAR` cluster keeps its tag-year meaning | unchanged | unknown form → `BadParameterGenericError` |
| `GET /api/library/advanced`, `/api/analytics/*` (MuMa) | new `form=<f>` (repeatable); `year_min`/`year_max` now compare the effective year `COALESCE(performance year, release_date year, af.release_year)` | unchanged | unknown form → 422 |

Non-breaking: every new parameter is optional. The `year` change on `getSpotifyTracks` widens a
match for live sets only (a live set with no performance date matches exactly as before).

## Cross-App Impact

- **LMS**: migration, fields, both builders, `getSpotifyTracks`, `getSongs`.
- **music-manager**: schema, scanner, hourly pass + push, `analytics_filters`.
- **frontend** (web and the phone, which bundles it): Soort chip in the sets view
  (`FilterBar.svelte`, `lib/trackForm.js`), `form` sent to `getSpotifyTracks`.
- **MuMa Mobile native** (Android Auto, voice): not changed; the server accepts `form` on
  `getSongs` for a follow-up (open-work).

## Technical Acceptance Criteria

1. `derive_form` / `derive_performance_date` unit tests cover every rule row, the precedence
   (podcast before festival, length before folder), and a missing duration.
2. `classify_library` writes only differing rows, clears a performance date that no longer applies,
   and leaves a window's rows unchanged when nothing changed.
3. The push skips a server without the columns and writes only rows the server disagrees with.
4. LMS `Track_findByForm_bothBuilders` and `Track_findByFilingYear_bothBuilders` (both builders,
   plus `countAdvanced`) pass, the migration test sees step 122 and re-runs it, and the `TrackForm`
   tests refuse an unknown form (`parseTrackForms`, shared by both endpoints).
5. `tests/integration/test_router_sql.py` runs the advanced/analytics SQL with `form` and a year
   range against MariaDB; `tests/integration/test_schema.py` expects both columns.
6. The frontend sends `form` only in the sets view; the chip is absent in the songs view.

## Related Docs

- [product-goal.md](../../product-goal.md), "What \"from 2012\" means"
- `services/music_manager/release_date_sync.py`, `song_version_sync.py` (the two sync shapes reused)
- `docs/bug-reports/068-deploy-hangs-on-no-op-alter-metadata-lock.md` (why the migration only adds)
