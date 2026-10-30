# Scoped Scans Wait For The Full Scan

# status: fixed

# reported problem
GitLab issue #125. Since MR !1079 (bug report 120) a plain library-wide scan request joins a running
library-wide scan instead of aborting it, and the library-wide scan completes again. But while one
runs, no scoped scan runs: the folders the downloader and tagger announce (`LmsScanTrigger.notify`,
`startScan.view?path=...`) wait until the whole library has been walked, and a new download does not
appear in LMS for hours.

# Possible reason
Measured read-only on production (192.0.2.27) on 2026-09-27, `docker logs lms`:

- Up to 15:38 announcements were read promptly: scoped scans started at 15:32:57, 15:34:12 and
  15:36:52, each finished in about 70 s ("Scan complete ... Not changed = 1710").
- 15:38:25.908 "Scheduling next scan right now" / "New scan started!": the library-wide scan.
- From 15:39:01 to 17:23 LMS logged "requested a scan" **225 times** -- 224 announcements plus one
  library-wide trigger at 16:55:34 ("Library scan requested while one is running: joining it", as
  bug 120 intended) -- and **"New scan started!" zero times**. The soundcloud worker logged "Notified
  LMS ... of 1 path(s)" throughout (16:59:30, 17:00:45, 17:04:00, ...).

**Why the scoped lane never ran.** The service already had a design for exactly this
(an agent plan, since removed; see `docs/designs/lms-scan-trigger/technical.md`): a scoped request should pause the
running periodic scan at its next batch boundary, run, and resume the periodic scan at the step it
was in. The pause was requested from `ScannerService::onScanRequestDue()`, the handler of the
debounce timer, and `requestScopedScan()` added its paths by `_ioService.post()`. Both run on the
scanner's `WIOService`, which has **one thread** (`_ioService.setThreadCount(1)`) -- and `scan()`
runs on that same thread, called from `_scheduleTimer`'s handler. While a scan runs, neither the
post nor the timer can execute. The pause branch (`_curState == InProgress` -> set `Pause`) was
therefore unreachable: by the time the handler ran, the scan it was meant to interrupt had ended.
The 225 posts simply queued up behind the library-wide scan.

Before bug 120 this was masked: the tagger's library-wide trigger called `abortScan()` every ~5
minutes, which stopped the io thread, and the queued scoped work ran in the gap -- at the price of
never completing a library-wide scan.

**Why making the pause work would not have been enough.** The design's own risk section: a pause
restarts the interrupted step from its beginning, and `ScanStepScanFiles` is the hour-long walk. A
tagger round that announces a folder every minute would restart that walk every minute -- bug
120's loop again, with a different trigger.

# solution
LMS (`services/music-management-server/src/libs/services/scanner/`):

- `impl/PriorityFolderQueue.{hpp,cpp}`: the announced folders now live in a mutex-guarded queue
  (the existing `ScanRequestCollector` inside it, so the 5 s quiet period / 60 s cap and the
  de-duplication stay). `requestScopedScan()` adds to it directly on the web thread; the idle timer
  still runs a scoped scan when nothing else runs.
- A library-wide scan reads the queue itself (`IPriorityScanYield`, implemented by
  `ScannerService`). At a safe point -- every batch handed to the job scheduler in
  `ScanStepScanFiles` and `ScanStepCheckForRemovedFiles`, after draining that step's in-flight jobs,
  and between steps (`runScanSteps`' new `betweenSteps`) -- it runs a **priority pass**: the ordinary
  scoped scan over the due folders (`runPriorityPass` in `ScanStepSequence.cpp`), on the same thread,
  then continues exactly where it was. Nothing is aborted or restarted; files the walk meets again
  later are unchanged and cost a skip each. No second scanner thread, no second writer: the pass
  takes the SQLite write lock batch by batch like any scan.
- Inside a library-wide scan a pass waits at least two minutes after the previous one ended, so a
  busy tagger slows the library scan by at most about a third instead of stalling it.
- The dead pause/resume machinery (`InterruptReason`, `PausedScan`, `libraryScanPaused` in
  `ImmediateScanPolicy`) is removed. A plain library-wide request during a pass still joins the
  running scan (`scoped` stays false for the pass).
- Status: `getScanStatus` gains `pendingFolders` (announced folders not read yet) and `priorityScan`
  (a pass is running); `step`/`count` keep describing the library-wide scan, whose progress the pass
  does not overwrite. The library-wide summary line gains `priority passes = N (M folders)`
  (`ScanStats::priorityPasses/priorityFolders`); each pass logs its own
  `Priority scan of N announced folder(s) complete. Changes = ...` line. A pass publishes nothing
  (`lastScan`, admin page, `scanComplete` event), like a scoped scan.
- Bug 121's scoped error policy holds unchanged: a pass is a scoped `ScanContext`, so
  `decidePlayListErrorReporting` skips out-of-scope playlists for it, and its errors are counted in
  its own stats, not in the published library-wide ones.
- An abort (admin fullScan/compact, shutdown) during a pass puts its folders back in the queue.

Tests (`test-scanner`): `PriorityFolderQueue.*` (debounce at both moments, dedupe, the gap, idle
ignores the gap, concurrent add/take); `ScanStepSequence.aFolderAnnouncedDuringALibraryScanIsReadBeforeItFinishes`
(folder announced mid-walk is read before the library scan finishes; the walk runs once, is never
interrupted, every file counted once; a folder announced twice is read once),
`aFolderAnnouncedDuringTheWalkButDueAfterItIsReadBetweenSteps`, `aPriorityPassCutShortPutsItsFoldersBack`,
`noPriorityPassWhenNothingIsDue`, `betweenStepsRunsAfterEveryCompletedStepButNotAfterTheLast`;
`ImmediateScanPolicy.aPlainRequestDuringAPriorityPassJoinsTheLibraryScan`,
`aScopedRequestIsNeverAbsorbed`. Design: `docs/designs/lms-scan-trigger/`.

To verify after deploy: during a library-wide scan, `docker logs lms` shows
`Priority scan of N announced folder(s) complete` lines within a few minutes of a download, and the
library scan still ends with `Scan complete ... priority passes = N`.
