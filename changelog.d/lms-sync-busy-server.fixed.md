- **The hourly lms.db sync no longer raises a WARNING per batch while LMS scans.** LMS's scanner
  holds its database's write lock for runs of up to twenty seconds, for as long as a scan lasts --
  and folder scans after downloads arrive up to 180 times an hour. The song-version and track-form
  pushes waited two seconds, slept a minute, tried three times per batch and then dropped the batch
  with `gave up on a batch after 3 locked attempts`: 40 WARNINGs a day, one pass parked for eleven
  minutes, and the track-form push's refusals logged under the song-version logger. Nothing was
  actually lost (the next pass rewrote the same rows; a production sample of 516 files matched),
  only delayed. Now each batch takes the lock up front (`BEGIN IMMEDIATE`, 10 s wait, still 100
  UPDATEs per transaction), the first refusal defers the pass's remaining rows instead of sleeping,
  and those exact rows are written again five minutes later, up to five times. One WARNING per hour
  remains, and only when rows are still unwritten after half an hour (bug report 129).

<!-- release notes -->

- **Grouped song versions reach the player within minutes even while it scans**, and the alerts
  topic no longer fires dozens of times a day about it.
