- **The app opens on its home screen without waiting for the queue** (issue #113). The bundled web
  UI no longer holds the boot screen until every queued track has been looked up: the mini player
  shows "Wachtrij wordt hersteld…" with a spinner and fills in when the restore is done. Starting a
  track before then cancels the restore, and `PlaybackService` is never sent an empty or half-built
  queue in the meantime -- what was playing keeps playing.

<!-- release notes -->

- **The app opens faster.** The home screen appears straight away and the mini player fills in
  once the queue is restored; starting something else meanwhile wins.
