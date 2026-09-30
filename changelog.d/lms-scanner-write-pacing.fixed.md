- **A write-heavy LMS scan no longer locks every other writer out of lms.db.** The scanner commits
  in small batches, but it started the next transaction as soon as the previous one committed. The
  lock was free for microseconds at a time. music-manager's hourly sync, which sleeps up to 100 ms
  between attempts at the lock, never got in and gave up after 10 s. Measured locally against a
  bulk writer with music-manager's settings, the result was `database is locked` after the full
  10 s in every case. After 0.5 s of writing the scanner now waits 120 ms without the lock. The
  same measurement gets the lock in 3 to 231 ms. A scan that paused says so in the log after its
  summary. A scan-files transaction also commits once it has run for 250 ms, and the WAL file is
  truncated back to 64 MB after each reset instead of staying at its high-water mark (1.09 GB on
  production). The 20 s runs measured on production on 2026-09-29 came mostly from the
  per-cluster transactions fixed in 0.83.0. On 0.85.0 the lock was held in 2 of 38,528 samples
  across three scoped scans (bug report 134).
- **A locked database no longer takes LMS down from a podcast refresh or a ListenBrainz sync.**
  These background writes ran on a thread that logs FATAL and aborts the process on any exception.
  None of them caught a write the database refused after its 15 s wait. A refused write is now
  logged as a WARNING and retried on the next round. A podcast refresh ended this way no longer
  stops refreshes for good (bug report 135).

<!-- release notes -->

- **Ratings and the hourly sync no longer wait for a big library scan to finish.**
- **A busy database no longer restarts the music server from the podcast or ListenBrainz
  features.**
