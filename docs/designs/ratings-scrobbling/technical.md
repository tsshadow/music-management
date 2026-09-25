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
- **Frontend (Svelte)**: Uses `GET /api/rating/ratings/{username}` to display user ratings and includes ratings in dynamic playlist track listings.
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
   `listened_at` or `created_at` within 5 s of it (the same play under another track, or unmatched
   -- whose `listened_at` may itself have been moved, while `created_at` was not).

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

## Related Docs

- [docs/architecture.md](../../architecture.md) — Overarching system structure.
- [docs/database-design.md](../../database-design.md) — Listening domain schema.
- [docs/api-specification.md](../../api-specification.md) — API endpoint overview.
