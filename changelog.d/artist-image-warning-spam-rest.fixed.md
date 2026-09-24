- **MusicBrainz timeouts and failed portrait downloads still pushed an alert per artist during the
  artist-image run.** Bug report 058 fixed the Spotify path only: the MusicBrainz provider logged every
  timed-out attempt as a `WARNING`, image-download retries were `WARNING`s and a failed save an `ERROR`
  (logged twice), each one a push on the alerts topic. These are now `INFO` and counted into the run's
  single summary, which reports failed downloads and non-answers per provider. A MusicBrainz `429`, or
  a `503` with `Retry-After`, pauses the run the way a Spotify `429` does. The only `ERROR` left is an
  image directory that cannot be written, once per run. Bug report 060.

<!-- release notes -->

- **The artist-image run no longer sends an alert per artist when MusicBrainz is slow or a portrait
  download fails.** It reports those once, in the summary at the end of the run.
