# A Retag That Changes Title Or Primary Artist Strands The Track's Ratings And Listens

# status: fixed — the scanner relinks the old track row, links are recomputed, a repair endpoint exists; the production run of that repair is still to do

# reported problem
Found by reading the scanner, not by a user report, but it explains two things that were seen:
ratings that seem to vanish after a retag, and a song whose "real" file LMS marks as a hidden
version.

`library_tracks.track_uid` is `sha256(title-duration-primary_artist_id)`
(`services/music_manager/routers/scanner.py`, `process_file`). A retag that fixes a title, or that
reorders or splits the artists (bug report 053 did this to every file its rules touched), produces a
new `track_uid`, so `process_file` inserts a new `library_tracks` row and repoints the file's
`library_media_files` row at it. Nothing in `services/`, `scripts/` or `tools/` ever deleted a
`library_tracks` row, so the old row stayed, without a file, holding:

- every rating (`rating_tracks.entity_id` is the `track_uid`);
- every listen (`scrobble_listens.track_id` is the id);
- the work membership. `song_version_worker._BEST_TRACK` LEFT JOINed the media files and broke score
  ties on `created_at ASC`, so the older, fileless row could win the canonical, and
  `song_version_sync` then wrote `is_canonical = 0` for the file that actually exists.

A second, smaller defect sat next to it: labels and channels were only ever `INSERT IGNORE`d, while
artists and genres are deleted and rewritten per file. A corrected publisher therefore kept its old
label link forever, although `docs/designs/scanner/functional.md` promises the label is updated on
rescan.

# Possible reason
The scanner treated `track_uid` as a stable identity. It is not: it is derived from exactly the
fields a retag exists to correct. Every table that references a track row was keyed on a value the
scanner could silently replace, and the only code that creates track rows never looked back at the
one it had just abandoned.

# solution
- `services/music_manager/track_relink.py` — `relink_track(cursor, old, new)` moves the ratings
  (the newer `updated_at` wins when a user rated both, and the timestamp is preserved), the listens
  (UPDATE IGNORE on the unique key; a leftover is a duplicate and is dropped; `listened_at` is
  preserved because the column may still carry ON UPDATE, bug report 039), the ml-analyzer rows and
  any work pin, then deletes the old row. It refuses when the old track still has a media file.
- `process_file` reads the file's previous `track_id`; when the file moves, the media-file repoint
  and the relink run in one explicit transaction (`conn.begin()` — the pool is `autocommit=True`).
  If the old track keeps another file, only its label and channel links are recomputed.
- Labels and channels are now recomputed from every file of the track (`ScannerManager._write_links`):
  delete and reinsert, with a missing sibling supporting nothing and an unreadable one only
  preventing removal.
- `_BEST_TRACK` inner-joins `library_media_files`: a fileless track can no longer be canonical.
- For rows orphaned before the fix: `POST /api/scanner/relink-orphans` (admin only) runs
  `relink_orphaned_tracks` in the background. An orphan is relinked only when exactly one track with
  a file has the same normalised title and duration and the same primary artist or the same set of
  artists; the totals are logged as an INFO event and returned by `GET /api/scanner/relink-orphans`.
  It is idempotent and never runs on its own.
- Tests: `services/music_manager/tests/test_track_relink.py`, `test_scanner_relink.py`, and
  `tests/integration/test_track_relink.py` (retag carries rating and listen; a track with a second
  file is kept; the orphan repair fixes a seeded orphan and a second run does nothing; a corrected
  publisher replaces the label link).

Still open: the repair has not been run on production. An orphan whose title changed beyond
normalisation (not just case or punctuation) has no match and is reported as `unmatched`; those
need a person. See [open-work.md](../open-work.md).

Follow-up: the first scan's file-name titles, which this key can never match, are relinked by a file-name key, and what no key matches is purged or listed. See bug report 104.
