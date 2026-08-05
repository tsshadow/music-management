# The Android Auto Rating Button Always Sets One Star

# status: fixed

# reported problem
In Android Auto the rating button only ever gives one star. A track rated 5 drops to 1, a track
rated 1 stays at 1, and an unrated track becomes 1. No other rating can be reached from the car.

# Possible reason
Not a server problem, and not the rating pipeline: LMS keeps `star`/`unstar` and `setRating`
separate (`MediaAnnotation.cpp`), and nothing in the app, `music_manager` or the web frontend
turns a favourite into a rating.

The car button is built once per rating (`MediaLibraryCommandHandler.getRatingCommandButton`) and
carries the rating it was drawn with in its `SessionCommand` extras, under
`PlaybackService.EXTRA_CURRENT_RATING`. `MediaLibrarySessionCallback.onCustomCommand` read the
current rating out of `customCommand.customExtras` and cycled on from there.

Those extras never arrive when the tap comes from Android Auto:

1. media3 does copy them outbound — `PlayerWrapper` puts `SessionCommand.customExtras` into the
   legacy `PlaybackStateCompat.CustomAction`, so the car does receive them.
2. On the way back, `MediaSessionLegacyStub.onCustomAction(action, extras)` builds a *fresh*
   `SessionCommand(action, Bundle.EMPTY)` and forwards the received bundle as the separate `args`
   parameter (verified in the media3-session 1.4.1 bytecode). `MediaControllerCompat` only ever
   sends the bundle its caller passed, not the custom action's own extras.

So `customExtras` was empty for every tap made in the car and `getInt(EXTRA_CURRENT_RATING, 0)`
fell back to its default of 0 — every tap cycled 0 → 1, whatever the track was rated. Phone-side
controllers, which are native media3 controllers and do keep `customExtras`, were never affected,
which is why this only showed up in the car.

A second, slower version of the same problem sat behind it: the rating was recorded only on the
cached `Track` (`mediaItem.toTrack().userRating = ...`). `MediaItemConverter`'s track cache expires
after ten minutes, after which `toTrack()` rebuilds from the item's metadata extras and hands back
the rating the item was built with.

# solution
Read the rating from the playing track — which is what the button was drawn from — instead of from
extras that do not survive the trip.

- `MediaLibraryCommandHandler.ratingAfterTap(trackRating, extrasRating)` picks the source: the
  track first, the extras only as a fallback for controllers that do pass them back and for taps
  arriving while no track is loaded.
- `MediaLibrarySessionCallback.onCustomCommand` calls it with
  `session.player.currentMediaItem?.toTrack()?.userRating`, and now also looks in `args` (where a
  legacy controller's bundle actually lands) before `customExtras`.
- `MediaItem.setUserRating` (new, in `MediaItemConverter`) writes the rating to both the cached
  `Track` and the item's metadata extras, so an expired cache entry rebuilds with the current
  rating rather than the original one.
- `onSetRating` refreshes the car's button whenever a star rating is set, so a rating given on the
  phone leaves the car showing the same number.

# tests
- `MediaLibraryRatingCycleTest` — the rating a tap moves to, covering the car's case (no extras):
  5 → 0, 1 → 2, unrated → 1, the track winning over stale extras, and the extras-only fallback.
- `MediaItemUserRatingTest` — a rating set on an item survives a cleared (expired) track cache,
  for both a set and a cleared rating. Both of those fail against the old single-write code.
- Full module suite: `./gradlew :ultrasonic:jacocoTestReport` (the CI job's task) — green.
