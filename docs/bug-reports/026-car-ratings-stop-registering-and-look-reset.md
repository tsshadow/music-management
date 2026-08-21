# Ratings Given In The Car Stop Registering And Look Reset Later

# status: fixed

# reported problem
Rating from the car over Android Auto does not seem to work. A handful of tracks were rated over
the past few days; the ratings now look reset. Reported 2026-08-21.

# Possible reason
The push side is healthy. LMS's `MusicManagementBackend::onRatingChanged` fired for every rating
made on 2026-08-21 and each one reached `POST /api/rating/lms-event` with `200 OK`, so a rating
that gets as far as the server is stored and mirrored. Whether any older row was deleted on the
server could not be checked: read-only access to prod's LMS database was refused in that session,
and both containers had been recreated that day, so their logs hold no history of the days in
question. Two defects in the app account for the report on their own.

**1. The rating a tap cycles on from goes stale.** This is the tail of
[024](024-android-auto-rating-button-always-sets-one-star.md). That fix made
`MediaItem.setUserRating` write the new rating to the cached `Track` *and* to the item's metadata
extras, so an expired cache entry would rebuild with the current rating. But the items the player
and the car's browse tree actually carry come from `buildMediaItem`, which also stamps the rating
into the metadata as a `StarRating` — and `MediaMetadata` is immutable, so `setUserRating` can
never reach that third copy. `toTrack()` read the extras first and then let the frozen `StarRating`
overwrite them, which put the rebuild right back where 024 started.

`MediaItemConverter`'s track cache expires after ten minutes and holds only 250 entries, so in a
car queue the rebuild happens constantly. `MediaLibrarySessionCallback.onCustomCommand` then draws
the next rating from a stale number:

- a track at 3 rated to 4 in the car recomputes 4 on the next tap, and `RatingManager.submitRating`
  drops it — "Don't submit the same rating twice" — so the button appears dead;
- an unrated track rebuilds as unrated (`StarRating(MAX_STARS)`, `isRated` false → 0), so every tap
  re-sends 1;
- a track at 5 wraps back to 0, clearing the rating that was just given.

**2. A rating is never written back into the app's own caches.**
`CachedMusicService.setRating` forwarded the call to the server and did nothing else. The copies the
app answers from — `cachedMusicDirectories`, `cachedAlbum`, `cachedHomeLists`, and
`MediaItemConverter`'s two caches — keep the rating they were fetched with until they expire. A
track rated in the car therefore shows its old rating everywhere else, which is what "the ratings
look reset" describes.

# solution
- `MediaItemConverter.toTrack` only falls back to the metadata `StarRating` when the extras carry no
  `userRating` of their own, so the copy that `setUserRating` keeps current is the one a rebuild
  reads. Items built without an extras entry (folder rows in the car's browse tree, anything from
  `buildMediaItem` that was never rated through the app) are unaffected.
- `CachedMusicService.setRating` corrects every cached copy of the track after the server call, via
  the new `applyRatingToCachedTracks`, and calls `MediaItemConverter.applyRating` to update the
  cached `Track` and drop the cached `MediaItem` — the item cannot be corrected in place, so it is
  rebuilt with the new rating instead.
- `LRUCache` grew `values()` and `remove(key)`: the caches above are keyed by directory or album id,
  and a rating change has to reach whichever of them holds the track without knowing those keys.

# tests
- `MediaItemUserRatingTest` — a raised rating and a first rating both survive a cleared (expired)
  track cache on an item built the way the player builds one. Both fail against the old code, with
  the item handing back the rating it was built with. Two further cases pin the fallback that has to
  keep working: an item with no extras of its own still reports the rating stamped into its
  metadata. Three more cover `MediaItemConverter.applyRating`.
- `CachedRatingTest` — `applyRatingToCachedTracks` reaches a track inside a cached directory and
  inside a nested home list, leaves other tracks alone, and writes a cleared rating as none. The
  function is tested on its own because constructing `CachedMusicService` needs a real Room database
  through `ActiveServerProvider`, the same reason `artistsCacheBypassesFor` sits beside it.
- `LRUCacheTest` — `values()` returns the live entries and nothing after a clear; `remove` drops
  only the entry it names.
- Full module suite: `./scripts/test/muma-mobile-unit.sh`'s task
  (`:core:voice:test :app:jacocoTestReport`) — green.
