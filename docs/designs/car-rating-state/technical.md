# Car Rating State: Technical Design

Implements [functional.md](functional.md). The car's button is an incremental toggle:
`MediaLibraryCommandHandler.ratingAfterTap` steps from the rating on the playing `MediaItem`. The
whole design keeps "unknown" (null) apart from 0 on that item, and fills in the real value.

## Data Model

- No schema change. `TrackDao.setUserRating(id, rating)` is a new `UPDATE` on the existing
  `tracks.userRating` column, in the downloaded library (`offlineMetaDatabase`) and in the active
  server's cache.
- `Track.userRating` null means unknown in the queue path. A server answer without `userRating`
  means unrated, so the code that reads a server answer turns null into 0.
- `MediaItem` extras key `userRating`: present means known (0 to 5), absent means unknown.
  `buildMediaItem` writes it when it gets a rating. `MediaItem.toTrack` reads it and falls back to
  a rated `StarRating`; an unrated `StarRating` is unknown, not 0.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `MumaPlayer.setQueue` (Capacitor) | Each track also has `userRating`: 0 to 5, or null when unknown | Unchanged | A value that is not an integer from 0 to 5 is read as unknown |
| `MumaPlayer.setRating` (Capacitor, new) | `{id: string, rating: 0..5}` | Resolves at once | Rejects without an id or with a rating off the scale |
| `getSong.view` (Subsonic, LMS) | `id` | One `song` | The app treats a failure as "the server does not know" |

`setRating` writes nothing to the server. The web writes to the server itself (or to the phone's
rating queue), so a rating is never sent twice. This is not a breaking change: an older bundle
sends no `userRating`, which reads as unknown.

### What each part does

1. Web payload: `toQueueTrack(track, sessionRatings)` in `nativeQueue.js` adds `userRating`, from
   the `ratings` store first, then `track.userRating`, else null.
2. Web to native push: `ratings.js` calls `platform.player.setRating(id, value)` when it shows a
   rating, and again with the old value on a rollback. The plugin publishes
   `RxBus.ratingKnown`. `PlaybackService` applies it with `QueueRatings.applyToQueue`, which writes
   every queued item for the id (composite ids included), and redraws the button when the playing
   item is one of them. In the background the plugin calls
   `CachedMusicService.applyKnownRating` (cached lists, `MediaItemConverter`, Room).
3. Unknown on a tap: `ratingAfterTap(null)` is null. `MediaLibrarySessionCallback.onRatingTap`
   then runs `RatingResolver` off the main thread: `getSong` on the server, the cached server copy
   (`CachedMusicService.cachedRating`), then the Room row. `PendingRatingTaps` counts the taps made
   in the meantime and the lookup steps by that count. No answer means no write.
4. Refresh on track change: `PlaybackService.onMediaItemTransition` calls `getSong` in the
   background and applies the answer. An answer that comes back after a local rating
   (`QueueRatings.stamp`/`changedSince`) is dropped. No request offline or for a live station.
5. Caches: `Track.toMediaItem` returns a cached item only when the new Track has no rating or the
   same one, and fills a missing rating from the cache. `MediaItemConverter.applyRating(trackId)`
   updates every cache key for the track, `<list>|<id>` included.
6. Room: `CachedMusicService.setRating` (after the server accepted) and `getSong` write the rating
   through to Room.
7. `RatingManager.forgetLast(id)` clears its duplicate check after a rating from elsewhere, so the
   car can send 5 again after the web set 4.

## Cross-App Impact

`services/frontend` and `services/muma-mobile` change together (AGENTS.md rule 7). The web bundle
ships inside the APK, so the release needs an app version bump. No server change: LMS already
answers `getSong`.

## Technical Acceptance Criteria

1. `toQueueTrack` sends the session rating, else the track's rating, else null (vitest).
2. `ratings.js` calls `player.setRating` on a write and on a rollback, and a failing call does not
   stop the server write (vitest).
3. `queueTrackOf` reads 0 to 5 and reads anything else as null (`QueueMarshallingTest`).
4. `ratingAfterTap(null)` is null; `ratingAfterTap(4, taps = 2)` is 0 (`MediaLibraryRatingCycleTest`).
5. `RatingResolver` asks server, cache, Room in that order and treats an exception as no answer
   (`CarRatingTapTest`).
6. A rating-less Track does not replace a rated cached item; `applyRating` reaches composite keys
   (`MediaItemUserRatingTest`).
7. `QueueRatings.applyToQueue` writes every queued copy and reports the playing one
   (`QueueRatingsTest`).
8. `MumaPlayer.setRating` publishes `KnownRating`, stores it, and refuses bad input
   (`MumaPlayerPluginRatingTest`).

## Related Docs

- [ratings-scrobbling](../ratings-scrobbling/) for the rating scale.
- [offline-followups](../offline-followups/technical.md) for the phone's rating queue.
- Issue #256 for the analysis.
