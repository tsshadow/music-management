# LMS scan trigger — Technical Design

Status: implemented with bug report 120 (GitLab issue #93); priority passes with bug report 126
(GitLab issue #125); bounded waits inside the removed-files check with bug report 136 (GitLab issue
#132). See the [functional design](functional.md) for the behaviour.

## Data Model

No schema change.

## API Contract

`GET /rest/startScan.view` (Subsonic, LMS) keeps its request and response shape. What changes is
when it answers and what a plain request does:

- Plain library-wide request (no `path`, no `fullScan`/`forceOptimize`/`compact`):
  `ScannerService::requestImmediateScan` asks `decideImmediateScan()`
  (`scanner/impl/ImmediateScanPolicy.cpp`):
  - a library-wide scan runs (also while it is in a priority pass, see below): **Absorb**,
    return at once;
  - a scoped scan runs: **QueueAfterCurrent**, `_libraryScanQueued` is set and the library-wide
    scan is scheduled when the scoped one completes;
  - nothing runs: **Start** (the old `abortScan()` + schedule path; nothing to wait for).
- Any other request keeps the old behaviour (abort and start over), including the wait in
  `abortScan()` on the HTTP thread; it is a rare admin action.

The decision reads `_scanRunning` and `_scanRunningScoped`, guarded by `_statusMutex`, so the web
thread never touches the scanner thread's own state.

### Scoped requests during a library-wide scan (bug report 126)

`GET /rest/startScan.view?path=...` calls `requestScopedScan`, which adds the folders to
`PriorityFolderQueue` (`scanner/impl/PriorityFolderQueue.cpp`) **on the web thread**: a mutex around
the existing `ScanRequestCollector` (5 s quiet period, 60 s cap, a `std::set` so duplicates merge).
It then posts `armScanRequestTimer()` to the io thread for the idle case.

Why not the io thread, as before: `WIOService` has one thread and `scan()` runs on it. The earlier
design paused the running scan from the debounce timer's handler, which could therefore only run
after the scan it was meant to pause had ended. That pause/resume machinery (`InterruptReason`,
`PausedScan`, `libraryScanPaused`) is removed.

Two ways the folders leave the queue:

- **Idle** -- the timer fires on the io thread, `runPendingScopedScan()` takes everything and runs a
  scoped `scan()`, as before.
- **During a library-wide scan** -- `ScannerService` implements `IPriorityScanYield`
  (`impl/steps/IPriorityScanYield.hpp`), handed to every step through
  `ScanStepBase::InitParams::priorityYield`. `isPriorityWorkDue()` is true when a library-wide scan
  runs (`_libraryScanContext`), no pass runs, no abort is pending, and
  `PriorityFolderQueue::isDue(now, DuringLibraryScan)`: the collector's deadline has passed **and**
  at least `minGapDuringLibraryScan` (2 min) has passed since the previous pass ended.
  `runPriorityWork()` calls `runPriorityPass()` (`ScanStepSequence.cpp`): take the due folders --
  at most `maxFoldersPerPriorityPass` (50); the rest stay queued and due, for the next pass after
  the gap -- build a scoped `ScanContext`, `runScanSteps(_scanSteps, ...)` over it, put the folders
  back if `_abortScan` went up.

Where a step may yield -- the contract in `IPriorityScanYield`: nothing of the step's own may be
queued on the job scheduler (`JobQueue` asserts it owns the scheduler: `getJobsDoneCount() == 0` on
construction) and no transaction may be open.

- `ScanStepScanFiles`: after each `queue.push()` of a 10-file job, if due: `queue.finish()` (drains
  and writes the in-flight results), flush the remaining operations, run the pass, keep walking from
  the current file. The walk's position is simply the stack frame of `exploreFilesRecursive`, so
  nothing needs a cursor.
- `ScanStepCheckForRemovedFiles`: after each batch push, same pattern; the keyset walk resumes from
  `lastCheckedId`. The done-callback only collects the ids to remove; the removal runs in the
  step's loop through `removeInWriteBatches` (`steps/BatchedRemoval.hpp`), 50 rows per write
  transaction, and asks again after every committed batch (bug report 136). Before that the
  callback removed everything the finished jobs had found, so the `queue.finish()` in front of a
  pass could mean 10,000 removals at 0.2 s each on production -- half an hour between passes.
- Between steps: `runScanSteps(..., betweenSteps)` calls it after each completed step except the
  last. The DB-only steps (artist reconciliation, image/lyrics association, orphan removal, cluster
  stats, duplicates) yield only there.

Re-entrancy: a pass re-enters the same step objects the library scan is inside (`_scanSteps`).
Steps keep all per-run state on the stack or in the `ScanContext`; their members are const or
references. `_inPriorityPass` makes `isPriorityWorkDue()` false inside a pass, so passes never nest.
`refreshScanSettings()` (which rebuilds `_scanSteps`) is only called at the start of `scan()`, never
from a pass.

Single writer: the pass runs on the scanner thread and takes the SQLite write lock batch by batch
(10 files per write transaction in `ScanStepScanFiles`), like any scan. Auth's
`tryCreateWriteTransaction()` bookkeeping from bug 120 is unaffected.

Status and summary:

- `IScannerService::Status` gains `pendingPriorityFolders` and `priorityPassInProgress`;
  `getScanStatus` returns them as `pendingFolders` (number) and `priorityScan` (bool), always
  present. `step`, `stepIndex`, `count`, `totalCount` keep describing the library-wide scan:
  `notifyInProgress` ignores progress while `_inPriorityPass`.
- `ScanStats` gains `priorityPasses` and `priorityFolders`, counted into the library-wide scan's
  stats; its summary line appends `priority passes = N (M folders)` when N > 0.
- Each pass logs `Priority scan of N announced folder(s) complete|aborted. Changes = ...` with the
  same fields as the scan summary. Its changes and errors are not added to the library-wide stats
  (the walk meets those files again and counts them as skips), and a pass emits no `scanStarted` /
  `scanComplete` event and does not touch `lastScan` -- as for any scoped scan.
- Bug 121's scoped error policy applies unchanged: the pass context is scoped, so
  `decidePlayListErrorReporting` returns `SkipOutOfScope` for playlists outside its folders.

How often a step asks: at every safe point -- after each queued job and after each write batch.
Asking is a mutex and a clock read; how often a pass actually runs is decided by the collector's
debounce and the two-minute gap, not by the step. So the longest a due pass waits is the work
between two safe points: one drain of the job queue (at most 50 jobs: 500 files to write in
`ScanStepScanFiles`, 10,000 file checks and no writes in `ScanStepCheckForRemovedFiles`) plus one
write batch. A wall-clock interval inside the step would add a second timer without shortening that.

Not done: a yield point inside the DB-only steps. Measured on production (bug report 136), an idle
scoped scan runs every one of them library-wide in 48-56 s, so between-steps is enough. If one of
them ever shows up as a gap between `Priority scan` lines, adding one is the same pattern as in
`ScanStepCheckForRemovedFiles`.

### The DB-only steps of a scoped scan (bug report 141)

Those 48-56 s were the price of every scoped scan, priority passes included: the association
steps and the cluster counts recomputed the whole library after any change. A scoped scan now
computes a `ScanScope` (`scanner/impl/steps/ScanScope.*`) once, by the first step that asks for it
(`ScanStepBase::getScanScope`, cached in `ScanContext`), after the walk and the removed-files
check:

| step | scoped scan walks |
|---|---|
| AssociatePlayListTracks | playlist files under the folders |
| AssociateReleaseImages | releases of the tracks under the folders |
| AssociateArtistImages | artists linked to the scope's tracks (any link type) |
| AssociateMediumImages | mediums of the scope's tracks |
| AssociateTrackImages | tracks under the folders + the other tracks of their releases |
| ComputeClusterStats | clusters of the scope's tracks + `Cluster::findIdsWithOutdatedTrackCount` |

The ids are handed to the existing jobs as runs of consecutive ids (`toConsecutiveIdRanges`),
so a job reads `BETWEEN first AND last` as before and never touches an id outside the scope.
The scope is library-wide (null) when:
- the scan is not scoped;
- more than `maxScopedTrackCount` (20,000) tracks are involved;
- for the artist and playlist steps, their setting changed since the last scan;
- for the cluster step, the previous scan could not write a batch.

Left for the next library-wide scan:
- an entity outside the folders whose artwork image the scan deleted (shown without artwork);
- a release elsewhere that would match an MBID-named image in a scanned folder;
- a playlist elsewhere that lists a file in a scanned folder.

ArtistReconciliation, UpdateLibraryFields, AssociateExternalLyrics and RemoveOrphanedDbEntries
stay library-wide: together they took under a second on production.

Authentication (`AuthTokenService::processAuthToken`, `AuthServiceBase::onUserAuthenticated`)
takes the process-wide write lock only when there is something to write. A use-limited token
still waits for it; the `last_used` and `last_login` stamps use the new
`Session::tryCreateWriteTransaction()` (built on `RecursiveSharedMutex::try_lock`) and are skipped
when a writer -- in practice a scanner batch -- holds the lock.

Client (`services/common/Helpers/LmsScanTrigger.py`): timeout `(5, 30)`; one retry after 2 s on
`requests.Timeout`/`ConnectionError`; failed notify paths are carried (max 1000, oldest dropped)
into the next notify; a failed trigger sets `_trigger_pending`, re-sent after the next successful
notify or by the next `trigger()`. WARNING on the first failure of an outage, INFO afterwards,
INFO on recovery.

Not a breaking change: no consumer reads anything but the HTTP status. The two `getScanStatus`
attributes added for bug report 126 are additive; the web Scanner tab and the contract/BDD tests
read only `scanning`, `lastScan` and `scanSettings`.

## Cross-App Impact

- `services/tagger/tagger.py`: `Tagger.run()` no longer calls `lms_scan_trigger.trigger()`.
- `services/music_manager/routers/tagger.py`: `tag_single` calls `notify([parent])`.
- `services/music_manager/routers/scanner.py`: unchanged, still one `trigger()` per hourly run;
  LMS now absorbs it when a library scan is already running.

## Technical Acceptance Criteria

- `test-scanner`: `ScanScope.*` and `ScanScopeIdRanges.*` (bug report 141: the scope, the cap,
  scoped track artwork leaves the rest alone, scoped cluster stats fix the genre a retag left),
  `ImmediateScanPolicy.*`, `PriorityFolderQueue.*`, `ScanStepSequence.*`,
  `BatchedRemoval.*` (a folder announced during a 20,000-row removal is read within one write
  batch of being due; every row is removed once)
  (including `aFolderAnnouncedDuringALibraryScanIsReadBeforeItFinishes`: read mid-walk, the walk
  runs once and is never interrupted, a folder announced twice is read once).
- `test-auth`: `AuthTokenReadPath.aValidTokenDoesNotQueueBehindAWriterForBookkeeping`,
  `aValidTokenIsStampedWhenTheLockIsFree`.
- `test-core`: `RecursiveSharedMutex.TryLockFailsWhileAnotherThreadHoldsItAndNests`.
- Python: `LmsScanTriggerTest` (retry, carry, resend, one WARNING per outage), `TaggerTest`,
  `test_scanner_tagger_routers.LmsTriggerTest`.

## Related Docs

- [Bug report 120](../../bug-reports/120-lms-scan-trigger-read-timeouts.md)
- [Bug report 126](../../bug-reports/126-scoped-scans-wait-for-full-scan.md)
- [Bug report 141](../../bug-reports/141-scoped-scans-recompute-the-whole-library.md) (scoped DB-only steps)
- [LMS scan errors design](../lms-scan-errors/technical.md) (scoped error policy, bug 121)
- [Tagger rescan paths](../tagger/rescan-paths.md)
