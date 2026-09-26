# The orphan relink dry run took hours and held the scanner lock

# status: fixed

# reported problem
The first dry run of `POST /api/scanner/relink-orphans` on production (0.77.0, 2026-09-26) walked
81,879 orphans at about 2 per second once past the May file-name stubs: after 25 minutes it stood
at 53,563, an hour later at 59,384. The run holds the scanner lock, so no scan could run meanwhile,
and the operator script's option A runs the same walk twice more (a dry run, then the relink).

# Possible reason
`find_relink_target` ran `_CANDIDATES` once per orphan that has a duration and an artist.
`ABS(t.duration_secs - %s) < %s` and the OR over the artist cannot use an index, so every call
scanned `library_tracks` (~400k rows) with an EXISTS on `library_media_files` per row. The
file-name key was already built in memory once per run; the metadata key was not.

# solution
A bulk run reads every track that has a file and a duration once (`_CANDIDATE_TRACKS`) and keeps
only the normalised titles some orphan carries (`build_metadata_index`). `find_relink_target`
takes that index and filters its few rows per orphan in Python with the same rules -- title,
duration within 0.5 s, primary artist or a credited artist, then the artist-set comparison. The
single-orphan path the scanner uses keeps the SQL. Idempotence and the per-orphan transaction are
unchanged.
