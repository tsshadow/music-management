# The Orphan Relink Could Not Match The First Scan's File-Name Titles, And Nothing Cleaned Up The Rest

# status: fixed — code and operator script done; the production run (`relink-orphans-by-filename.sh`) waits for the deploy. GitLab issue #71 stays open for the orphans a person has to decide.

# reported problem
Measured on production on 2026-09-26 (GitLab issue #71): 81,888 `library_tracks` rows have no
`library_media_files` row. The bulk repair of bug report 042 (`POST /api/scanner/relink-orphans`)
ran on 2026-09-24 and reported "425 of 82441 fileless tracks relinked, 82016 without a single
successor".

Breakdown by creation month: 50,828 orphans come from the first scan in May 2026. Their title is
the raw file name without extension (`04-lucy_furr_and_meander_-_damnation`), with no artist, no
duration and no form. 26,103 are from July, 4,196 from August and 752 from September, and nearly
all of those have real tag titles, artists and durations.

If an orphan's title is compared exactly against the basename-without-extension of every current
media file, 45,775 of the May stubs match exactly one file and 5,053 match several. Of the later
orphans, 2,822 match exactly one file and 272 match several.

References on the orphans, measured before any relink: 239 have listens (581 listens in all), 6
have a rating, none is pinned, and 121 have an ml label a curator reviewed (116 `human_verified`,
5 `do_not_train`). 35,002 have an unreviewed ml label under their `track_uid`, and 120 works name
one as `previous_canonical_track_id`.

# Possible reason
`find_relink_target` matches only on normalised title + duration + artist, and returns None when
the orphan has no artist or no duration. That rules out every May stub before a query is even
made. Their title is the one thing that still identifies them: the file name is re-parseable and
idempotent, because the first scan copied it verbatim.

Nothing ever deleted an orphan that no key can match. Most of those rows carry nothing (no listen,
no rating, no pin). They still count as tracks in any query that forgets to join
`library_media_files`, and the song-version worker can pull them into works. Bug report 100 found
77k works whose only members had no file.

# solution
- **File-name key** (`services/music_manager/track_relink.py`). The relink tries the metadata key
  first. When that finds no single successor, `find_file_name_target` relinks the orphan to the
  track whose file has exactly its title as the basename without extension. The index
  (`build_file_name_index`) is built once per run: one query over `library_media_files`, which
  fetches only `SUBSTRING_INDEX(file_path, '/', -1)` and keeps only the stems some orphan title
  equals. The per-orphan `LIKE` would have scanned ~345k rows 80,000 times. Several tracks under
  one name count as ambiguous: they are counted (`ambiguous_file_name`) and left alone. Two files
  of the same track, such as an mp3 next to its flac, still give one successor, because the index
  holds track ids. The orphan itself is never its own target. The comparison is exact, case
  included. Each orphan is still its own transaction, and the run is still idempotent.
- **Counts per key**: `relinked_metadata`, `relinked_file_name` and `ambiguous_file_name` appear in
  the totals, in the INFO event text and on `GET /api/scanner/relink-orphans`. That endpoint also
  returns `keys: ["metadata", "file_name"]` (so a caller can tell the new build before any run),
  `dry_run_supported` and a live `progress`.
- **Dry run**: `POST /api/scanner/relink-orphans?dry_run=1` counts what each key would relink and
  writes nothing. It is reported on GET only, not as an event.
- **Purge** (`services/music_manager/orphan_purge.py`, `POST/GET /api/scanner/purge-orphans`,
  admin only, `dry_run=1` supported). This runs after the relink. It deletes every orphan that no
  listen, no rating (on its `track_uid`), no work pin and no reviewed ml label points at. The
  deletes go in batches of 1000, one transaction each, under the scanner lock. Inside each batch,
  every guard is checked again in SQL with `FOR UPDATE`, so a listen or a file that arrived after
  the survey keeps its track (counted as `skipped_changed`). A purged orphan takes its artist,
  genre, label and channel links with it, plus its unreviewed ml labels (keyed on the `track_uid`,
  which no FK reaches). Any `canonical_track_id` or `previous_canonical_track_id` that names it is
  cleared, and a work that lost its canonical is recomputed at once. The ml-analyzer's
  `internal_track_id` is set to NULL (as its FK would do). Orphans that are referenced are kept and
  listed (`kept_list`: id, title and each count) so a person can decide.
  `radio_timeline.track_id` is left alone because it holds LMS ids, and so is
  `downloads_soundcloud_unavailable.track_id`, which holds SoundCloud ids. Radio history keeps
  following its own convention, which is to never touch it.
  `library_track_ml_predictions` is empty on production (the ml-analyzer is deprecated) and is not
  touched either.
- **Operator script** `relink-orphans-by-filename.sh`. It runs a preflight on
  the new keys, then the relink dry run, then a backup of every row either step touches, taken
  before anything is written. Then it relinks and verifies, runs the purge dry run with the kept
  list, purges and verifies, and optionally posts the kept list on #71.
- **Why the scanner itself needs no change (task 2).** `_settle_previous_track`, since 2026-09-23,
  already relinks the old row whenever a rescan repoints the same path to a new track. That was
  the only way the scanner made orphans: it never deletes a `library_media_files` row. A moved
  file gets a new media row, and the old row keeps its track alive. The May stubs were orphaned by
  rescans that ran before that code existed. The numbers back this up: after the 2026-09-24 run
  there were 82,016 orphans, and on 2026-09-26 there were 81,879 while the scanner and the tagger
  kept working. The count went down, not up. A file-name lookup inside `process_file` would need
  the same library-wide stem index for every scanned file, and it would only repeat what
  `_settle_previous_track` already does for the same path. The bulk relink is the right place.
- Tests: `services/music_manager/tests/test_track_relink.py` (file stem, index, unique /
  ambiguous / self / exact-case, metadata wins, dry run, totals per key),
  `test_orphan_purge.py` (survey per reference kind, batch SQL and ordering, dry run, batching and
  rollback, idempotent second run), `test_scanner_relink.py` (endpoints, dry-run pass-through,
  mutual exclusion, events), `tests/integration/test_track_relink.py` (both against MariaDB, and
  the dry-run endpoints write nothing), and `tests/unit/test_relink_orphans_script.py` (the
  operator script against fake ssh/curl: dry run only posts dry runs, the backup comes before the
  first write, it stops on the old build, and P refuses while anything is still relinkable).

Still open (issue #71): the orphans no key matches that a user's listen, rating or reviewed label
points at. Also the metadata-title orphans whose title changed beyond normalisation. Works left
with no member after the purge are not deleted. They were already fileless, and the song-version
worker never picks a fileless canonical.
