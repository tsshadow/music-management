# LMS scanner write pacing — Technical Design

Implements [functional.md](functional.md). Bug reports 134 (issue #133) and 135 (issue #135).

## Data Model

No schema change. One per-connection pragma is added in `Db.cpp`:
`PRAGMA journal_size_limit=67108864` (64 MiB). It changes only how large the WAL file is left
after a reset. Checkpointing (`wal_autocheckpoint`, default 1000 pages) is unchanged.

## API Contract

None. No endpoint, request or response changes.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| — | — | — | — |

## Cross-App Impact

None. music-manager's lms.db writers (`lms_writes.PendingWrites`, see
[lms-sync-busy-server](../lms-sync-busy-server/technical.md)) are unchanged. They benefit because
the scanner now leaves them gaps inside their 10 s busy timeout.

## Design

### `db::WritePacer` (`database/WritePacer.hpp`)

- Belongs to one `db::Session`, so to one thread (`Session::setWritePacer`). `WriteTransaction`
  calls `onWriteBegin()` before it takes the in-process write mutex, and `onWriteEnd()` after it
  has released it. It does this through a `detail::WritePacingScope` member declared before the
  lock.
- A *stretch* starts at a write transaction and ends at a gap of at least `pause` between one
  commit and the next begin. When the next outermost write transaction begins a stretch that is
  `maxStretch` or older, the pacer first sleeps for `pause`.
- Nested write transactions are counted but never paced. `tryCreateWriteTransaction` (which never
  waits) passes no pacer.
- The scanner sets `maxStretch = 500 ms` and `pause = 120 ms` on its own thread's session in
  `ScannerService::scan`. 120 ms is longer than the 100 ms maximum sleep of SQLite's default busy
  handler, so a connection that is waiting always makes at least one attempt inside the gap. The
  in-process write mutex hands over within a millisecond. The throughput cost is at most
  120 / 620 ≈ 19 % on a write-bound stretch, and less in practice: file parsing on the job
  scheduler goes on during the pause.

### Time-bounded batches in `ScanStepScanFiles`

`processFileScanOperations` still takes up to 10 file results per write transaction. It now also
commits as soon as a transaction has run for 250 ms, so one transaction full of heavy files cannot
hold the lock for seconds.

### `db::writeGuarded` (`database/GuardedWrite.hpp`)

This is the bug-132 pattern, lifted into one template. An outer try covers the whole transaction
scope, which catches both a BEGIN IMMEDIATE timeout and a failed commit. An inner try inside the
scope makes an explicit `flush()`. Both catches call `discardUnflushed()`. `onFailure` is called
at most once, and the function returns false. Only `Wt::Dbo::Exception` is caught.

It is used by:
- the podcast steps: CheckForMissingFiles, RemovePodcasts and RemoveEpisodes end the refresh with
  `onAbort()`, which resets `_refreshInProgress` through `onRefreshDone`. RefreshPodcasts,
  DownloadPodcastArtworks, DownloadEpisodeArtworks and DownloadEpisodes skip the item and delete
  the file they downloaded for it. `PodcastService::runStep` also catches `Wt::Dbo::Exception`
  from a step's synchronous part and ends the refresh.
- ListenBrainz: `ListensSynchronizer::saveListen`, and `FeedbacksSynchronizer::enqueFeedback`,
  `onFeedbackSent` and `tryImportFeedback`. `enqueFeedback` now sends its HTTP request after the
  commit. `onFeedbackSent` changes the cached feedback count only after a committed write.
  `ListensSynchronizer::enquePendingListens`, which only reads, now opens a read transaction.

## Technical Acceptance Criteria

1. `WritePacer` unit tests with an injected clock: no pause under `maxStretch`, one pause at
   `maxStretch`, repeated pauses on continuous writing, no pause when the gaps are at least
   `pause`, and nested transactions not paced.
2. `WritePacer.anotherConnectionGetsTheLockWhileAPacedBulkWriterRuns`: a raw SQLite connection
   (busy_timeout 3 s) gets `BEGIN IMMEDIATE` within 1.5 s while a paced writer runs back-to-back
   5 ms transactions.
3. `WritePacer.anotherThreadGetsTheWriteMutexWhileAPacedBulkWriterRuns`: the same for an
   in-process `createWriteTransaction`.
4. `GuardedWrite.*`: a successful write commits. A refused statement returns false without
   throwing, calls `onFailure` once, and the discarded change is not flushed by the next write
   transaction.

## Measurement

Local measurement, with the test harness in `database/test/WritePacer.cpp` and a temporary
variant: a foreign connection with busy_timeout 10 s (music-manager's value) tried
`BEGIN IMMEDIATE` 300 ms into a bulk writer that runs back-to-back transactions of 2, 10 or 30 ms.

| Transaction length | Unpaced | Paced |
|---|---|---|
| 2 ms | SQLITE_BUSY after 10,072 ms | lock after 231 ms |
| 10 ms | SQLITE_BUSY after 10,061 ms | lock after 229 ms |
| 30 ms | SQLITE_BUSY after 10,048 ms | lock after 3 ms |

## Related Docs

- [docs/bug-reports/134-lms-scanner-holds-the-write-lock.md](../../bug-reports/134-lms-scanner-holds-the-write-lock.md)
- [docs/bug-reports/135-lms-background-writes-abort-on-a-refused-commit.md](../../bug-reports/135-lms-background-writes-abort-on-a-refused-commit.md)
- [docs/bug-reports/132-lms-crashes-on-locked-cluster-count-update.md](../../bug-reports/132-lms-crashes-on-locked-cluster-count-update.md)
- [docs/designs/lms-sync-busy-server/technical.md](../lms-sync-busy-server/technical.md)
