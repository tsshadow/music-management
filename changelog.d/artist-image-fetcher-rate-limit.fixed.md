- **A Spotify rate limit during the artist-image run pushed an alert every five minutes for the whole
  run.** Spotify answered `429` on about 40% of the lookups, and the fetcher logged each one as a
  `WARNING` and went straight on to the next artist, which kept the limit tripped: 3,278 warnings on
  2026-09-24, 1,650 in one hour. The Spotify provider now reads `Retry-After` (default 30 s, capped at
  10 minutes) on the lookup and the token endpoint, and the fetcher pauses the whole run for that long
  and asks about the same artist once more before deferring it. Per-artist non-answers are `INFO`; a
  run logs at most two `WARNING`s, the first rate limit and a closing summary (artists deferred,
  pauses, total pause time). Bug report 057.

<!-- release notes -->

- **The artist-image run no longer sends an alert every five minutes when Spotify slows it down.** It
  now waits as long as Spotify asks and reports once at the end of the run.
