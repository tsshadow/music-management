# The lms.db sync gives up on batches while LMS scans

# status: fixed

# reported problem
The events table on production (read-only, 2026-09-29) showed the logger
`services.music_manager.song_version_sync` logging the WARNING
`server-stable: gave up on a batch after 3 locked attempts` 40 times in 24 hours and about 120 times
in 72 hours, spread over nearly every hour of the day -- not only during the long library scan of
2026-09-28 11:41-14:37 UTC. music-manager writes LMS's SQLite database (`lms.db`) directly: the
song-version columns and the form/performance-date columns of `track`, every hour.

Two questions: what holds the lock, and is a batch that is given up lost?

# Possible reason
All measured read-only on production (192.0.2.27) on 2026-09-29.

**LMS's own scanner holds the lock.** `/proc/locks` shows the WAL write lock (byte 120 of
`lms.db-shm`) as a POSIX WRITE lock of the `lms` process, and nobody else's: music-manager does
not even have the file open between passes. Sampled every 5 ms for 30 s during a scan, the lock
was held in 5,853 of 5,855 samples -- runs of up to 19.6 s with a single 10 ms gap. `docker logs lms`
explains the scans: `requested a scan` arrives 3 to 180 times an hour (the downloader and tagger
announcing the folders they wrote, `LmsScanTrigger`), plus the library-wide walk that takes hours.
A scan was running from 11:44 onwards while this was measured.

**It is not music-manager contending with itself.** The hourly sync runs its passes one after
another on one connection under `lms_db_sync_lock`; the other writer (issuing a Subsonic token in
`subsonic_token.py`) is rare, and the scrobble reconcile and lineup readers open the file
read-only.

**Why the old handling failed.** Every batch waited 2 s for the lock (`PRAGMA busy_timeout =
2000`), slept 60 s, and tried three times; the event timestamps show exactly that rhythm (62 s
between the "locked, waiting 60s" lines). Against a scanner that holds the lock for 20 s at a time,
for an hour or more, that fails every time. Each failed batch then cost two minutes of sleep, so a
single pass on 2026-09-29 09:09-09:20 sat on the sync lock for eleven minutes to write nothing, and
each given-up batch was a WARNING -- one alert per batch for an ordinary condition.

**Also:** `_write_batch` lived in `song_version_sync`, and `track_form_sync` borrowed it, so the
track-form push's give-ups were logged under the song-version logger too (three of the five
WARNINGs in the 09:00 hour came from the track-form push).

**Is data lost? No, only delayed.** Both pushes are diff-based: every pass reads the whole library
and writes what LMS disagrees with, so a batch given up is recomputed by the next pass that is not
itself locked. Checked against production: for 516 of 518 sampled files (the scanner's own
`library_media_files` rows, spread over the id range; two were not on the server) LMS's
`work_id`/`version_kind`/`version_score` equal muma's. The pass after the eleven-minute one (10:21)
wrote 24 rows, which included the ones given up. A first sample that looked like drift turned out to
be the stale duplicate rows of bug report 093, which the sync deliberately does not push. So the
WARNING was mis-levelled, and the real cost was latency -- up to an hour, longer when consecutive
passes met a scan -- plus a sync thread parked for minutes at a time.

# solution
music-manager (`services/music_manager/`):

- New `lms_writes.py`, used by both pushes. Every batch opens with `BEGIN IMMEDIATE`, so the write
  lock is taken up front while the connection holds nothing. That is the only shape in which
  SQLite honours the busy timeout (a transaction that reads first and then upgrades is refused at
  once), and because a connection waiting for the lock holds no lock of its own, the timeout is
  raised from 2 s to 10 s at no cost to the player. What stays short is the hold: 100 indexed
  UPDATEs per transaction.
- The first batch that still finds the server busy ends the writing for that pass. It and every
  later batch are kept in a `PendingWrites` -- never dropped -- and the pass finishes its reads and
  returns in seconds instead of sleeping through the scan.
- `routers/users.py` collects those rows per server (`_deferred_writes`) and, after the pass,
  writes exactly those rows again: five tries, five minutes plus up to a minute of jitter apart,
  each on its own short connection. Nothing is re-read. A new pass for a server discards what an
  earlier one deferred, since it recomputes every difference.
- Logging follows what actually happened: each push's INFO summary says how many rows it deferred,
  the retry logs one INFO line when everything landed, and one WARNING per cycle only when rows
  are still unwritten after the last try (LMS genuinely behind, until the next hourly pass). Each
  push now logs under its own logger.
- A transaction the artist-image sync left open after an error is rolled back before the pushes
  start, so it cannot hold LMS's write lock through them.

Tests: `test_lms_writes.py` (two real connections on a WAL file: a held lock defers rows, deferred
rows land once it is free, a lock released within the timeout is waited for, batches stay short),
`test_song_version_sync.py` and `test_track_form_sync.py` (refusals reach the collector, no
WARNING, retry writes them), `test_lms_sync_retry.py` (retry writes the rows, one WARNING when the
server stays busy, jitter bound, a vanished server, a new pass resets the list, open transaction
rolled back).

Left open: the LMS scanner itself holds the write lock for runs of 20 s, which is also what makes
LMS's own rating/scrobble requests fail during a scan (GitLab issue #133). Post-deploy check: GitLab issue #134.
