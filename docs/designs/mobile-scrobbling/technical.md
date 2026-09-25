# Mobile Scrobbling — Technical Design

Implements [functional.md](functional.md). Code in `services/muma-mobile/app/src/main/kotlin/nl/teunschriks/mumamobile/service/`.

## Data Model

No server-side schema change. The server's existing keys are the de-duplication:

- LMS `InternalBackend::addTimedListen` skips a listen that already exists for
  `(user, track, Internal, listenedAt)`.
- MuMa `scrobble_listens` has `UNIQUE (username, listened_at, track_id)`, and `record_match` is an
  `INSERT ... ON DUPLICATE KEY UPDATE` that tops up `played_secs` and never touches `listened_at`;
  `scrobble_unmatched_listens` has `UNIQUE (username, listened_at, artist_name, track_title)`.

On the phone, a private preferences file `muma_pending_scrobbles`, key `queue`, holds the pending
listens as text, one per line, tab-separated (`PendingScrobbleCodec`):

| Field | Meaning |
|---|---|
| `trackId` | LMS track id (a radio item's wrapped id, never a `MEDIA_*` id) |
| `serverId` | Server the track belongs to; `-1` = whichever server is active when sending |
| `startedAtMs` | Wall-clock epoch ms at which the track first started playing |
| `playedSeconds` | Seconds actually playing, pauses excluded, seeks not added |
| `source` | `mobile` or `auto`, decided when the play started |
| `open` | `1` while the play is running in the process that wrote it |
| `attempts` | Failed sends so far (diagnostics only) |

The play's key is `serverId|trackId|startedAtMs`. Not Gson: R8 renames data-class fields in the
release build, and this file must be readable by the next build.

Limits: 2000 entries (oldest dropped first), 30 days (older entries dropped when the queue is read).

## Components

- `PlayTally` — measures the current play from two injected clocks (wall clock for the start,
  `elapsedRealtime` for the playing time). The start is set on the first transition to playing,
  not when the item becomes current.
- `ScrobbleLedger` — the decision. `onTrack` closes the previous play and begins the next;
  `checkpoint` (every 10 s while playing, and on every pause) writes the running play as an **open**
  entry once it has 5 s; closing writes it as a **closed** entry. Below 5 s nothing is written.
- `PendingScrobbleQueue` — the persistent list; `record` upserts by key; `closeOrphans` (called once
  per process, before anything is recorded) closes every open entry, because the process that
  wrote it is gone; `due(activeServerId)` returns closed entries for that server or `-1`.
- `ScrobbleDelivery` — sends due entries oldest first; stops at the first retryable failure.
  `SubsonicError` 70 (not found) or 10 (parameter missing) drop the entry; anything else is retried.
- `Scrobbler` — Android glue, owned by `PlaybackService` (not by the app-side `MediaPlayerManager`,
  which only exists once an activity created it). Fed by the service player's
  `onMediaItemTransition`, `onIsPlayingChanged`, `STATE_ENDED`, and a position discontinuity that
  moves to another queue entry holding the same item. Sends on a single-thread IO dispatcher.
  Flushes on start, after every closed listen, when a network becomes available, and on an
  exponential back-off (30 s doubling to 15 min) while entries are left.
  "Now playing" is sent once per play and never queued.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| LMS `GET /rest/scrobble.view` (unchanged) | `id`, `submission=true`, **`time=<startedAtMs>`** (now always sent by the app), `playedSeconds`, `source` | Subsonic OK | Subsonic error 70 for an unknown track (entry dropped); transport/5xx (entry retried) |
| MuMa `POST /api/scrobble/event` (unchanged) | LMS relays `listened_at` = the Subsonic `time` / 1000 | `200 {status, matched}` | unchanged |

With `time` present LMS takes the `addTimedListen` path: its own listen and the relay both carry
the start time, instead of two separately taken `currentDateTime()` values (MuMa's copy of listen
37787 on 2026-09-25 is 55 s later than LMS's own). Not a breaking change: `time` is standard Subsonic, and the web
player still sends none.

## Cross-App Impact

- MuMa Mobile: all changes.
- LMS, music-manager, frontend: none. Listens reported by the app are now dated at their start
  rather than at the moment the request arrived; the reconcile's `exact` class becomes reliable for
  them (`EXACT_WINDOW_SECONDS` = 5 was not enough when the two LMS timestamps drifted apart).

## Technical Acceptance Criteria

1. `ScrobbleLedgerTest`: threshold crossed then skip → one entry sent with the start time;
   below threshold → nothing; open entry + restart → sent exactly once; offline/IO failure → kept,
   attempts counted, sent once when the sender succeeds; not-found → dropped; same track twice →
   two listens; pause excluded; end of queue closes; age and size limits.
2. `PendingScrobbleCodecTest`: round trip; a damaged line is skipped.
3. `ScrobbleRulesTest`: radio id unwrapped, news and other `MEDIA_*` ids refused, repeated-item
   discontinuity rule.
4. `test_scrobble_played_secs.py`: the event's `listened_at` is the stored time, and two identical
   events produce identical upserts; `tests/integration/test_router_sql.py`
   `test_a_retried_matched_listen_is_stored_once` proves one row in MariaDB.

## Related Docs

- [Bug report 071](../../bug-reports/071-app-scrobbler-loses-listens.md)
- [Bug report 035](../../bug-reports/035-app-scrobbles-every-listen-twice.md)
- [Ratings & Scrobbling technical design](../ratings-scrobbling/technical.md)
