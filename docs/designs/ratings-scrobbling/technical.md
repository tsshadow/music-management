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

## Related Docs

- [docs/architecture.md](../../architecture.md) — Overarching system structure.
- [docs/database-design.md](../../database-design.md) — Listening domain schema.
- [docs/api-specification.md](../../api-specification.md) — API endpoint overview.
