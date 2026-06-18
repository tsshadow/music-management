# External Rating Synchronization (MusicManagement)

This module provides a mechanism to synchronize user ratings from LMS to an external management tool. 
This is particularly useful if you want to write ratings back to the audio file tags, as LMS maintains a read-only principle for the music library.

## How it works

When a user sets a rating for a track (via the Spotify UI, Subsonic API, or any other interface), the `MusicManagement` feedback backend catches the event and forwards it to a configured webhook.

## Configuration

### 1. LMS Configuration (`lms.conf`)

Add or update the following setting in your `lms.conf` file:

```conf
# The URL of the external service that will receive the rating events
music-management-api-url = "http://music-management:8080/api/lms-event";
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
  "rating": integer (0-5),
  "path": "string (absolute file path)"
}
```

- **event**: Currently only `rating_changed` is emitted.
- **object_type**: Currently only `track` is supported.
- **object_id**: The internal LMS ID of the track.
- **rating**: The new rating (0-5). `0` means the rating was removed.
- **path**: The absolute path to the audio file on disk. This is useful for tools like `music-management` to identify exactly which file to tag.

## Technical Details

- **Implementation**: `src/libs/services/feedback/impl/musicmanagement/MusicManagementBackend.cpp`
- **Service Integration**: The `FeedbackService` calls the backend asynchronously using the `boost::asio` io_context.
