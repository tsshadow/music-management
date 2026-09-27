# LMS Listen Outbox — Technical Design

Implements [functional.md](functional.md). Issue #67, bug report 075.

## Data Model

New table in `lms.db`. It is created by LMS migration step 124 → **125**
(`LMS_DATABASE_VERSION` 125, `migrateFromV124`). For a fresh database it is created by
`Session::createIndexesIfNeeded()`, because a fresh database starts at the current version and runs
no migration step. Both use the same `Migration::mumaListenOutboxTableDefinition`, so they cannot
drift:

```sql
CREATE TABLE IF NOT EXISTS muma_listen_outbox (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,  -- relay order; AUTOINCREMENT never reuses an id
  payload  TEXT    NOT NULL,                   -- the JSON body exactly as POSTed
  created  INTEGER NOT NULL,                   -- Unix seconds, when the listen was queued
  attempts INTEGER NOT NULL DEFAULT 0          -- failed deliveries, informational
)
```

This is a plain table, not a `Wt::Dbo` object. Access goes through
`database/MumaListenOutbox.hpp` (`push`, `front`, `remove`, `recordAttempt`, `dropOverflow`,
`dropOlderThan`, `getStatus`).

The payload is fixed when the listen is recorded: user name, track title, album, first artist, MBID,
source, played seconds, and `listened_at` (the start time). A retry therefore sends the same bytes,
and music-manager's unique `(username, listened_at, track_id)` key makes a second delivery a no-op.
The API key header is added at send time, so a rotated key applies to listens already waiting.

## Flow

```
Wt request thread                       io_context (strand)                    music-manager
-----------------                       -------------------                    -------------
ScrobblingService::listenFinished
  -> MusicManagementBackend::sendScrobble
     build payload (read txn)
     ListenOutboxRelay::enqueue
        INSERT + dropOverflow (write txn)
        wake() ------------------------> sendNext()
                                           drop rows older than maxAge
                                           front() -> POST (own IClient) -------> /api/scrobble/event
                                         onAnswer(status) <-----------------------
                                           2xx/409: DELETE row, sendNext()
                                           400/413/422: WARNING, DELETE, sendNext()
                                           other: attempts++, retry timer
                                         onTransportFailure: attempts++, retry timer
```

- **Off the request threads.** The request thread writes one row and returns. Everything else runs
  on LMS's "Misc" io_context through a strand. The relay has its own `core::http::IClient`, and so
  its own `SendQueue`. A backlog here never sits in the `/muma` proxy's serial queue and never
  holds a Wt thread. Two known LMS problems came from exactly that: the serial `/muma` proxy queue
  (one slow call made everything behind it time out) and Wt thread-pool starvation.
- **In order, one at a time.** At most one request is in flight. A listen recorded during a pending
  retry waits for that retry rather than jumping ahead.
- **Backoff.** The first retry comes after 5 s. The wait doubles on each further failure, up to
  60 s. The send queue's own two quick retries on a transport error come first. The first success
  resets the backoff. The cap is 60 s, not longer, because the outage that matters is a deploy of a
  minute or so, and one small request a minute during a long outage costs nothing.
- **Status handling.** `treatAnyStatusAsSuccess = true`, so every answer reaches the relay:
  - `2xx`, and `409`: delivered, so the row is deleted. music-manager answers 200 for a duplicate.
  - `400`, `413`, `422`: the body itself is wrong, and a retry cannot help. The row is dropped with a
    WARNING so it does not block the queue.
  - Everything else (`401`/`403` during a key rotation, `404` from a proxy mid-deploy, `429`, `5xx`)
    and every transport error: the row is kept, `attempts` goes up, and a retry is scheduled.
- **Bounds.** At most `maxCount` = 10,000 rows. `enqueue` drops the oldest beyond that, with a
  WARNING. At most `maxAge` = 14 days: `sendNext` drops older rows first, with a WARNING. That is
  about ten weeks of this library's listening, well past any outage worth waiting for. What gets
  dropped is still in LMS's `listen` table, where music-manager's `lms-listen-backfill` loop can
  find it. That loop reads a 48-hour window, and an older listen needs the manual reconcile.
- **Restart.** `MusicManagementBackend`'s constructor calls `ListenOutboxRelay::start()`. It logs
  `Resuming N listen(s) queued since …` and wakes the relay. The destructor calls `stop()`, which
  takes the HTTP client away under a mutex and destroys it. That aborts its queue. Rows stay put.
- **Lifetime.** The relay is held by `shared_ptr`. The HTTP callbacks and the retry timer hold only a
  `weak_ptr`, so an answer that arrives after `stop()` does nothing.
- **Logging.** One WARNING per outage (the first failed attempt), one INFO on recovery, one WARNING
  per drop. Each retry is logged at DEBUG.

## API Contract

No endpoint changes on LMS. music-manager's `POST /api/scrobble/event` is unchanged; it already
answers 200 for a listen it had.

One additive field on music-manager's `GET /health`:

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /health` | — | adds `lms_listen_outbox`: `[{"server": str, "count": int\|null, "oldest": ISO-8601 UTC\|null}]`. `count` is null for an LMS older than db version 125. An unreadable file also gets an `error` string. The whole field is null if listing the LMS databases fails. | Never changes `status` or the HTTP code. |

Not a breaking change: the field is new, and Uptime Kuma and the Home Assistant sensor read
`status` only.

The status is shown through music-manager, not through a new LMS endpoint. LMS has no HTTP health
endpoint, and a new LMS-owned `/muma/api/...` route would also need the nginx regex that sends
`/muma/api` straight to music-manager, plus its routing test. music-manager already opens every
`lms.db` read-only (`lms_db_targets`) for the hourly sync and the backfill.

## Cross-App Impact

- `music-management-server` (LMS): migration 125, outbox table, relay.
- `music-manager`: `lms_listen_backfill.outbox_status()` and the `/health` field. The backfill loop
  stays unchanged, as the net behind the outbox.
- Frontend, MuMa Mobile: none.

Interaction with the backfill loop: the backfill only touches listens older than 30 minutes, and it
skips a listen with a muma listen within 600 s of it. In an outage longer than 30 minutes both paths
can deliver the same listen. They then agree on `listened_at`, and the unique key absorbs the
second, provided both resolve the same track. The relay matches by artist and title, the backfill by
path. When the two disagree, one listen can be counted twice. The backfill's guard catches that
whenever the relay was first, so the window is the backfill winning a race it only enters after 30
minutes of outage.

## Technical Acceptance Criteria

1. `test-scrobbling` (`src/libs/services/scrobbling/test/MusicManagementBackend.cpp`):
   - `anOutageThenRecoveryDeliversEveryListenInOrder`: a transport failure, then a 503, then
     recovery delivers three listens in play order, one in flight at a time.
   - `aRetryIsTheSameListenSoADuplicateIsHarmless`: the retry body is byte-identical, and a 409
     clears the row.
   - `theOutboxSurvivesARestart`: a row left by a destroyed backend is sent by the next one, and a
     late answer to the old one changes nothing.
   - `beyondItsSizeTheOutboxDropsTheOldest` and `aListenPastItsAgeIsDropped`: the bounds.
   - `aListenRefusedForGoodIsDroppedAndTheNextOneGoes` and `anUnauthorisedAnswerKeepsTheListen`:
     status handling.
   - `recordingAListenSendsNothingOnTheCallingThread`: nothing is sent before the io_context runs.
   - `aNewListenDuringAnOutageWaitsItsTurn`: order holds across a pending retry.
2. `test-database`: `MumaListenOutbox.cpp` covers the storage functions, and `Migration.cpp` covers
   step 124 (the table exists and a re-run keeps its rows).
3. `services/music_manager/tests/test_lms_listen_backfill.py::OutboxStatusTest`: the status per
   server, an LMS without the table, an unreadable file, and `/health` carrying the field without
   turning red.
4. `tests/contracts/test_relay_outbox_outage.py`: with music-manager stopped, a scrobble reaches LMS.
   After music-manager starts again, the listen arrives in `scrobble_listens`.

## Related Docs

- [docs/bug-reports/075-lms-relay-drops-listens-during-outages.md](../../bug-reports/075-lms-relay-drops-listens-during-outages.md)
- [docs/designs/mobile-scrobbling/functional.md](../mobile-scrobbling/functional.md)
- [docs/designs/ratings-scrobbling/technical.md](../ratings-scrobbling/technical.md)
