# External Rating Synchronization (MusicManagement)

This module provides a mechanism to synchronize user ratings from LMS to an external management tool.
This is particularly useful if you want to write ratings back to the audio file tags, as LMS maintains a read-only principle for the music library.

## How it works

When a user sets or clears a rating for a track, release or artist (via the MuMa web player, the
Subsonic API, or any other interface), the `MusicManagement` feedback backend builds the event
below and writes it to the `muma_rating_outbox` table (LMS database version 128 and later). It
does not send anything itself.

The relay in `src/libs/services/mumaoutbox/` sends the rows of that table, and of the listen outbox
(`muma_listen_outbox`), to music-manager: oldest first across both tables, one request at a time,
on the io_context and never on the Wt request thread.

- A row stays until music-manager answers 2xx or 409. On a connection failure or any other answer
  (5xx, 401/403, 404) the relay waits 5 s, doubling up to 60 s, and sends the same body again.
  The wait is shared with listens, because one music-manager serves both.
- 400, 413 and 422 mean the body is wrong and will stay wrong: the row is dropped with a `WARNING`.
- One row per user, object type and object id. A newer change replaces a waiting one, so three
  changes during an outage send the last state only, and a cleared rating sends the removal.
- A row older than 14 days, or past 10,000 waiting rows, is dropped with a `WARNING` that names the
  user and the item. `scripts/restore_lms_ratings.py export-lms` and `import-muma` repair what
  was dropped.
- The table survives a restart of LMS: the next start sends what is left.

Design: `docs/designs/lms-rating-outbox/` in the repository root.

## Configuration

### 1. LMS Configuration (`lms.conf`)

The relay sends to `<music-management-url>/rating/lms-event`, with `music-management-api-key` as
`X-API-Key`. Without `music-management-url` there is no relay, and nothing is queued.

```conf
# music-manager's API root; each route is appended to it
music-management-url = "http://music-manager:8000/api";
music-management-api-key = "<the system key>";
```

### 2. Database Activation

To enable this backend for a specific user, you must update the `feedback_backend` column for that user in the database.

Using SQLite:
```sql
UPDATE user SET feedback_backend = 2 WHERE name = 'your_username';
```
*(Note: `2` corresponds to the `MusicManagement` enum value in the LMS source code)*

## Webhook API Specification

The external service should expect a `POST` request with a JSON payload.

### Payload Structure

```json
{
  "event": "rating_changed",
  "object_type": "track",
  "object_id": "string (UUID)",
  "username": "string",
  "rating": integer (0-5),
  "path": "string (absolute file path)"
}
```

- **event**: `rating_changed` when a rating is set, `rating_removed` when it is cleared. The
  removal is captured before the rated row is deleted (`RatingRemovedEvent`); before that, a
  cleared rating sent nothing at all.
- **object_type**: `track`, `release` or `artist`.
- **object_id**: The internal LMS ID of the track, or the release/artist name.
- **username**: The login name of the user who rated.
- **rating**: The new rating (1-5); always `0` for `rating_removed`.
- **path**: The absolute path to the audio file on disk. This is useful for tools like `music-management` to identify exactly which file to tag.

## Technical Details

- **Implementation**: `src/libs/services/feedback/impl/musicmanagement/MusicManagementBackend.cpp`
- **Service Integration**: The `FeedbackService` calls the backend, which writes the outbox row on
  the calling thread and returns; the shared relay (`IMumaOutboxRelay`, created in `main.cpp`)
  delivers it on the `boost::asio` io_context.
