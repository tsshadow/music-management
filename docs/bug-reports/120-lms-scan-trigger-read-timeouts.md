# LMS Scan Trigger Read Timeouts

# status: fixed

# reported problem
GitLab issue #93. The production events table for 2026-09-26/27 held two recurring WARNINGs, each
of them a push on the alerts topic:

- `root: Failed to trigger LMS scan on http://lms:5082: HTTPConnectionPool(host='lms', port=5082): Read timed out`
  -- music-manager, about 50 per 12 hours;
- `root: Failed to notify LMS on http://lms:5082: ... Read timed out` -- downloader, about 43 per 12
  hours.

The client timeout was 10 seconds for both.

# Possible reason
Measured read-only on 2026-09-27 (events table, `docker logs lms` on 192.0.2.27).

**Who sends what.** `LmsScanTrigger.trigger()` sends `startScan.view` without a `path`: a
library-wide scan. Its music-manager caller that fires every few minutes is the tagger loop:
`Tagger.run()` ended every round with `lms_scan_trigger.trigger()`, and the loop sleeps 300 s after
a round, so the trigger came every ~5.1 minutes -- 23:34, 23:39, 23:44, 23:49, ... on the events
table, successes and failures alternating. `notify(paths)` sends `startScan.view` with `path=`
parameters (a scoped scan); the downloader's failures are those.

**What LMS does with a library-wide request.** `handleStartScan` calls
`IScannerService::requestImmediateScan`, which calls `abortScan()` on the HTTP (Wt) thread. That
sets the abort flag and calls `_ioService.stop()`, which joins the scanner's IO thread: the request
does not answer until the running scan has unwound to a batch boundary and the handler after it
has run. After the 01:36 deploy the log shows exactly that -- a trigger entering the handler at
01:46:59.435, the library scan aborting at 01:46:59.496, the debounced scoped scan behind it
starting and aborting at 01:47:04.505, and music-manager logging "Triggered" at 01:47:04.560. Five
seconds that time; whenever the running step takes longer to reach a boundary, more than ten.

**Why that is worse than a timeout.** The same abort throws the running scan away. A library-wide
scan here takes the better part of an hour (`ScannerOptions.hpp`); the tagger asked for a new one
every five minutes. The one started at 01:41:53 had reached 152,654 unchanged files when the next
trigger aborted it at 01:46:59; its successor reached 650,194 file checks and was aborted at
01:52:07. No library-wide scan -- neither the requested ones nor the periodic 01:00 scan -- could
complete while the tagger loop ran. Anything nobody announced per folder, and every removed file,
waited for a scan that never finished.

**Why a scoped notify could time out too.** `requestScopedScan` only posts to the IO thread, so the
handler never waits on the scan. The wait was before it, in authentication: `processAuthToken`
resolved the API key under a read transaction, then took a write transaction unconditionally --
the process-wide exclusive lock that the scanner holds for each write batch -- and
`onUserAuthenticated` took it again for `last_login`. The subsonic auth cache hides this for five
minutes per client; the tagger's ~5.1-minute cadence meant its trigger was never cached, and the
downloader's key expired now and then between bursts. At 01:41:48.311 and .339 two requests logged
"requested a scan" in the same instant the scanner released its batch ("Scan aborted" at
01:41:48.422), which is what a request parked on that lock looks like.

**Nothing was retried.** A failed notify was logged and dropped: its folder showed up only after a
library-wide scan, which, as above, never completed.

# solution
LMS (`services/music-management-server`):

- `ImmediateScanPolicy` (`scanner/impl/ImmediateScanPolicy.cpp`) decides what a library-wide request
  does. A plain one joins a running or paused library-wide scan (logged at INFO, returns at once),
  is queued behind a running scoped scan (runs when that completes), and only starts -- with the
  old abort -- when nothing runs. `fullScan`, `forceOptimize` and `compact` requests still start
  over, as an admin would expect. The state it reads (`_scanRunning`, `_scanRunningScoped`,
  `_libraryScanPaused`, `_libraryScanQueued`) lives under `_statusMutex`, so the web thread never
  touches the scanner thread's own fields.
- `processAuthToken` takes the write lock only when there is something to write. An expired token
  and a use-limited token still wait for it; a `last_used` stamp alone goes through the new
  `Session::tryCreateWriteTransaction()` (`RecursiveSharedMutex::try_lock`) and is skipped while a
  writer holds the lock. `onUserAuthenticated` does the same for `last_login`.

Client (`services/common/Helpers/LmsScanTrigger.py`):

- Timeout `(5, 30)` instead of 10; one retry after 2 s on a timeout or refused connection.
- A notify that still fails keeps its paths (up to 1000, oldest dropped) and sends them with the
  next notify. A trigger that still fails is re-sent after the next notify that gets through, or by
  the next `trigger()` call. If no request follows at all, LMS's periodic scan -- which can now
  complete -- is the backstop.
- The first failure of an outage is a WARNING; further failures are INFO; the first success
  afterwards logs "LMS on ... answers scan requests again" at INFO.

Callers: `Tagger.run()` no longer sends a library-wide trigger (every folder a round writes is
already notified), and `tag_single` (rerun-parse, curation "apply now") notifies the file's folder
instead of triggering a library-wide scan per file. The hourly music-manager scanner run still sends
one trigger, which LMS now absorbs if a library scan is already running.

Tests: `test-scanner` `ImmediateScanPolicy.*`; `test-auth`
`AuthTokenReadPath.aValidTokenDoesNotQueueBehindAWriterForBookkeeping` and
`aValidTokenIsStampedWhenTheLockIsFree`; `test-core`
`RecursiveSharedMutex.TryLockFailsWhileAnotherThreadHoldsItAndNests`; Python `LmsScanTriggerTest`,
`TaggerTest.test_a_run_does_not_ask_lms_for_a_library_wide_scan`,
`LmsTriggerTest.test_tagging_a_single_file_tells_lms_its_folder`. Design:
`docs/designs/lms-scan-trigger/`.

To verify after deploy: the two WARNINGs stop, and `docker logs lms` shows "Scan complete" for a
library-wide scan (not only "Scan aborted").
