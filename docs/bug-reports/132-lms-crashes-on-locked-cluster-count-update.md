# LMS crashes on an uncaught "database is locked" while updating cluster counts

# status: fixed

# reported problem
The `lms` container on production went down twice in 72 hours: at about 2026-09-28 18:10 UTC and
2026-09-29 04:00 UTC. Autoheal or the restart policy brought it back each time, and the restart
count went to 2. Both times `docker logs lms` (read-only) ended with:

```
terminate called after throwing an instance of 'Wt::Dbo::backend::Sqlite3Exception'
  what():  Sqlite3: update "cluster" set "version" = ?, "name" = ?, "track_count" = ?, "release_count" = ?, "cluster_type_id" = ? where "id" = ? and "version" = ?: database is locked
```

Both times it happened on the scanner thread, in a scoped scan: "Scan complete" and "Priority
scan of N announced folder(s) complete" lines came from that thread, and the downloader was
announcing a folder every few seconds.

# Possible reason
The UPDATE is `ScanStepComputeClusterStats::process`
(`services/music-management-server/src/libs/services/scanner/impl/steps/ScanStepComputeClusterStats.cpp`,
the write block at lines 84-90 before this fix). This is the second-to-last scan step, and every
scan with at least one change runs it. For each cluster (every genre, mood, festival and so on,
thousands of them), it opened its own write transaction, re-read the cluster, and set both counts
whether or not they had changed. The flush and commit ran in `WriteTransaction::~WriteTransaction`.

Three facts make that a crash:

1. **The lock wait never applies.** Wt's SQLite backend opens every transaction with a plain,
   deferred `begin transaction`. The step reads (`Cluster::find`) and then writes. SQLite returns
   `SQLITE_BUSY` for a read-to-write upgrade immediately when another connection holds the write
   lock: the busy handler runs only for a connection with no transaction open. So LMS's
   `PRAGMA busy_timeout=15000` did nothing here. The same mechanism once made rating requests
   fail during music-manager's hourly sync (MR !741).
2. **Another connection does hold the lock.** music-manager writes `lms.db` directly. The events
   table puts its hourly passes at both crash moments: `track_form_sync` ran at 18:10:57 and
   `song_version_sync` wrote 69 rows at 18:11:19, and on the second day at 04:00:45 and 04:01:09
   (46 rows). Since MR !1134 those passes take the lock up front with `BEGIN IMMEDIATE` and hold
   it for up to 100 UPDATEs. The step made one trip for the lock per cluster, thousands per scan,
   and with scoped scans arriving every minute one of those trips was bound to land inside such a
   batch. LMS's own scanner cannot be the other holder, because inside the process every writer
   is serialised by the database write mutex.
3. **Nothing catches the exception.** The scanner runs on a `Wt::WIOService` thread, and
   `WIOService::run()` has no try/catch. The exception came out of the commit in the destructor.
   The destructor is implicitly `noexcept(false)`, because `Wt::Dbo::Transaction`'s destructor is,
   so the exception passed through `process()`, `runScanSteps`, `ScannerService::scan` and the
   posted handler, and ended the thread in `std::terminate`.

# solution
- **Write transactions take the lock up front.** `db::WriteTransaction` now opens its SQLite
  transaction in its constructor, and the connection (`Db.cpp`, `Connection::startTransaction`)
  starts it with `BEGIN IMMEDIATE` instead of Wt's deferred BEGIN. Taking the write lock while no
  transaction is open is the case `busy_timeout` covers, so a write transaction now waits up to 15
  s for music-manager instead of failing on its first write. Read transactions keep the deferred
  BEGIN: under WAL they do not queue behind a writer. A write transaction nested inside one that
  is already open reuses it, as before. This change is in the database layer, so it covers every
  write transaction in LMS, including the HTTP request paths (ratings, scrobbles), not only this step.
- **The step writes only what changed, in batches.** Counts are computed in a read transaction per
  batch of 100 clusters. Only the clusters whose counts moved are written, in one write
  transaction per batch. A typical scoped scan now writes a handful of rows in one transaction,
  instead of thousands of transactions.
- **A refused write no longer kills the process.** The step flushes explicitly inside a try that
  sits inside the transaction scope. On a `Wt::Dbo::Exception` it calls
  `Session::discardUnflushed()`, because a failed flush leaves the objects dirty in the thread's
  session and the next write transaction would flush them again. It then logs a WARNING and ends
  the step. A flag makes the next scan run the step even when that scan has no changes of its own.
- **The scanner thread has a safety net.** `ScannerService::runScanStepsGuarded` catches a
  `Wt::Dbo::Exception` from any step, logs a WARNING, and handles the scan as stopped rather than
  complete: it does not save the settings or publish the stats. A scoped scan puts its folders
  back in the priority queue. A library-wide scan is retried after 5 minutes. A priority pass
  inside a library scan puts its folders back (`runPriorityPass`) and clears its in-pass flags
  before the exception moves on, so later passes still run.

Tests: `src/libs/database/test/WriteTransactionLock.cpp` holds the write lock on a second, raw
SQLite connection, as music-manager does. It checks three things: a read-then-write transaction
waits for the lock and succeeds (under the old deferred BEGIN this is the exact
`database is locked` failure), a read transaction is not held up, and a nested write transaction
still works. `ScanStepSequence.aPriorityPassEndedByAnExceptionPutsItsFoldersBack` covers the pass.

**Other background write paths of the same shape.** A survey found that none of the following
catch a `Wt::Dbo::Exception` around the commit. They run on the "Misc" `IOContextRunner`, which
does catch, but then logs FATAL and calls `std::abort()`:
- Podcast steps: `CheckForMissingFilesStep.cpp:105,135`, `RemovePodcastsStep.cpp:87`,
  `RefreshPodcastsStep.cpp:55`, `RemoveEpisodesStep.cpp:97`, `DownloadPodcastArtworksStep.cpp:42`,
  `DownloadEpisodeArtworksStep.cpp:43` and `DownloadEpisodesStep.cpp:47`. An exception there
  would also leave `_refreshInProgress` set.
- ListenBrainz scrobbling: `ListensSynchronizer.cpp:310,347`.
- ListenBrainz feedback: `FeedbacksSynchronizer.cpp:82,158,458`.

The `BEGIN IMMEDIATE` change lowers the risk on all of them, since they now wait for the lock
instead of failing on an upgrade. They are still unguarded against a lock held longer than 15 s.
Neither feature is known to be in use on production. That work is filed as GitLab issue #135.
The music-manager `ListenOutboxRelay` and `UserSynchronizer` paths already catch at the commit.
