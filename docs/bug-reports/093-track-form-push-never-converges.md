# The track-form push rewrote ~1,700 LMS files every hour, and 90,297 tracks never got a form

# status: fixed

# reported problem

On production (0.75.1) the hourly `track_form_sync` run logged:

```
track-form pass considered 378864 tracks, wrote 0 in 12.9s
server-stable: track-form push considered 308312 files, wrote 1711
```

and the next hours wrote 1713, 1706, 1704. The muma pass was stable, but the push into LMS rewrote
roughly the same 1,700 files every hour -- each run taking LMS's SQLite write lock, which is what
makes a rating request 500 during the hourly sync. Separately, `library_tracks.form` was NULL for
90,297 of 378,917 tracks, and the pass wrote 0, so those were never classified.

# Possible reason

Measured read-only on production on 2026-09-26 (muma MariaDB via the read-only account; LMS
`/app/data/stable/lms.db` opened with `mode=ro` inside the music-manager container):

- **Two muma media rows for one file.** `library_media_files` has 1,481 paths held by two rows
  each (2,962 rows). `file_path_hash` is unique, but for 1,493 rows it is not the SHA-256 of the
  path they hold; every one of them has `last_seen` 2026-07-11 12:18, i.e. one event left them
  behind. Each points at a stub track with the file name as title and no length, so `form` NULL.
  The scanner looks rows up by hash, so it only ever updates its own row and never sees the stale
  one. The push read both rows, and both mapped to one LMS path: in one run the scanner's row
  wrote `track`, a later chunk found `track` and the stale row wrote `''` back. 882 such pairs
  disagree, two writes each: ~1,700 a run, and LMS ended every run on the wrong value.
  Nothing else explained the writes: 893 rows differed at the time of the check, all
  `'' -> track/set/liveset`, all on a duplicated path; no LMS path had two `track` rows, no type
  or date format mismatch.
- **NULL forms.** All 90,297 NULL-form tracks have no length (`classify` returns NULL without
  one). 50,843 have no media file at all -- rows a retag left behind (bug report 042). 39,454 have
  a file: 1,489 are the stale-duplicate stubs above, 37,965 are real files (almost all under
  `EPs/`, 65 under `Soundcloud/`) scanned in May 2026 with the file name as title and no length.
  Their media row also has no length, and because the file's mtime and size never changed, the
  scanner's fast path never read them again. Reading a sample of 400 now gives a length and a real
  title for every one, and LMS has a duration for all of them.

# solution

- `push_forms_to_server` reads muma rows sorted by path (byte order) and pushes only the first row
  per path, carried across chunk boundaries: the scanner's own media row first
  (`file_path_hash = SHA2(file_path, 256)`), then one whose track has a form, then the newest. Two
  rows naming one file now give one answer, so a second run writes nothing. The skipped rows are
  counted in the log line.
- The LMS UPDATE compares before it writes (`WHERE absolute_file_path = ?3 AND (form IS NOT ?1 OR
  performance_date IS NOT ?2)`). A run that finds nothing to change issues no UPDATE and takes no
  write lock; a row another writer settled between the read and the write is left alone.
- Tracks without a media file stay NULL on purpose: they are not playable tracks. The form pass
  now logs `no form: N without a file, M without a length`, so the two kinds are visible.
- The scanner re-reads a file whose media row has no length even when mtime and size are
  unchanged. The ~38,000 real files get their length, title and form on the next full walk (a
  changed title means a new track row; the retag relink moves ratings and listens across as it
  does for any retag). A file that still yields no length is re-read on every walk, which is
  accepted: every readable audio file has one.

Tests: `test_track_form_sync.py` (run twice, duplicate rows in one chunk and across chunks, no
UPDATE statement on the second run via SQLite's trace callback, the guarded UPDATE),
`test_scanner_tagger_routers.py` (a length-less row is read again), and
`tests/integration/test_router_sql.py` (the sort and SHA2 preference on real MariaDB).

Left open (the GitLab issues): deleting the 1,493 stale media rows and their stub tracks, and
checking on production that the push writes 0 on its second hourly run.

The stale rows (GitLab issue #124): `merge-stale-media-rows.sh` folds each
one into the live track for the same file and deletes it with its stub. Measured on production on
2026-10-02: 1,493 rows, 1,481 matched by path, 10 by the path with a doubled release folder
collapsed, 2 folder rows (`/mnt/music/music/EPs/Dirty Workz`) that nothing refers to; 1 rating
and 3 listens move, nothing is kept. Ratings keep the highest value per user.
