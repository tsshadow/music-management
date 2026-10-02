- **The app shows its home screen before the queue is restored** (issue #113). Inside the Android
  shell the web UI used to wait on the boot screen for one `getSong` per queued track (up to 200)
  before it mounted. It now mounts as soon as the server and session are known; the mini player
  says "Wachtrij wordt hersteld…" with a spinner and fills in when the restore finishes. A track
  started before then cancels the restore, so a late answer never replaces it; "add to queue"
  meanwhile keeps its tracks behind the restored ones. Nothing is pushed to the player service
  while the restore runs -- not the empty queue the UI starts with, not yesterday's queue from
  `localStorage` -- and a restore that finishes goes across paused, as before. LMS has no endpoint
  that resolves a list of track ids (`getSongs` filters by cluster, artist, work and form), so the
  lookups themselves are unchanged; they just no longer hold the first paint back.

<!-- release notes -->

- **The app opens faster.** The home screen appears straight away; the mini player shows that the
  queue is being restored and fills in when it is ready. Starting something else meanwhile wins.
