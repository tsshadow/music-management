# Song grouping key — Technical Design

Implements [functional.md](functional.md). The ranking (`KIND_ORDER`, `version_kind`,
`version_score`) is untouched.

## Data Model

No schema change. `library_works.work_key` keeps its shape `<artist>:::<title>`, plus the reserved
`track:` and `split:` prefixes. Auto-split works use `split:<track_id>` and set
`library_tracks.work_locked = 1`, the same as `POST /api/songs/tracks/{id}/split`.

## Key rules (`services/music_manager/song_versions.py`)

- `_MODIFIER_TOKENS` gains `pro`, `audio`, `music`.
- `_is_version_marker(text)` is true when every token is a modifier, or when the text contains
  `official`, at least one upload word (`video`, `videoclip`, `clip`, `visualizer`, `visualiser`,
  `audio`, `lyric`, `lyrics`, `preview`), and every other token is a modifier or in
  `_GENRE_TOKENS`.
- `_strip_grouping_markers(title)` loops over `_strip_one_marker`, which first drops trailing
  decoration (`[^\w)\]]+$`). It then strips one of: a trailing bracket group (may leave nothing, as
  before), a dash suffix (`\s[-–—|｜]\s` with text in front), or a tail starting with the word
  `official` (with text in front). A trailing bracket that is not a marker stops the loop.
- `version_free_title` uses it. `version_kind` still uses `_strip_version_brackets`, so kinds
  are unchanged.
- `grouping_artist(artist)` takes the first part of `_COLLAB_SPLIT` (`&`, `+`, `x`, `×`,
  `feat.`, `ft.`, `featuring`, `vs.`, `,`) and returns `''` for an `official` kind phrase.
  `work_key` uses it for the artist half.

## False-merge guard

- `services/music_manager/song_work_audit.py` (pure): `distinct_lengths` (chained within 3 s),
  `assess_work` (verdict `split` when lengths > `AUTO_SPLIT_LENGTHS` = 12; otherwise `suspicious`
  on lengths > 6, ratio > 1.5 with >= 4 lengths, or > 12 versions over > 3 years), and
  `suspicious_works`.
- `song_version_worker.split_false_merges(cursor, touched)` runs in `group_once` before the
  canonicals are recomputed. One `GROUP BY ... HAVING COUNT(*) > 12` query filters the touched
  works, and only those candidates have their members read. `split_work` moves each unlocked
  member with `WHERE id = %s AND work_id = %s AND work_locked = 0`, clears a pin that named a moved
  member, and recomputes canonicals. `find_suspicious_works(cursor)` feeds the report.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| none | | | |

The report is a CLI (`scripts/repair_song_works.py --report`). The Versies page (!1015) already
sorts works by version count, so the worst false merges sit at the top of it.

## Cross-App Impact

None. LMS receives the new canonicals through the existing hourly song-version sync.

## Technical Acceptance Criteria

1. `test_song_grouping_key.py`: every same-song pair shares a key, and every must-stay-apart pair
   (remix, VIP, bootleg, named edit, genre mix, anthem, different lead artists, collab with a
   different title) does not.
2. `test_song_work_audit.py`: the 20-length series is `split`, radio+extended and a popular song
   with few lengths are not flagged, and 12 lengths is not enough to split.
3. `test_song_work_split.py`: split writes locked `split:` works with the precondition in the
   statement, clears the pin, and leaves one-song works alone.
4. `RepairSongWorksTest.py`: dry-run movement counts, pinned tracks kept, and `--dry-run` and
   `--report` issue no writes.

## Related Docs

- [Bug report 098](../../bug-reports/098-song-grouping-key.md)
- [Song versions and canonical](../../superpowers/specs/2026-08-23-song-versions-and-canonical-design.md)
- `scripts/prod/person/regroup-song-works.sh`
