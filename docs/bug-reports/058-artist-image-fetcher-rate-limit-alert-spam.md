# Artist Image Fetcher Spammed The Alerts Topic Under A Spotify Rate Limit

# status: fixed

# reported problem
On 2026-09-24 production's artist-image run walked every artist without a portrait at roughly one
Spotify lookup per second. Spotify answered `429 Too Many Requests` on about 40% of the lookups.
Each one was logged by the fetcher as

    Provider spotify could not answer for <artist>: Spotify: lookup answered 429

at `WARNING`. Every `WARNING` becomes an event and a push on the `music-management-alerts` ntfy
topic; the 5-minute dedupe on `(level, source, logger)` only thins that out to one push every five
minutes, for as long as the run lasts. The day produced 3,278 of these warnings, 1,650 of them in a
single hour.

The day before, at 11:31, a run of `401` answers showed the Spotify access token expiring mid-run
without being renewed.

# Possible reason
- `SpotifyArtistImageProvider` raised the same `ProviderUnavailable` for every non-200 answer. A
  `429` is about the run, not about the artist, but nothing could tell it apart, and the
  `Retry-After` header Spotify sends with it was never read.
- `ArtistImageFetcher.fetch_for_artist` deferred the artist and the loop moved straight on to the
  next one -- which got the same `429`, because nothing had waited. The run therefore kept Spotify's
  limit tripped and collected one warning per artist.
- Every per-artist non-answer was logged at `WARNING`, and there was no per-run summary, so the only
  way the run could report trouble was once per artist.
- The `401` run was the token-lifetime bug fixed in bug report 043 (renew before `expires_in`, one
  retry after a `401`); production at the time was not yet running that fix.

Not part of this fix, but it inflates the number of lookups: many "artists" in `library_artists` are
song titles or festival-rip fragments that no provider will ever know. That is a curation problem
(which names count as artists), not a fetcher problem, and the list of artists fetched is unchanged
here.

# solution
- `providers/base.py` has a new `ProviderRateLimited(ProviderUnavailable)` carrying `retry_after`.
- `SpotifyArtistImageProvider` raises it for a `429` from both the search/artist lookup and the token
  endpoint. `retry_after` comes from the `Retry-After` header (seconds), falls back to 30 s when the
  header is missing or unreadable, and is bounded to 1 s .. 10 minutes. A `401` still renews the token
  once and retries (bug report 043); a failed renewal is a `ProviderUnavailable`, a rate-limited
  renewal a `ProviderRateLimited`.
- `ArtistImageFetcher` pauses the whole run on a `ProviderRateLimited`: it waits `retry_after` on its
  `stop_event` (a `threading.Event`, so a caller can cut the pause short) and then asks the same
  provider about the same artist once more. Still limited -- or stopped during the pause -- defers the
  artist as before, without a verdict.
- Per-artist non-answers (`429`, `5xx`, connection errors) are logged at `INFO`. A run gets at most two
  `WARNING`s: the first rate limit it hits, and a summary at the end
  (`log_run_summary()`: artists deferred, rate-limit pauses, total pause time). A run without
  deferrals or pauses logs the summary at `INFO`. `run_fetch_missing` in the router and the CLI's
  `fetch-missing` and `refresh` commands bracket their loop with `start_run()` and
  `log_run_summary()`.
- Tests: `artist_image_fetcher/tests/test_providers.py` (429 with and without `Retry-After`, an
  unreadable and a huge header, token-endpoint 429, 401 renewal failing or rate limited, 502 not a
  rate limit), `artist_image_fetcher/tests/test_fetcher.py` (`RateLimitTest`: pause with
  `retry_after`, same artist retried, defer after a second limit or a stop, INFO per artist, single
  summary WARNING, only the first rate limit a WARNING), plus the router and CLI calling the summary.
