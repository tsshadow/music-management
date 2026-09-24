# Artist Image Fetcher Still Pushed Alerts Per Artist For MusicBrainz And Download Failures

# status: fixed

# reported problem
Bug report 058 stopped the artist-image run from pushing an alert every five minutes under a
Spotify rate limit. The rest of the pipeline kept the old habit of logging each artist's trouble at
`WARNING` or `ERROR`, and every one of those becomes an event and a push on the
`music-management-alerts` ntfy topic (deduped only on `(level, source, logger)` per five minutes):

- `providers/musicbrainz.py` logged every timed-out attempt at `WARNING`, a final timeout at
  `WARNING` again, and any other failure at `ERROR` -- per artist. musicbrainz.org is routinely slow
  (see the timeout comment in the provider), so a long run pushed for as long as it lasted.
- `storage.py` logged every image-download retry at `WARNING` and every failed save at `ERROR`, and
  the fetcher logged the same failed save at `ERROR` a second time -- per artist.
- A MusicBrainz `429`, or the `503` it documents as its own rate-limit answer, was treated as "no
  metadata" and the run walked straight into the next artist, keeping the limit tripped.
- The fetcher logged "No image provider configured" at `WARNING` per artist, and a provider that
  raised an unexpected exception at `ERROR` per artist; the router logged each artist whose fetch
  raised at `ERROR`.

# Possible reason
!944 (bug report 058) introduced the per-run discipline -- `INFO` per artist, a counted summary at
the end -- only on the Spotify path. MusicBrainz was never a candidate provider (it supplies
metadata, not images) and was called outside the provider loop, and the download/save path sat after
it; neither was brought under the new counters.

# solution
- `MusicBrainzArtistProvider.get_artist_metadata` now follows the provider contract in
  `providers/base.py`: `None` means it looked and found nothing (no hit, a `404` for an unknown MBID),
  `ProviderUnavailable` means it could not answer (timeout after every attempt, transport error, `5xx`,
  unreadable body), and `ProviderRateLimited` is raised for a `429` or a `503` with `Retry-After`,
  bounded like Spotify's (default 30 s, capped at 10 minutes). The per-attempt timeout line is `INFO`.
  The `Retry-After` parsing moved to `parse_retry_after()` in `providers/base.py`, shared with Spotify.
- `ArtistImageFetcher` asks MusicBrainz through the same rate-limit pause as the image providers; a
  non-answer is `INFO` and the lookup goes on by name, without the external ids.
- `start_run()` has two new counters: `provider_failures` (per provider, MusicBrainz included) and
  `download_failures`. `log_run_summary()` reports both and returns them; the summary is a `WARNING`
  when artists were deferred, the run paused, or a download failed, `INFO` otherwise -- still one per
  run.
- `ImageDownloader` logs each failed attempt at `INFO`; `ImageStorage.save_image` raises without
  logging. The fetcher logs a failed download or save at `INFO` and counts it. An image directory that
  cannot be written (`EACCES`, `EPERM`, `EROFS`, `ENOSPC`, `EDQUOT`) is the one genuine `ERROR`,
  logged once per run.
- The blind-fetcher skip and a provider that blew up are `INFO` (the latter counted per provider);
  the router logs only the first artist whose fetch raised at `ERROR`, the rest at `INFO`, and puts
  deferred artists, failed downloads and errors in the completion message and the completion
  event's context. The CLI's `fetch-missing` and `refresh` still end with `log_run_summary()`, whose
  line carries the new counters.
- Tests: `artist_image_fetcher/tests/test_providers.py` (MusicBrainz timeout attempts at `INFO`,
  persistent timeout / transport error / unreadable body / bare `503` are `ProviderUnavailable`, `404`
  is `None`, `429` and `503` with `Retry-After` are `ProviderRateLimited`, huge header capped),
  `test_storage.py` (retry at `INFO`, save raises without logging), `test_fetcher.py`
  (`QuietFailureTest`: MusicBrainz non-answer counted and `INFO`, MusicBrainz rate limit pauses the
  run, download failures in the summary, unwritable directory one `ERROR` per run), and
  `services/music_manager/tests/test_artist_images_router.py` (counters in the completion message,
  only the first raising artist an `ERROR`).
