# Track form and performance date — Technical Design

Implements [functional.md](functional.md).

## Data Model

### MuMa (MariaDB)

`library_tracks` gets two nullable columns (db_init `ALTER ... ADD COLUMN IF NOT EXISTS`,
`migrate_v42_track_form.sql`):

| Column | Type | Meaning |
|---|---|---|
| `form` | `VARCHAR(16) NULL`, indexed (`idx_tracks_form`) | `track` / `set` / `liveset` / `podcast` / `interview` / `preview`; NULL = not classified (no duration) |
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

0. an interview or a DVD preview → `interview` / `preview`, at any length and with no duration
   too (`derive_non_music_form`, [non-music-forms](../non-music-forms/technical.md))
1. no duration → `None`
2. duration < 600 s → `track`
3. top folder `Livesets` or `Telegram` → `liveset`; `Podcasts` → `podcast`
4. approved podcast show in title + path → `podcast`
5. festival in title, or in path with a year → `liveset` -- except under top folder `EPs`
   (`LABEL_FOLDERS`), where it also needs a live marker in title or path (`_LIVE_MARKER`: the
   whole word `live`, `liveset(s)`, `dvd` or `dvda`, after `_ - . ( ) [ ]` are read as spaces);
   without one → `set` (bug report 109)
6. otherwise → `set`

Podcast before festival: "Defqon.1 Podcast #12" names a festival with no year and is an episode.

The label-tree exception exists because a label release names a festival for reasons other than
having been recorded there -- a track title ("Decibel Dictature"), or the label's mix album for an
edition. Neither length nor performance date tells those from the DVD rips and live registrations
among the label releases (measured on production, bug report 109); the word "live" or "DVD" does.
The folder name is the literal `EPs` like the other folder rules, not `eps_folder_path`.

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
  statement). A server without the columns is skipped. The push converges (bug report 093): muma
  rows are read sorted by path and only the first row per path is pushed -- the scanner's own
  media row (its `file_path_hash` is the hash of its path) before a stale duplicate, then one that
  knows a form, then the newest -- and the UPDATE compares before it writes
  (`WHERE ... AND (form IS NOT ?1 OR performance_date IS NOT ?2)`). A second run over an unchanged
  library issues no UPDATE and so never takes LMS's write lock.
- **Unclassified tracks**: `form` stays NULL when the length is unknown. The pass logs how many of
  those have no media file (rows a retag left behind, bug report 042 -- deliberately left NULL)
  and how many have a file but no length; the scanner re-reads a file whose media row has no
  length even when its mtime and size are unchanged, so the second kind drains on the next walk.

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
- **MuMa Mobile native** (issue #47), no server change -- `getSongs` already took both:
  - `core/subsonic-api`: `TrackForm` (`FORMS`, `SET_FORMS`, `known`, `sanitize`) and `form`/`year` on
    `SubsonicAPIDefinition.getSongs`. `MusicService.getSongs` gains `forms`/`year`;
    `RESTMusicService` passes forms through `TrackForm.sanitize`, the single choke point, so no
    caller can put an unknown form on the wire. `OfflineMusicService` applies `year` to the date tag
    and ignores `forms` (the cache has no form; the LENGTH cluster still keeps it on the sets side).
  - Android Auto: pseudo tag type `FORM` (`BrowseQuery.TAG_FORM`), same id grammar as `LINEUP`:
    `MEDIA_TAG_LIST|long|FORM` lists `TrackForm.SET_FORMS` statically, `MEDIA_TAG_TRACKS|long|FORM|
    <form>|<year>|<sort>` is an ordinary tag folder. `BrowseQuery` carries `forms` and `year`.
  - Voice (`core/voice`): `ParsedQuery.forms`, `Target.Filtered.forms`/`year`, explanation field
    `FORM`; `VoiceBridge` adds `form` (comma-separated) and `year` to the web's `getSongs` params.
    An artist slot that places no artist is tried as a festival on the sets side.
  - Podcast show by name (issue #88): `LibraryVocabulary.podcasts()` returns `PodcastShow(name,
    aliases)`, asked only when the spoken forms include `podcast` ("podcast", "aflevering",
    "episode" all name it). `MusicServiceVocabulary` reads the names from `getTags(PODCAST)` -- the
    only values ever sent -- sorted by episode count, and lends each the aliases of the curated show
    of the same name from `GET /api/rules/podcasts?state=white` (optional: unreachable means names
    only). `QueryResolver.podcastNamed` tries the artist slot, then the free term (skipped when it is
    exactly a genre): name + " podcast", then name, then alias, exact; then `VoiceQuery.match`'s
    partial fallback over names and aliases for four letters or more. Ties go to list order. A hit
    adds `PODCAST=<show>`, drops `podcast` from `forms` (unclassified new episodes would be hidden)
    and consumes the slot it came from; the explanation gets field `PODCAST` (and no `SETS` row).
  - Presets: `form` key in the preset JSON (`TileInfo.form`, `presets.js`), written only for a sets
    preset and only when it is one of `SET_FORMS`; the preset builder has a Soort select in sets mode
    and "save as preset" carries the filter bar's Soort.
  - **Year rule, all three paths**: with a form and exactly one year, the year goes as `year` (filing
    year) instead of the `YEAR` cluster; otherwise the cluster as before. The LENGTH cluster is kept
    beside `form` in every path -- redundant on the server (a form implies the length) but it keeps
    offline mode on the right side of ten minutes.

## Technical Acceptance Criteria

1. `derive_form` / `derive_performance_date` unit tests cover every rule row, the precedence
   (podcast before festival, length before folder), a missing duration, and the label-tree
   exception (festival alone → `set`, festival plus live marker → `liveset`, outside `EPs`
   unchanged).
2. `classify_library` writes only differing rows, clears a performance date that no longer applies,
   and leaves a window's rows unchanged when nothing changed.
3. The push skips a server without the columns and writes only rows the server disagrees with;
   run twice -- including two muma rows naming one file -- the second run issues no UPDATE.
4. LMS `Track_findByForm_bothBuilders` and `Track_findByFilingYear_bothBuilders` (both builders,
   plus `countAdvanced`) pass, the migration test sees step 122 and re-runs it, and the `TrackForm`
   tests refuse an unknown form (`parseTrackForms`, shared by both endpoints).
5. `tests/integration/test_router_sql.py` runs the advanced/analytics SQL with `form` and a year
   range against MariaDB; `tests/integration/test_schema.py` expects both columns.
6. The frontend sends `form` only in the sets view; the chip is absent in the songs view.
7. MuMa Mobile (issue #47): `TrackFormTest` (only known forms survive `sanitize`), `BrowseQueryTest`
   (preset and form-row round trips, filing year only with a form), `MediaLibraryBrowseTabsTest`
   (Soort row in Sets only, static list, `form`/`year` reach `getSongs`, a mangled id sends no form),
   `VoiceFormTest` + `MediaLibraryVoiceSearchTest` (spoken forms to request params, unknown forms
   dropped) and `VoiceBridgeTest`; web `presets.test.js`, `presetBuilder.test.js`, `voiceView.test.js`.
8. Issue #88: `VoicePodcastTest` (NL/EN phrases, alias and partial match, word put back, no match
   keeps the form, genre stays a genre, only listed names sent, tie by list order, no lookup
   outside a podcast request) and `MusicServiceVocabularyTest` (tag values, aliases joined by name,
   alias outage).

## Related Docs

- [product-goal.md](../../product-goal.md), "What \"from 2012\" means"
- `services/music_manager/release_date_sync.py`, `song_version_sync.py` (the two sync shapes reused)
- `docs/bug-reports/068-deploy-hangs-on-no-op-alter-metadata-lock.md` (why the migration only adds)
