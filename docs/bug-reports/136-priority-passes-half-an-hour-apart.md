# Priority Passes Come Half An Hour Apart During A Library Scan

# status: fixed

# reported problem
GitLab issue #132, follow-up to bug report 126. During a library-wide LMS scan on production
(2026-09-28, 0.82.x), the folders the downloader and tagger announced were read in priority
passes, but about 27 minutes apart (12:09, 12:36, 13:04, 13:31, 13:59) instead of "within a few
minutes". A new download therefore stayed invisible for up to half an hour while a library scan
ran. The issue guessed that a file-scan batch takes that long on production.

# Possible reason
Measured read-only on production (192.0.2.27) on 2026-09-30, 0.85.2, during the library scan
that started at 07:47:22:

- `docker logs lms`: passes ended at 07:49:06, 07:51:51, 07:54:36, 07:59:03, 08:01:58 and
  08:04:53 -- every 2 min 45 s, which is the two-minute gap plus a pass of about 45 s. The next
  ended at 08:37:55, the one after that had not come by 09:00, although the tagger announced a
  folder about once a minute throughout ("requested a scan").
- So the walk (`ScanStepScanFiles`) was not the problem: it checks after every 10-file job and
  its passes came on time. The 33-minute holes are elsewhere.
- `/proc/<tid>` of the scanner thread: 100 % CPU since about 08:05, half of it system time,
  about 700,000 `pread` calls per second (2.9 GB/s of 4 KB SQLite page reads), no music file
  open, the four scan worker threads idle.
- The WAL frames written in that window were almost all `image_stem_idx`,
  `image_directory_stem_idx`, `image_path_idx`, `image` and `artwork` pages: rows were being
  deleted from `image`. `SELECT count(*) FROM image` dropped by 300 per minute, 5 rows a second.
- The 300 rows deleted in one minute were all `/mnt/music/artists/<n>/spotify-<hash>.jpg` -- the
  artist portraits music-manager inserts into lms.db itself (`routers/artist_images.py`). LMS
  sees `/music`, not `/mnt/music`, so `ScanStepCheckForRemovedFiles` removes every one of them as
  "out of media directory" on every library scan. They sit together at the top of the id range
  (about 20,000 rows), which is why the removal is one long block.
- 0.2 s a row: deleting an image cascades to its `artwork` row, and that sets
  `preferred_artwork_id` to NULL in `track`, `release`, `medium`, `artist` (and the podcast
  tables). None of those columns has an index, so each deletion scans `track` (342,933 rows)
  twice and the other tables once.

**Why that stops the passes.** `ScanStepCheckForRemovedFiles` does check for priority work after
every 200-row job it queues. But when a pass is due it first calls `queue.finish()`, which waits
for every job in flight (up to 50 jobs of 200 rows) and hands them to the done-callback -- and the
callback deleted the rows the jobs had found, all of them, before returning. With 10,000 rows in
flight, all missing, that is 10,000 × 0.2 s = 33 minutes before the pass can start. The 27-minute
spacing on 2026-09-28 is the same thing.

The DB-only steps after the walk (artist reconciliation, image/lyrics association, orphan removal,
cluster stats) are not the cause: an idle scoped scan runs every one of them library-wide and takes
48-56 s in total on production (07:41:55-07:42:43, and four more like it that morning).

# solution
LMS (`services/music-management-server/src/libs/services/scanner/impl/`):

- `ScanStepCheckForRemovedFiles`: the done-callback now only collects the ids to remove. The
  removal runs in the step's own loop through the new `removeInWriteBatches`
  (`steps/BatchedRemoval.hpp`), one write transaction of 50 rows at a time, and after every
  committed batch -- with no transaction open -- a due priority pass is let through
  (`queue.finish()`, now cheap because it only collects, then `runPriorityWork()`). The check after
  every queued job stays. So the longest a due pass waits here is one write batch (50 rows, about
  10 s at production's 0.2 s a row) plus the file checks in flight, instead of the whole removal.
  Every row is still removed exactly once, `deletions` counts the same, and an abort still stops
  the in-walk removal and removes what was collected at the end, as before. A row the pass
  already removed is deleted a second time, which is a no-op.
- The interval is a write batch rather than a timer: the question "is a pass due?" is a mutex and
  a clock read, so asking it after every batch costs nothing, and the existing debounce (5 s quiet,
  60 s cap) and the two-minute gap after a pass already decide how often a pass actually runs. The
  worst case for a download is now the gap, plus one batch, plus the pass itself: about 3-4 minutes.
- A pass reads at most 50 folders (`maxFoldersPerPriorityPass`, `ScanRequestCollector::take(n)`,
  `PriorityFolderQueue::takeDue(..., maxCount)`); the rest stay queued and still due, and go in the
  next pass after the gap. Together with the gap that bounds how much of the library scan passes can
  take, however many folders are announced.
- `ScanStepScanFiles` is unchanged: it already checks after every 10-file job, and the drain before
  a pass is at most 50 jobs of 10 files, written in the 250 ms / 10-file transactions of bug 134.
- No yield point inside the DB-only steps, for the reason measured above; revisit if one of them
  shows up as a gap between `Priority scan` lines.

Not fixed here, filed separately: the artist-portrait rows music-manager writes under
`/mnt/music/artists` are removed on every library scan and, judging by the `image` id counter
(4.7 million for 512,000 rows), written again afterwards; and none of the `preferred_artwork_id`
columns has an index. Either fix would make this removal take seconds instead of an hour.

Tests (`test-scanner`): `BatchedRemoval.aFolderAnnouncedDuringALongRemovalIsReadWithinOneWriteBatch`
(20,000 rows at 0.2 s each, a folder announced at t=1 s is read by t=130 s, every row removed once,
in order), `idsAddedBetweenBatchesAreRemovedInTheSameCall`, `fullBatchesOnlyLeavesTheRemainder`,
`nothingPendingMeansNoWriteTransaction`; `ScanStepSequence.aPriorityPassReadsAtMostItsShareOfFolders`;
`PriorityFolderQueue.aBoundedTakeLeavesTheRestForTheNextPass`;
`ScanRequestCollector.aBoundedTakeLeavesTheRestDue`. Design: `docs/designs/lms-scan-trigger/`.

To verify after deploy: during a library-wide scan, `docker logs lms` shows no gap longer than
about four minutes between `Priority scan of N announced folder(s) complete` lines while folders
are being announced, including while `SELECT count(*) FROM image` is dropping.
