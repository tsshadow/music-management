# One canonical version per song in the player — Technical Design

Implements [functional.md](functional.md). Code: `services/music_manager/song_version_sync.py`.

## Data Model

No schema change. The push writes the existing LMS `track` columns from migration 118 (`work_id`,
`is_canonical`, `version_kind`, `version_score`). muma's model is read unchanged:
`library_works.canonical_track_id`, `library_tracks.work_id/version_kind/version_score`, and per file
`library_media_files.id/file_path/file_path_hash/file_size/duration_secs`.

Invariant after a pass, per server database: for every `work_id` present in `track`, exactly one row
has `is_canonical = 1`, provided muma knows every file of that work the server has. Rows with
`work_id` NULL keep `is_canonical = 1`.

Selection, per work, over the server rows muma could map (via `library_paths.candidate_paths`):

1. One muma row per path: sorted by `CAST(file_path AS BINARY)`, the scanner's own row
   (`file_path_hash = SHA2(file_path, 256)`) first, then the highest `mf.id` (bug report 093;
   `first_per_path`, shared with `track_form_sync`). One muma row per server row id.
2. Track: `canonical_track_id` if the server has at least one of its files; otherwise (named
   canonical absent, or none named) the track with the highest `version_score`, then the best file
   rank, then the lowest track id. Counted as `canonical_fallbacks` and logged each run.
3. File within that track, lowest `file_rank`: scanner's own row, `song_versions.format_tier`,
   higher `derived_bitrate`, higher `mf.id`.

Ungrouped files are written while streaming; files of a work are held in memory per work as
`_ServerFile` tuples (ints, no paths) until the stream ends, because one work's files are spread
over the path order. Roughly half the library is grouped, so a few tens of MB at most.

## API Contract

No API change. The Subsonic `isCanonical` attribute and the `canonicalOnly` filter keep their
meaning; only the stored values become correct.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| none | | | |

## Cross-App Impact

None in code. The app and Android Auto benefit without a change (`canonicalOnly`, default on).

## Technical Acceptance Criteria

1. A work whose canonical track has two files in the server gets exactly one canonical row, the
   better file.
2. A work whose canonical track has no file in the server gets exactly one canonical row, on the
   best version the server has, and `canonical_fallbacks` counts it.
3. A path with two muma media rows is pushed once, from the scanner's own row.
4. A second run over an unchanged library writes 0 rows and issues no UPDATE or BEGIN.
5. The UPDATE is keyed on the server row id and guarded with `IS NOT` per column.

Covered by `services/music_manager/tests/test_song_version_sync.py` and
`tests/integration/test_router_sql.py::test_the_version_push_marks_one_canonical_row_per_work`.

## Related Docs

- `docs/superpowers/specs/2026-08-23-song-versions-and-canonical-design.md` — the version model.
- [Bug report 093](../../bug-reports/093-track-form-push-never-converges.md) — duplicate media rows,
  compare-before-write.
- [Bug report 097](../../bug-reports/097-lms-canonical-one-per-work.md).
