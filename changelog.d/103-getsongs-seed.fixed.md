- **A shuffled preset paged into a new shuffle every 100 tracks** (issue #103). The web's
  `getSongsContinuation` sent the preset's `seed` to `getSongs`, but the LMS fork only read `seed`
  on `getSongsByFilter` and `getSpotifyTracks`; every page of a Random preset was a fresh
  `RANDOM()` draw, so "Meer laden" and the queue top-up repeated tracks (hidden by the dedupe as a
  shorter page) and could skip others. `getSongs` now honours `seed`, which Android Auto's new list
  continuation relies on as well. Additive: a request without `seed` shuffles as before.
<!-- release notes -->
- A shuffled preset no longer repeats tracks when it loads more.
