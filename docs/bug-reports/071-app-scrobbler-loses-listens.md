# The App's Scrobbler Loses Listens, And LMS's Relay Drops Some Of The Rest

# status: fixed — the app keeps every qualifying listen on disk until the server has it; LMS's relay to MuMa is still best-effort (open-work)

# reported problem

On 2026-09-25 LMS recorded four listens for user "Teun" (LMS `listen` 37774, 37780, 37781, 37787
at 05:26:10, 05:36:36, 05:39:53 and 06:08:56 UTC; tracks 9596523, 9648936, 9648937, 9374019).
MuMa has one of them: `scrobble_listens` track 9374019 at 06:09:51, source `mobile`. Nothing for
the other three in `scrobble_listens` or `scrobble_unmatched_listens` between 05:20 and 06:15. The
LMS reconcile dry run finds 1,453 LMS-only listens overall. the open-work list already listed "the
app's own scrobbler loses listens the web player used to catch" since 0.72.1 (bug report 035),
when the web player inside the app stopped scrobbling and `service/Scrobbler.kt` became the only
path.

# Possible reason

There are two places a listen can be lost, and this morning's evidence points at the second.

## 1. LMS to MuMa: the three missing listens reached LMS

An LMS `listen` row with `backend = 0` (Internal) is written by the same call that relays the listen
to MuMa, so a row in LMS with none in MuMa means the app delivered it and the relay lost it:

- `/rest/scrobble` without `time` calls `listenFinished`
  (`services/music-management-server/src/libs/subsonic/impl/endpoints/MediaAnnotation.cpp:228-230`).
- `ScrobblingService::listenFinished` calls the user's backend (Internal writes the LMS row) and
  then `_mumaScrobbler->listenFinished`
  (`src/libs/services/scrobbling/impl/ScrobblingService.cpp:91-98`).
- `MusicManagementBackend::sendScrobble` posts to `/api/scrobble/event` on a `SendQueue` with no
  failure callback (`src/libs/services/scrobbling/impl/musicmanagement/MusicManagementBackend.cpp:124-132`).
- That queue gives up after two retries of a transport error, back to back, 5 s timeout each
  (`src/libs/core/impl/http/SendQueue.hpp:59`, `SendQueue.cpp:106`, `:303-327`), and drops any
  non-200 answer without retrying (`SendQueue.cpp:389-401`). It lives in memory, so an LMS restart
  drops whatever is still queued.

So any stretch of more than about 15 seconds in which MuMa is unreachable or answers 5xx loses
every listen relayed in it. The three lost listens (05:26:10 to 05:39:53) fall inside the 0.73.2
release: `release/0.73.2` was pushed (which deploys) at 05:16:32 UTC and merged to master at
05:45:04 UTC; the listen that arrived (06:08:56) is after it. That is circumstantial. What would
settle it is LMS's log for those minutes: `Too many retries, giving up operation` or
`Send error, status = ...` from `[Http SendQueue]`. That log was not read for this report
(production was out of scope).

The 1,453 LMS-only listens are the sum of every such window since the relay exists, plus history
from before it.

A second oddity in the evidence comes from the same path: MuMa's row for 37787 is 55 s later than
LMS's. Without `time`, LMS takes the timestamp twice -- `InternalBackend::listenFinished` stamps
`currentDateTime()` before it waits for its write transaction
(`src/libs/services/scrobbling/impl/internal/InternalBackend.cpp:40-46`), and the relay stamps
`currentDateTime()` again afterwards (`MusicManagementBackend.cpp:60-63`, `:105-106`). A slow write
puts them apart, and the reconcile's 5-second `exact` window then no longer pairs them.

## 2. The app: every gap that would have lost a listen before it reached LMS

The native path (before this change) was `MediaPlayerManager`'s controller listener calling
`Scrobbler.scrobble`, which called `MusicService.scrobble` once, in a coroutine:

1. **Not running at all without an activity.** `MediaPlayerManager.onCreate` is only reached from
   `MediaPlayerLifecycleSupport.onCreate`, called by `CapacitorActivity.onResume`
   (`activity/CapacitorActivity.kt:171-175`) or a network-available callback
   (`service/MusicServiceFactory.kt:79`). Playback started by Android Auto or a media button in a
   fresh process had no listener, and so no scrobbles.
2. **A failed send was dropped.** `Scrobbler.kt:64-80` (old) caught the exception, logged it at INFO
   and forgot the listen. Prod diagnostics report 37 lost one to a `500` from `/rest/scrobble`. A
   retry was not safe either: the request carried no `time` (`RESTMusicService.kt:391`, `null`), so
   a request that had committed before failing would have become a second listen.
3. **Offline listens were discarded.** `isScrobblingEnabled()` is false in offline mode
   (`data/ActiveServerProvider.kt:326-331`), and `autoSwitchOffline` switches to offline mode as soon
   as the network is gone, so the listen was not even attempted.
4. **A listen only existed once the track was left.** The submission fired on
   `onMediaItemTransition` or `STATE_ENDED` (`MediaPlayerManager.kt:140-151`, `:318-336`, old). A
   long set whose process was killed mid-play left nothing.
5. **Radio and news were sent with synthetic ids** (`MEDIA_RADIO_TRACK|<id>`, `MEDIA_NEWS_ITEM|<id>`),
   which LMS refuses.
6. **A track played twice in a row was suppressed** by `id == lastSubmission` (`Scrobbler.kt:53`, old).
7. **The playing time was a position, not a duration**, read from the discontinuity before the
   transition; a seek to the end of a set reported the whole set as played.

# solution

**App (MuMa Mobile).** Scrobbling moved from `MediaPlayerManager` into `PlaybackService`, which is
alive whenever anything plays. Every play is measured by `PlayTally` (wall-clock start, monotonic
playing time, pauses excluded). `ScrobbleLedger` writes a play into `PendingScrobbleQueue` -- a
preferences file, plain text so the next build can read it -- as an open entry as soon as it has
5 seconds, updates it every 10 seconds and on every pause, and closes it when the track is left for
any reason, including the end of the queue and the service stopping. A new process closes the open
entries the old one left behind. `ScrobbleDelivery` sends closed entries oldest first, with the
play's start as the Subsonic `time`, and removes an entry only once the server answered; anything
else is retried on the next listen, when the network returns, on a 30 s to 15 min back-off, and in
the next process. Offline listens are queued, radio items are reported as the track they play,
news is not reported, and a repeat is a second listen.

Sending `time` is what makes all of that safe: LMS takes the `addTimedListen` path
(`MediaAnnotation.cpp:238`), skips a listen it already has for that second
(`InternalBackend.cpp:54`), and relays that same second to MuMa, whose unique key
`(username, listened_at, track_id)` turns a repeat into an update. It also puts LMS and MuMa on the
same timestamp, so the reconcile pairs them exactly.

Tests: `ScrobbleLedgerTest` (threshold then skip; below threshold; process death; restart sends
once; offline then online; not-found dropped; repeat; pauses; end of queue; server and age limits),
`PendingScrobbleCodecTest`, `ScrobbleRulesTest` (radio/news ids, repeated-item rule),
`test_scrobble_played_secs.py` (start time is the stored time; identical upserts) and
`test_router_sql.py::ScrobblingTest::test_a_retried_matched_listen_is_stored_once` (one row in
MariaDB).

**Not fixed here: LMS's relay.** The three listens of this morning would still be lost, because the
app did its part. The existing reconcile can insert them (`POST /api/scrobble/reconcile/lms` with
`insert_lms_only`). Making the relay durable -- an outbox in LMS, or MuMa pulling recent LMS-only
listens on a schedule -- is a decision recorded in the open GitLab issues.
Decided in bug report 075: MuMa pulls, through the `lms-listen-backfill` loop.
