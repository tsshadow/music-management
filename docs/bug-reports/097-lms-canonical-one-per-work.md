# LMS showed some songs twice and lost others entirely in canonical-only lists

# status: fixed

# reported problem

The app (and Android Auto) hides non-canonical versions by default (`canonicalOnly`,
`Settings.kt:49`), and the server filters on the `is_canonical` column muma pushes into LMS's
`track` table (migration 118, `song_version_sync.py`). Measured read-only on production on
2026-09-26 in the stable `lms.db`: 341,116 tracks, 48,731 of them non-canonical, but

- **5,226 works had more than one canonical row**, so those songs appeared twice (or more) in every
  canonical-only list, and
- **1,081 works had no canonical row at all**, so the whole song disappeared from every
  canonical-only list in the app and in the car.

# Possible reason

`sync_song_versions_to_server` decided "canonical" per muma media file: a file was canonical when
its track was the one its work names (`library_works.canonical_track_id`). Two consequences:

- **A canonical track with several files marked all of them.** A muma track can own the FLAC and
  the MP3 of one release, or the same recording in two folders; 9,164 muma tracks own 57,067 files.
  On the muma side (prod, read-only, 2026-09-26) 5,902 works have a canonical track with more than
  one distinct file path -- the LMS count of 5,226 is the part of those whose files LMS has.
- **A canonical the server does not have left the work with none.** Every other version of the
  work was pushed as 0. When the canonical track's file is not in LMS -- or its path does not map
  through `candidate_paths` -- nothing was 1. On the muma side 797 works have a canonical track
  without any media file while one of their other versions does have one (the rest of the 1,081 are
  files LMS lacks or path spellings that do not map), and 3 works with files have no canonical at
  all (those were pushed as all-canonical, which was also more than one).
- The stale duplicate `library_media_files` rows from bug report 093 (1,481 paths with two rows,
  one of them on a stub track) hit this push as well: one LMS file could receive two answers per
  run.

# solution

`services/music_manager/song_version_sync.py` now decides per work, not per file:

- muma rows are read sorted by path (byte order) and only the first row per path is used -- the
  scanner's own row first (`file_path_hash = SHA2(file_path, 256)`), then the newest -- the rule
  093 introduced for the track-form push. The helper (`first_per_path`) now lives in
  `song_version_sync` and `track_form_sync` imports it, so the two pushes cannot drift.
- Each kept file is looked up in LMS (every spelling of the path, as before). Ungrouped files are
  settled at once (canonical, no work -- LMS shows a row without a work regardless). Files of a
  work are parked per work, as LMS row ids rather than paths, until the whole library is read.
- Per work exactly one LMS row gets `is_canonical = 1`: the best file of the canonical track --
  the scanner's own row, then the best format tier (lossless, 320, AAC, 192, rest; the song-version
  tiers), then the higher derived bitrate, then the newest media row. All other files of that track
  and every other version get 0.
- If LMS has none of the canonical track's files (or the work names no canonical), the best
  version LMS does have takes its place, ranked like `song_version_worker`: highest
  `version_score`, then its best file, then the lowest track id. The number of such works is
  logged every run (`N works, M of them canonical through a fallback`) and returned as
  `canonical_fallbacks`.
- Compare-before-write as in 093: rows that already agree are never written, so an unchanged run
  opens no write transaction, and the UPDATE is keyed on the LMS row id with
  `IS NOT` guards so a row settled by another writer in between is left alone. `matched` is now the
  number of rows actually changed; a second run reports 0.

Tests: `services/music_manager/tests/test_song_version_sync.py` (`OneCanonicalPerWorkTest`:
multi-file track, quality and newest tie-breaks, the scanner's own row, fallback, a work without a
named canonical, a work split across chunks, duplicate path rows, ungrouped tracks, idempotent
second run without write statements) and
`tests/integration/test_router_sql.py::test_the_version_push_marks_one_canonical_row_per_work`
(MariaDB plus an `lms.db` file).

**Measuring after the deploy** (read-only, against `/app/data/stable/lms.db` opened with
`mode=ro`). Both counts should be 0. What can remain is an LMS file muma no longer has a row for:
the push never touches it, so it keeps whatever work id an older run gave it.

```sql
SELECT COUNT(*) FROM (SELECT work_id FROM track WHERE work_id IS NOT NULL AND work_id <> 0
                      GROUP BY work_id HAVING SUM(is_canonical <> 0) > 1);
SELECT COUNT(*) FROM (SELECT work_id FROM track WHERE work_id IS NOT NULL AND work_id <> 0
                      GROUP BY work_id HAVING SUM(is_canonical <> 0) = 0);
```

The after-counts could not be taken from this branch: the fix is not deployed yet, and reading
`lms.db` needs a shell on the production host, which an agent session is not allowed. The first
hourly run after the deploy writes the corrections (on the order of 10,000 rows, in batches of
100); the second should log `wrote 0`. See docs/open-work.md.
