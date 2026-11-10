# LMS Rating Outbox: Technical Design

Implements [functional.md](functional.md). Issue #222. Builds on the listen outbox
([lms-listen-outbox/technical.md](../lms-listen-outbox/technical.md)), issue #67.

## Where It Starts

`src/libs/services/feedback/impl/musicmanagement/MusicManagementBackend.cpp` (`sendEvent`) builds
the JSON body and calls `sendPOSTRequest` once on its own `core::http::IClient`. The client is
created with `treatAnyStatusAsSuccess = false`, so a non-200 answer and a transport error both end
in `onFailureFunc`, which logs one WARNING. Nothing else happens to the event.

`FeedbackService::setRating` calls the backend after its write transaction commits, on the thread
that set the rating (a Wt request thread for the web player and Subsonic). A removal is captured
before the rated row is deleted (`RatingRemovedEvent`), so the body of a removal can only be built
at that moment.

The relay goes to the user's configured feedback backend only (`User::getFeedbackBackend`). All
production users have `MusicManagement` (2). This design keeps that rule.

## Data Model

New table in `lms.db`, created by LMS migration step 127 to **128** (`LMS_DATABASE_VERSION` 128,
`migrateFromV127`), the next free step under the
[database version policy](../../../services/music-management-server/FORK.md#database-version-policy).
Before merge, check that no other open branch claims step 127; whichever merges second renumbers.

A fresh database starts at the current version and runs no step, so `Session::createIndexesIfNeeded()`
creates the table as well. Both use `Migration::mumaRatingOutboxTableDefinition` and
`mumaRatingOutboxIndexDefinition` in `Migration.hpp`, as the listen outbox does:

```sql
CREATE TABLE IF NOT EXISTS muma_rating_outbox (
  id          INTEGER PRIMARY KEY AUTOINCREMENT, -- relay order; AUTOINCREMENT never reuses an id
  username    TEXT    NOT NULL,                  -- login name, as in the payload
  object_type TEXT    NOT NULL,                  -- 'track', 'release' or 'artist'
  object_id   TEXT    NOT NULL,                  -- LMS track id, or the release/artist name
  payload     TEXT    NOT NULL,                  -- the JSON body exactly as POSTed
  created     INTEGER NOT NULL,                  -- Unix seconds, when this state was queued
  attempts    INTEGER NOT NULL DEFAULT 0         -- failed deliveries, informational
);
CREATE UNIQUE INDEX IF NOT EXISTS muma_rating_outbox_item_idx
  ON muma_rating_outbox (username, object_type, object_id);
```

The key is the same triple music-manager stores under (`rating_tracks`: `entity_type`, `entity_id`,
`username`). Releases and artists are identified by name on both sides, so two releases with the
same name share one key here, as they share one row there.

Storage goes through a new `database/MumaRatingOutbox.hpp` (`replace`, `front`, `remove`,
`recordAttempt`, `dropOverflow`, `dropOlderThan`, `getStatus`), a plain table like
`MumaListenOutbox.hpp`, not a `Wt::Dbo` object.

### The last state wins

`replace(session, key, payload, created)` runs in one write transaction:

```sql
DELETE FROM muma_rating_outbox WHERE username = ? AND object_type = ? AND object_id = ?;
INSERT INTO muma_rating_outbox (username, object_type, object_id, payload, created) VALUES (?, ?, ?, ?, ?);
```

It deletes and inserts on purpose, and does not update in place. The new row gets a new `id`, and
that keeps a change in flight safe. Take row 5 (rating 3) on its way to music-manager when the user
sets 4. `replace` removes row 5 and adds row 9. The answer to row 5 removes "row 5", which is
already gone, so nothing happens. Row 9 goes next. An update in place would keep id 5, and the
answer to the old request would delete the new state before it was sent.

A removal is a state like any other. Its payload is `rating_removed` and it replaces a waiting
`rating_changed` for the same item. It is always sent, also when the replaced change was never
delivered, because the relay cannot know whether music-manager had a rating from before. The
DELETE on music-manager's side is a no-op when there is nothing to delete.

The payload is fixed when the change is queued: event, object type and id, username, rating, and
for a track the absolute path. The API key header is added at send time, so a rotated key applies
to changes already waiting.

## Flow

```
Wt request thread                     io_context (strand)                       music-manager
-----------------                     -------------------                       -------------
FeedbackService::setRating
  -> feedback MusicManagementBackend
     build payload (read txn)
     MumaOutboxRelay::enqueueRating
        replace + dropOverflow (write txn)
        wake() ----------------------> sendNext()
                                         drop rows past maxAge (both tables)
                                         pick the older front of the two tables
                                         POST (shared IClient) -----------------> /api/rating/lms-event
                                       onAnswer(table, id, status) <------------- or /api/scrobble/event
                                         2xx/409: remove(table, id), sendNext()
                                         400/413/422: WARNING, remove, sendNext()
                                         other: attempts++, retry timer
                                       onTransportFailure: attempts++, retry timer
```

### One relay for both outboxes

`ListenOutboxRelay` becomes `MumaOutboxRelay`. It has the same strand, the same single HTTP client
and send queue, one request in flight, the same backoff (5 s, doubling, capped at 60 s, reset by a
success) and the same status rules. What changes:

- **Two tables, one queue.** `sendNext` reads the front of `muma_listen_outbox` and the front of
  `muma_rating_outbox` and sends the one with the smaller `created`; on a tie the listen goes
  first. Listens and ratings are independent at music-manager, so the order between them only
  decides who waits. Oldest first means a rating made after a long outage waits behind that
  outage's listens, which takes seconds: one small request each, one at a time.
- **One URL per table.** The client is created with `music-management-url` as its base, and each
  request sets `relativeUrl`: `/scrobble/event` for a listen, `/rating/lms-event` for a rating
  (`SendQueue` builds `baseUrl + relativeUrl`).
- **The answer names its table.** `Answer` carries `{ table, id, status }`, so `remove`,
  `recordAttempt` and the log line go to the right table.
- **One backoff.** A failure on either table delays both. The same music-manager serves both
  endpoints, so an outage for one is an outage for the other.
- **Logging.** The prefix becomes `[MuMa outbox]`, and each line says `listen` or `rating`. Still one
  WARNING per outage, one INFO on recovery, one WARNING per drop.

The cost of sharing: a rating that music-manager keeps answering with a retryable status (a 500 from
a bug that hits one payload) blocks the listens behind it, and the reverse. That was already true
inside the listen outbox, and `maxAge` ends it after 14 days. Two relays would isolate the tables
but would also send two requests at once to a music-manager that is just coming back, and need two
of everything this design reuses. Teun chose the shared relay.

### Who owns the relay

The relay is no longer owned by the scrobbling backend, because the feedback service needs it too.
It moves to a library of its own, `src/libs/services/mumaoutbox/` (`IMumaOutboxRelay`,
`MumaOutboxRelay`, `createMumaOutboxRelay(ioContext, db)`), and `main.cpp` creates it as
`core::Service<IMumaOutboxRelay>` before the feedback and scrobbling services. `core::Service`
destroys in reverse order, so the relay outlives both backends. Its destructor calls `stop()`. The
relay calls `start()` once, after both services exist, so `Resuming N listen(s) and M rating(s)
queued since ...` reports both tables.

Both backends take an `IMumaOutboxRelay*` in their constructor. Production passes
`core::Service<IMumaOutboxRelay>::get()`, and the tests pass their own relay with a fake client. A
null relay (no `music-management-url`) means the backend does nothing, as a null client does now.

The interface:

```cpp
class IMumaOutboxRelay
{
public:
    virtual ~IMumaOutboxRelay() = default;
    virtual void start() = 0;
    virtual void enqueueListen(std::string_view payload) = 0;
    virtual void enqueueRating(const RatingKey& key, std::string_view payload) = 0;
    virtual void stop() = 0;
};
```

`RatingKey` is `{ username, objectType, objectId }`. Both `enqueue` calls write in a write
transaction on the calling thread, log an ERROR and return if the write fails, and then wake the
relay. A failed rating write loses that change, as today's failed POST does. The ERROR names the
user and item.

### Bounds and drops

| Bound | Listens | Ratings |
|---|---|---|
| `maxCount` | 10,000 | 10,000 |
| `maxAge` | 14 days | 14 days (open question in functional.md) |
| On a drop | WARNING with the count | WARNING per dropped row with username, object type and id |

A dropped listen is still in LMS's `listen` table, where music-manager's `lms-listen-backfill` can
find it. A dropped rating has no such net. The WARNING says which row went and that
`scripts/restore_lms_ratings.py export-lms` and `import-muma` repair it. `maxCount` for ratings is a
guard, not a working limit: one row per user and item means the table only reaches it if more than
10,000 distinct items change during one outage.

`MumaOutboxSettings` holds both pairs of limits, with the same defaults as `ListenOutboxSettings`.

## API Contract

No endpoint changes on LMS.

### music-manager: `POST /api/rating/lms-event`

The body and the answers stay as they are. A repeat is harmless: `rating_changed` is
`INSERT ... ON DUPLICATE KEY UPDATE`, and `rating_removed` is a `DELETE` by key. The relay depends
on the answers below:

| Answer | When | Relay |
|---|---|---|
| 200 `success` / `removed` | written | delivered, row removed |
| 200 `ignored` | unknown `event` | delivered, row removed |
| 403 | not the system key | kept, retried |
| 422 | body does not parse | dropped with a WARNING |
| 500 | database unreachable | kept, retried |

One change in the handler. For a track with a `path` it first resolves the path to a `track_uid`.
When that lookup gets no database connection (`get_db_connection()` returns None) it now carries on
with the LMS track id, and the second connection a moment later usually succeeds. The rating is then
stored under a dead id and answered with 200, so the relay removes it. The handler answers 503
instead, and the relay retries. A path that resolves to no track stays as it is: it stores the LMS
id, as it does today. That is a library question, not a delivery failure.

The path prefix needs no change. LMS sends its own spelling (`/music/...` on production) and
`library_paths.candidate_paths` tries both roots in both directions (MR !287, 0.10.0). The payload is
frozen at queue time, so a file moved between queueing and delivery is looked up under its old path
and falls back to the LMS id. That is rare and the same as a delivery during the move today.

### music-manager: `GET /health`

One more informational field, next to `lms_listen_outbox` and with its shape:

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /health` | none | adds `lms_rating_outbox`: `[{"server": str, "count": int\|null, "oldest": ISO-8601 UTC\|null}]`. `count` is null for an LMS older than db version 128. An unreadable file also gets an `error` string. The whole field is null if listing the LMS databases fails. | Never changes `status` or the HTTP code. |

`lms_listen_backfill.outbox_status()` takes the table name as a parameter, from a fixed set of
two, and `main.py` gets `_lms_rating_outbox_status()` beside `_lms_listen_outbox_status()`. The
SQL is `SELECT COUNT(*), MIN(created) FROM muma_rating_outbox`. Additive, not a breaking change:
Uptime Kuma and the Home Assistant sensor read `status` only. `docs/api-specification.md` gets the
field.

## Cross-App Impact

- `music-management-server` (LMS): migration 128, the outbox table and its storage functions, the
  relay moved into `services/mumaoutbox` and taught a second table, both backends on the shared
  relay, `main.cpp` wiring. `src/libs/services/feedback/impl/musicmanagement/README.md` describes
  the outbox. FORK.md: step 127 in the list of fork steps (103 to 127), and the new library in the
  table of MuMa-specific subsystems.
- `music-manager`: the 503 in `routers/rating.py`, `outbox_status` per table, the `/health` field,
  `docs/api-specification.md`, AGENTS.md (the `/health` paragraph names `lms_listen_outbox`; it
  gets `lms_rating_outbox` too).
- Frontend, MuMa Mobile: none. They rate through LMS's Subsonic API, which is unchanged.

## Technical Acceptance Criteria

1. `test-database`:
   - `MumaRatingOutbox.cpp`: `replace` of a waiting item gives one row with a new, higher id;
     `front`, `remove` of a missing id, `recordAttempt`, `dropOverflow`, `dropOlderThan`,
     `getStatus`.
   - `Migration.cpp`: step 127 creates the table and the unique index, and a re-run keeps the rows.
     A fresh database has the table too.
2. `test-feedback` (`src/libs/services/feedback/test/MusicManagementBackend.cpp`), with a fake
   client:
   - `anOutageThenRecoveryDeliversTheRating`: transport failure, 503, then 200 delivers the rating.
   - `theLastStateWins`: 3, then 5, during an outage sends 5 only.
   - `aRemovalAfterASetSendsTheRemoval`: set 4, clear, during an outage sends `rating_removed` only.
   - `aChangeDuringAnInFlightRequestIsSentAfterIt`: rate 3, rate 4 before the answer to 3; the
     answer to 3 leaves the row for 4, which is sent next.
   - `aRetryIsTheSameBody`: the retried body is byte-identical.
   - `aRefusedRatingIsDroppedAndTheNextGoes` (422) and `anUnauthorisedAnswerKeepsTheRating` (403).
   - `theRatingOutboxSurvivesARestart`: a row left by a destroyed relay is sent by the next one.
   - `aRatingPastItsAgeIsDroppedWithItsKeyInTheLog`, and the count bound.
   - `settingARatingSendsNothingOnTheCallingThread`.
3. The relay tests that cover both tables
   (`src/libs/services/mumaoutbox/test/MumaOutboxRelay.cpp`; the listen cases move there from
   `test-scrobbling` unchanged):
   - `theOlderChangeGoesFirstAcrossTables`: a listen queued before a rating is sent first, and the
     reverse.
   - `eachTableGoesToItsOwnUrl`: `relativeUrl` is `/scrobble/event` or `/rating/lms-event`.
   - `anAnswerRemovesTheRowFromItsOwnTable`: a listen and a rating with the same id do not touch
     each other.
   - `oneBackoffForBoth`: a failed rating delays the next listen.
4. `services/music_manager/tests/test_rating.py`: a repeated
   `rating_changed` and a repeated `rating_removed` leave one result; the path lookup without a
   connection answers 503 and writes nothing.
5. `services/music_manager/tests/test_lms_listen_backfill.py::OutboxStatusTest`: the rating table
   per server, an LMS without it (`count: None`), and `/health` carrying `lms_rating_outbox`
   without turning red.
6. `tests/integration/test_router_sql.py`: nothing new, the rating SQL is unchanged.
7. `tests/contracts/test_relay_outbox_outage.py`: with music-manager stopped, rate the fixture
   track through LMS (`setRating`, token-signed as the listen case is), then rate it again with
   another value. After music-manager starts, `rating_tracks` holds the second value. A third case
   clears the rating during the outage and checks the row is gone.
8. `./scripts/test/muma-server-unit.sh`, `muma-server-tidy.sh` and `muma-server-format.sh` pass.

## Related Docs

- [docs/designs/lms-listen-outbox/technical.md](../lms-listen-outbox/technical.md)
- [docs/designs/ratings-scrobbling/technical.md](../ratings-scrobbling/technical.md)
- [services/music-management-server/FORK.md](../../../services/music-management-server/FORK.md)
- [docs/api-specification.md](../../api-specification.md) (`POST /api/rating/lms-event`)
