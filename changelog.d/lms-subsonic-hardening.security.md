- **Any logged-in user could crash the music server with one settings request.** `updateUser`
  stored any integer as the feedback or scrobbling backend, and the next rating or listen looked
  up a backend that did not exist and dereferenced a null pointer -- a segfault for everyone.
  Every enum setting is now range-checked (an unknown value is a bad-parameter error and nothing is
  written), and both services look a backend up without inserting into the map the request
  threads share. Subsonic tokens are unique per domain (migration V121 removes values two users
  shared, so both re-issue) and must be at least 16 characters. Bug report 044.
- **`getSpotifyTracks`, `getSpotifyPlaylist` and `getSpotifyHistory` no longer walk the whole
  library.** A negative `offset`/`count` is refused and `count` is capped at 1000, so `count=-1`
  no longer means "everything".
- **A 429 from MuMa no longer freezes the queue to MuMa.** A proxied call gets the 429 as its
  answer, other requests are retried three times and then failed, and the queue is capped at 1000
  waiting requests.
<!-- release notes -->
- **Fixed a settings request that let any user crash the music server.**
- **Fixed three smaller holes in the server:** unbounded page sizes, a queue that a busy MuMa could
  freeze, and Subsonic tokens that two users could share.
