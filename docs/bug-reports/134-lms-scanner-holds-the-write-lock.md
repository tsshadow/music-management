# The LMS scanner keeps the lms.db write lock to itself while it writes

# status: fixed

# reported problem
GitLab issue #133, found while analysing bug report 129. On 2026-09-29, during a scan that
started at 11:44 UTC, `/proc/locks` on production was sampled read-only every 5 ms for 30 s. The
WAL write lock of `lms.db` (byte 120 of `lms.db-shm`) was held by the `lms` process in 5,853 of
5,855 samples. The runs lasted up to 19.6 s, with a single gap of about 10 ms. Scans are requested
3 to 180 times an hour. Every other writer starved or waited:
- music-manager's hourly lms-db-sync gives up on a row after its 10 s busy timeout and defers it
  (bug report 129).
- LMS's own rating and scrobble writes wait under `BEGIN IMMEDIATE`, up to 15 s.
- The listen outbox waits too.

The WAL file next to the database was also noted at 800 MB, as large as the database itself. It
was 1.09 GB on 2026-09-30, against an 807 MB database.

# Possible reason
Two things add up.

1. **The measured runs were mostly the cluster-count step from before 0.83.0.** Production ran
   0.82.x at 11:44 on 2026-09-29. 0.83.0, which carries bug report 132, reached master at 16:30.
   In 0.82.x, `ScanStepComputeClusterStats` opened one write transaction per cluster, on every
   scan with a change. That is thousands of back-to-back transactions. Measured again on
   2026-09-30 on 0.85.0, with the same sampler, over three scoped scans (one or two changed files
   each, about 49 s per scan), the lock was held in 2 of 38,528 samples. The 49 s of a scoped scan
   is spent reading.
2. **Short transactions are not enough on their own.** Every scan step commits in bounded batches
   (`ScanStepScanFiles` takes 10 file results per transaction, the image and orphan steps 50 to
   200 rows). But each step starts the next transaction straight after committing the last. The
   lock is free for microseconds between two of them. A connection waiting on SQLite's busy
   handler sleeps up to 100 ms between attempts, so it practically never lands in such a gap. This
   is still the shape of any scan that writes a lot: a retag wave, a new batch of downloads, a
   library-wide scan after a rename. Measured locally with a bulk writer running back-to-back
   transactions of 2, 10 or 30 ms, a second connection with music-manager's 10 s busy timeout got
   `SQLITE_BUSY` after the full 10 s in every case. The in-process write mutex hands over
   better (36 to 79 ms), but nothing guarantees that.

On the WAL size: SQLite never shrinks the WAL file by itself. After a checkpoint it rewinds to the
start of the file, but the file keeps the size of the longest stretch that ever had to be held
without a checkpoint getting through. `journal_size_limit` was not set.

# solution
- **A write pacer for the scanner thread** (`db::WritePacer`, installed on the scanner's session
  in `ScannerService::scan`). `WriteTransaction` reports each outermost write transaction to it,
  before taking the write mutex and after releasing it. Once the scanner has written for 500 ms
  without a gap of at least 120 ms, the next write transaction first sleeps 120 ms without the
  lock. 120 ms is longer than the busy handler's longest sleep, so a waiting connection always
  gets an attempt inside the gap. The in-process write mutex hands over at once. Measured with the
  same harness, the foreign connection now gets the lock within 3 to 231 ms, where it used to time
  out after 10 s. A scan that pauses logs "Scan released the write lock to other writers N
  time(s), X ms in total" after its summary.
- **Time-bounded batches in `ScanStepScanFiles`.** A transaction still takes up to 10 file results,
  and now also commits once it has run for 250 ms.
- **`PRAGMA journal_size_limit=67108864`** on every LMS connection. The WAL file is truncated back
  to 64 MB whenever the log is reset. Checkpointing itself is unchanged.

Tests: `src/libs/database/test/WritePacer.cpp` covers the pacer logic with an injected clock. It
also checks that a raw SQLite connection, and another LMS thread, get the write lock within 1.5 s
while a paced bulk writer runs.

Not verified yet: a write-heavy scan on production with the pacer in place. The check is to re-run
the `/proc/locks` sampler during one and look for gaps of at least 120 ms at least every ~0.6 s.
This is tracked as GitLab issue #143. Design:
[docs/designs/lms-scanner-write-pacing/](../designs/lms-scanner-write-pacing/).
