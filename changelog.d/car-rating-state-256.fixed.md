- **The web player now tells the phone's player the rating of each queued track.** The queue it
  sends has a `userRating` per track (null when it does not know), and a rating set in the web
  player goes to the phone's player at once with `MumaPlayer.setRating`, without a second write to
  the server. Before, the queue had no ratings, so the car's rating button started at 0 (issue
  #256, `docs/designs/car-rating-state/`).

<!-- release notes -->

- **The car's rating button shows the rating a track has when the web player queued it.**
