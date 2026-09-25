# Ratings & Scrobbling — Technical Design

> See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This document implements the [functional design](functional.md) and describes the technical implementation in `services/music_manager/routers/rating.py` and `services/music_manager/routers/scrobbler.py`.

## Data Model

The following tables in the MariaDB `music_management` database manage ratings and listening history:

### `rating_tracks`
Stores user-specific track ratings.

| Column | Type | Notes |
|---|---|---|
| `id` | `INT AUTO_INCREMENT` | Primary key |
| `entity_type` | `VARCHAR(50)` | Always 'track' in current implementation |
| `entity_id` | `VARCHAR(255)` | The `track_uid` from `library_tracks` |
| `username` | `VARCHAR(255)` | The MuMa username |
| `rating` | `INT` | 0-100 scale |
| `updated_at` | `TIMESTAMP` | Auto-updated on rating changes |

**Unique Constraint**: `(entity_type, entity_id, username)` ensures one rating per track per user.

### `scrobble_listens`
Stores matched listening events.

| Column | Type | Notes |
|---|---|---|
| `id` | `INT AUTO_INCREMENT` | Primary key |
| `track_id` | `INT` | FK to `library_tracks.id` |
| `listened_at` | `TIMESTAMP` | When the track was played |
| `username` | `VARCHAR(255)` | |
| `source` | `VARCHAR(50)` | 'manual', 'listenbrainz', etc. |

**Unique Constraint**: `(username, listened_at, track_id)` prevents duplicate scrobbles.

### `scrobble_unmatched_listens`
Stores listening events that couldn't be resolved to a library track at ingestion time.

| Column | Type | Notes |
|---|---|---|
| `artist_name` | `VARCHAR(512)` | Raw artist name from event |
| `track_title` | `VARCHAR(512)` | Raw track title from event |
| `data` | `JSON` | Full original event payload for later reconciliation |

## API Contract

### Rating Service (`/api/rating`)

| Endpoint | Method | Body / Params | Response | Error cases |
|---|---|---|---|---|
| `/lms-event` | `POST` | `MuMaServerEvent` (event, object_type, object_id, username, rating, path?) | `200 {status: "success", entity_id: "..."}`; `200 {status: "removed", entity_id: "..."}` for `rating_removed` | `401` Unauthorized; `500` DB failure |
| `/ratings/{username}` | `GET` | — | `200 List[Rating]` | `401` Unauthorized |

**Logic**: `/lms-event` resolves the `object_id` to a MuMa `track_uid`. If a `path` is provided, it attempts to look up the track in `library_media_files` to find the correct `track_uid`.
`rating_changed` upserts the row; `rating_removed` (sent with `rating: 0` when a rating is cleared
on the server) and a `rating_changed` with `rating <= 0` delete it. Before bug report 044 the server
sent nothing on a clear, so the mirror kept the old rating.

### Scrobbler Service (`/api/scrobble`)

| Endpoint | Method | Body / Params | Response | Error cases |
|---|---|---|---|---|
| `/event` | `POST` | `ScrobbleEvent` | `200 {status: "success", matched: bool}` | `401` Unauthorized |
| `/import/listenbrainz` | `POST` | `{username, lb_username?, token?}` | `200 {status: "ok", import_id: int}` | `403` another account's `username` (admins and the system key excepted); `500` DB failure |

An import pages through ListenBrainz with an exclusive `max_ts`, at most 100 pages of 100 listens per
run. A run that reaches that cap ends as `truncated` rather than `completed`, and stores the oldest
timestamp it reached in `scrobble_imports.oldest_listened_ts`; the next import for the same account
continues below it.

**Logic**: `/event` attempts to match `artist_name` and `track_title` against `library_artists` and `library_tracks`. If matched, it inserts into `scrobble_listens`; otherwise, it inserts into `scrobble_unmatched_listens`.

## Cross-App Impact

- **Music Management Server (LMS)**: Must be configured with the Music Manager's URL to send webhooks on rating changes. LMS handles Subsonic `star` actions and translates them into these webhooks.
- **Frontend (Svelte)**: includes ratings in dynamic playlist track listings. `GET /api/rating/ratings/{username}`
  has no frontend caller (checked in bug report 084); the end-to-end suite (`tests/bdd`) reads it to
  verify the rating round trip.
- **MuMa Mobile (Android)**: No direct impact; relies on LMS to proxy rating changes via the established webhook.

## Technical Acceptance Criteria

1. **Path Resolution**: Ratings events from LMS containing a file path must correctly resolve to the `track_uid` even if the LMS `object_id` differs from the MuMa internal ID.
2. **Deduplication**: Multiple scrobble events for the same timestamp and track must not result in duplicate `scrobble_listens` rows.
3. **Background Processing**: ListenBrainz imports must be handled by `BackgroundTasks` to ensure the API remains responsive during long-running imports.
4. **Dynamic Playlist Integration**: Dynamic playlist queries in `users.py` must correctly join with `rating_tracks` to allow filtering by `rating_range`.
5. **Testing**: All flows must be verified by `services/music_manager/tests/test_rating.py`.

## LMS listen reconcile (2026-09-24)

Repair tool for bug report 039. Logic in `services/music_manager/scrobble_reconcile.py`
(pure `classify()` plus loaders and writers), endpoints in `routers/reconcile.py`, mounted at
`/api/scrobble/reconcile`. No schema change.

**Sources.** Every `lms.db` `routers/users.py::lms_db_targets()` finds (the same list the hourly
LMS sync uses), opened read-only (`file:...?mode=ro`). From each:

```sql
SELECT l.id, l.date_time, u.login_name, t.absolute_file_path
FROM listen l JOIN user u ON u.id = l.user_id JOIN track t ON t.id = l.track_id
WHERE l.backend = 0 AND (l.sync_state IS NULL OR l.sync_state != 2)
```

`backend = 0` is `ScrobblingBackend::Internal` (the listens LMS records itself). A scrobble
without a Subsonic `time` is stamped twice with `currentDateTime()` -- once by the Internal backend,
once by `MusicManagementBackend` -- which a slow write can put seconds apart; a scrobble with `time`
(MuMa Mobile since bug report 071) carries that one instant to both. `sync_state = 2`
is `PendingRemove`. The same (user, muma track, second) seen on two servers counts once.

**The LMS-to-muma track join.** By file path, as the rating webhook and the version sync do:
`listen.track_id` -> `track.absolute_file_path` -> every spelling
`library_paths.candidate_paths()` produces (the path as given, under `MUMA_MUSIC_ROOT`
(`/mnt/music`), under `LMS_MUSIC_ROOT` (`/music`), and relative) -> `library_media_files.file_path`
(`WHERE track_id IS NOT NULL`, 200 paths per `IN`) -> `library_media_files.track_id`. The first
spelling muma has wins. The user joins by name: LMS relays `user.login_name` as `username`. A
listen whose file muma does not know is reported as `lms_unmapped`.

**Time.** LMS `date_time` is Wt::Dbo's SQLite text, `YYYY-MM-DDTHH:MM:SS.mmm` in UTC; it is parsed
as UTC (an explicit offset or `Z` is honoured) and floored to whole seconds. muma's side is read
as `UNIX_TIMESTAMP(listened_at)` / `UNIX_TIMESTAMP(created_at)` and written as
`FROM_UNIXTIME(%s)` on a session pinned to `+00:00` (restored afterwards). The relay stored
`datetime.fromtimestamp(ts)` -- a naive value in the process zone -- which MariaDB read in the
session zone; `zone_check()` compares the two offsets, the dry run reports them under `zones`,
and the apply refuses (`ZoneMismatchError`) when they differ.

**Classification**, per (username, muma track), deterministic (every ordering is total: gap,
muma id, LMS server and id):

1. `exact`: |muma - LMS| <= 5 s. Pairs are taken smallest gap first, one-to-one.
2. `shifted`: from what is left, muma - LMS > 5 s (the bug moved times forward only), the muma
   row is live (`source` not `listenbrainz`/`listenbrainz_import`) and shows a later write
   (|`listened_at` - `created_at`| > 5 s; `created_at` never had an ON UPDATE). Smallest gap
   first, one-to-one, so an LMS listen repairs at most its nearest moved row. Stricter than
   "nearest LMS listen more than 5 s away" on purpose: an untouched row is a second play.
3. `muma_only`: every muma listen not paired. Never written.
4. `lms_only`: every LMS listen not paired. `insertable` only if no unpaired muma listen of the
   same user and track exists and no muma listen or unmatched listen of the user has a
   `listened_at` or `created_at` within `SAME_PLAY_WINDOW_SECONDS` (600 s) of it (the same play
   under another track, or unmatched -- whose `listened_at` may itself have been moved, while
   `created_at` was not). Until bug report 070 this guard used the 5 s pairing window, but LMS
   records a listen when playback starts and the app scrobbles about a minute later (55 s
   observed), so the same play under another track id slipped through. The cost of 600 s: a lost
   scrobble within ten minutes of any other listen of the user stays reported-only.

Usernames are compared case-insensitively (`str.casefold()`) in grouping, pairing and the guard,
and every name is rewritten to muma's `users.username` (oldest account first) before classifying,
so `user` in muma and `Teun` in LMS are one user and an insert carries muma's spelling. An LMS
user muma does not know under any spelling is never insertable (bug report 070).

**Writes** (`POST`, background task, one transaction per user):

- shifted: `UPDATE scrobble_listens SET listened_at = FROM_UNIXTIME(lms) WHERE id = %s AND
  listened_at = FROM_UNIXTIME(old)` -- a row changed since the read is left alone and counted as
  `changed_since_read`.
- lms_only (opt-in, insertable only): `INSERT ... (track_id, listened_at, username, source,
  match_method) VALUES (..., 'lms-reconcile', 'exact')`.
- A 1062 on the UNIQUE (username, listened_at, track_id) is skipped and counted as `collisions`;
  any other error rolls that user's transaction back.
- Totals go to an INFO event "Listens reconciled against LMS" and to `GET /lms/status`.

Idempotent: repaired and inserted rows are `exact` on the next run.

| Endpoint | Method | Body / Params | Response | Error cases |
|---|---|---|---|---|
| `/api/scrobble/reconcile/lms` | `GET` | `username?` | `200 {username, servers, zones, totals, users, sample}` | `401`; `403` not admin; `503` no `lms.db` visible |
| `/api/scrobble/reconcile/lms` | `POST` | `{username?, apply_shifted: bool, insert_lms_only: bool}` | `200 {message, last}`; runs in the background | `400` nothing to apply; `401`; `403`; `409` already running |
| `/api/scrobble/reconcile/lms/status` | `GET` | -- | `200 {running, last, error}` | `401`; `403` |

Not a breaking change: new endpoints only, no existing contract touched.

**Not verified here:** the storage format comes from Wt 4.11.1's `Wt/Dbo/backend/Sqlite3.h` in the
server image (default `DateTimeStorage::ISO8601AsText`; LMS never calls `setDateTimeStorage`) and
LMS's mapping (`Listen.hpp`), not from a production `lms.db`; the parser also accepts a space
separator (`PseudoISO8601AsText`), no fraction and a zone suffix. The dry run's runtime on production size is unmeasured; it runs
inline, so a very large history may need `username` to stay under the proxy timeout.

## LMS listen backfill loop (2026-09-25)

Bug report 075. LMS relays each listen to `POST /api/scrobble/event` best-effort (in-memory
`SendQueue`, two immediate retries, any non-200 dropped, lost on restart), so every music-manager
outage loses the listens relayed during it. LMS's own `listen` table keeps them. Of the two ways
to make that durable -- an outbox in LMS, or MuMa pulling -- MuMa pulls: it reuses the tested
reconcile, survives LMS restarts, and needs no C++ change; LMS's `listen` table is the outbox.

**The loop.** `services/music_manager/lms_listen_backfill.py`, started at startup as the
`lms-listen-backfill` thread through `thread_registry.run_forever` (so it appears in `/health`
`threads` and `heartbeats`; `stale_after` is 72 h because the interval can be raised at runtime).
Each round reads the settings, opens every `lms_db_targets()` database read-only and calls
`scrobble_reconcile.backfill(conn, servers, since=now - window, until=now - 1800)`:

- the same `_analyse()`/`classify()` as the manual reconcile, but LMS listens are read only from
  `since` on (`AND julianday(l.date_time) >= julianday(?)`, so the `T` separator Wt::Dbo writes
  compares as an instant), and `scrobble_listens` / `scrobble_unmatched_listens` from
  `since - CONTEXT_MARGIN_SECONDS` (1,200 s, twice the same-play window) on, matching a row when
  `listened_at` *or* `created_at` is inside (the guard reads both);
- only `lms_only` listens that are `insertable` and at or before `until` are written -- a listen
  LMS recorded in the last 30 minutes (`SETTLE_SECONDS`) is left for its own relay and for the
  app's scrobble to arrive first, and picked up by a later round;
- **`shifted` is never applied**; nothing existing is updated;
- inserts go through the reconcile's writer with `source = 'lms-backfill'`, LMS's start time as
  `listened_at`, the account's own spelling of the username (`canonicalize()` over
  `identity.account_spellings()`, exactly as the manual reconcile; an LMS user without a muma
  account gets nothing), `match_method = 'exact'` (the track is resolved by file path), one
  transaction per user, a 1062 on UNIQUE `(username, listened_at, track_id)` counted as a
  collision. A later relay of the same play (same second, since the app sends `time`) lands on
  that key and becomes an update of the backfilled row.

Rows are ordinary `scrobble_listens` rows: no reader filters on `source`, so ratings, listening
statistics (`/api/listening/sources` shows them as `lms-backfill`) and feeds count them like any
listen.

One difference from a full-history run: "no unpaired muma listen of the same track" only looks
inside the window, so an old unpaired import of the same track no longer blocks a recent insert.

**Settings** (`services/common/config_store.py`, group "Scrobbling", read every round):
`lms_listen_backfill_enabled` (default on), `lms_listen_backfill_interval_minutes` (15),
`lms_listen_backfill_window_hours` (48). Invalid or non-positive numbers fall back to the default.

**Logging.** One INFO line per round that inserted something (count per user), DEBUG otherwise. A
failing round (database gone, `ZoneMismatchError`, unreadable `lms.db`) is caught inside the tick:
one WARNING for a run of failures, DEBUG for the repeats, re-armed by the next success. The
heartbeat keeps beating, so a missing LMS database does not mark music-manager unhealthy.

**The historical backlog** (listens older than the window, 1,453 LMS-only on 2026-09-25) is not
walked by the loop. It stays a one-off, admin-triggered run: dry run with
`GET /api/scrobble/reconcile/lms`, then `POST /api/scrobble/reconcile/lms` with
`{"insert_lms_only": true}` (source `lms-reconcile`), result on `GET /lms/status`.

No new endpoint, no schema change, no contract change.

## Related Docs

- [docs/architecture.md](../../architecture.md) — Overarching system structure.
- [docs/database-design.md](../../database-design.md) — Listening domain schema.
- [docs/api-specification.md](../../api-specification.md) — API endpoint overview.
