- **A tap on the car's rating button wrote 1 over the real rating.** A queue from the web player
  had no ratings, the app read the missing rating as 0, and the first tap set 1. On 2026-11-12 a
  track rated 4 got 1 to 5 from the car in one second. The app now keeps "not known" apart from 0,
  asks the server for the rating when a track starts, and on a tap before that it finds the rating
  first (server, the app's cached copy, then the downloaded library). When no source knows it,
  the tap does nothing. Ratings also reach the downloaded library, so offline car lists show the
  last rating (issue #256, `docs/designs/car-rating-state/`).

<!-- release notes -->

- **A tap on the car's rating button no longer resets a rated track to 1 star.** The button starts
  from the track's real rating, also for a queue from the web player.
