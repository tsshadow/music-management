# Audio Features Cover Nothing Anyone Listened To

# status: fixed

# reported problem
`library_track_audio_features` holds 90.107 rows, and every BPM- or energy-based feature reads 0%
coverage on the listened library. Measured on production 2026-08-17: every row joins to
`library_tracks`, yet **zero** belong to a track that was ever played and exactly one to a rated
track. Of 200 sampled listened tracks, 0 matched on `track_uid`, 0 on `internal_track_id`, and 91
on `file_path`.

It reads as "the analyzer never ran", which is why nothing was built on the data.

# Possible reason
The first diagnosis blamed the media-library rebuild for shifting every `library_tracks.id`. That
was wrong. Re-read of the code on 2026-08-21:

**The features table's primary key is not a track identifier.**
`library_track_audio_features.track_id` holds a `library_media_files.file_path_hash`.
`services/ml-analyzer/migrate_paths.py` says so outright — it joins `f.track_id = m.file_path_hash`.

**The readers joined it as though it were a track uid.** Both
`routers/analytics_filters.py:29` and `routers/library.py:59` carried:

```sql
LEFT JOIN library_track_audio_features af ON t.track_uid = af.track_id
```

A uid compared against a path hash matches almost nothing by construction.

**Some rows matched anyway, and that is what hid it.** `services/ml-analyzer/analyzer.py:235,241`
inserts its own `library_tracks` rows with `track_uid = path_hash`. Those joined. `routers/scanner.py:166`
writes a different uid, and scanner rows are the ones that get played — hence a table that "joins
fine" while covering nothing anyone listened to.

The unit suite could not catch this: it mocks the cursor, so it proves which columns a query names,
never that the two sides of a join hold the same kind of value. Both sides are opaque strings.

# solution
`internal_track_id` is the real foreign key to `library_tracks(id)` and is what the readers should
use. Two halves:

1. **The readers repointed** to `ON af.internal_track_id = t.id`.
2. **`migrate_v10_audio_features_relink.sql`** fills `internal_track_id` for the existing rows, by
   both routes that can still resolve: `f.track_id = m.file_path_hash`, and failing that
   `f.file_path = m.file_path`. It fills unconditionally, unlike `migrate_paths.py`, which only ever
   filled NULLs and so never repaired a row holding a wrong value. Prefix indexes on both
   `file_path` columns keep the path join off a 90k x 300k cross product.

New rows were never affected: `analyzer.py` already writes `internal_track_id` on insert.

Covered by `tests/integration/test_audio_features_link.py`, which runs against a real MariaDB —
a join-key bug cannot be tested against a mocked cursor. Six tests: a row keyed by path hash finds
its track, a row with only a path finds its track, a wrong id is repaired rather than left alone, a
row whose file the library no longer knows stays unlinked, the reader's join reaches a scanner
track, and — guarding the diagnosis itself — the old join key would still have missed it.

The production row counts above have not been re-measured since the fix. Coverage should be checked
against real data before anything is built on top of it.
