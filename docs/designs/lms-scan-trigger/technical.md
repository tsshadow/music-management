# LMS scan trigger — Technical Design

Status: implemented with bug report 120 (GitLab issue #93). See the
[functional design](functional.md) for the behaviour.

## Data Model

No schema change.

## API Contract

`GET /rest/startScan.view` (Subsonic, LMS) keeps its request and response shape. What changes is
when it answers and what a plain request does:

- Plain library-wide request (no `path`, no `fullScan`/`forceOptimize`/`compact`):
  `ScannerService::requestImmediateScan` asks `decideImmediateScan()`
  (`scanner/impl/ImmediateScanPolicy.cpp`):
  - a library-wide scan runs, or is paused behind a scoped one: **Absorb**, return at once;
  - a scoped scan runs: **QueueAfterCurrent**, `_libraryScanQueued` is set and the library-wide
    scan is scheduled when the scoped one completes;
  - nothing runs: **Start** (the old `abortScan()` + schedule path; nothing to wait for).
- Any other request keeps the old behaviour (abort and start over), including the wait in
  `abortScan()` on the HTTP thread; it is a rare admin action.

The decision reads `_scanRunning`, `_scanRunningScoped` and `_libraryScanPaused` (a mirror of
`_pausedScan`), all guarded by `_statusMutex`, so the web thread never touches the scanner
thread's own state.

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

Not a breaking change: no consumer reads anything but the HTTP status.

## Cross-App Impact

- `services/tagger/tagger.py`: `Tagger.run()` no longer calls `lms_scan_trigger.trigger()`.
- `services/music_manager/routers/tagger.py`: `tag_single` calls `notify([parent])`.
- `services/music_manager/routers/scanner.py`: unchanged, still one `trigger()` per hourly run;
  LMS now absorbs it when a library scan is already running.

## Technical Acceptance Criteria

- `test-scanner`: `ImmediateScanPolicy.*`.
- `test-auth`: `AuthTokenReadPath.aValidTokenDoesNotQueueBehindAWriterForBookkeeping`,
  `aValidTokenIsStampedWhenTheLockIsFree`.
- `test-core`: `RecursiveSharedMutex.TryLockFailsWhileAnotherThreadHoldsItAndNests`.
- Python: `LmsScanTriggerTest` (retry, carry, resend, one WARNING per outage), `TaggerTest`,
  `test_scanner_tagger_routers.LmsTriggerTest`.

## Related Docs

- [Bug report 120](../../bug-reports/120-lms-scan-trigger-read-timeouts.md)
- [Tagger rescan paths](../tagger/rescan-paths.md)
