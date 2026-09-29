- **LMS no longer crashes when music-manager's hourly lms.db sync runs during a scan.** The scan
  step that updates the genre, mood and festival track counts opened a separate write transaction
  for every cluster and rewrote each one, changed or not. That meant thousands of trips for the
  write lock on every folder scan. When one of those trips landed inside a music-manager sync
  batch, SQLite refused the UPDATE at once, even though LMS is configured to wait 15 s for the
  lock. The error `update "cluster" ...: database is locked` escaped the scanner thread and took
  the whole server down with `std::terminate`. It happened twice in 72 hours, both times inside
  the sync pass. The configured wait was ignored because Wt starts transactions as deferred, and
  SQLite does not wait when a transaction that has already read tries to write. Now every LMS
  write transaction starts with `BEGIN IMMEDIATE`, so it waits for the lock. The step writes only
  the clusters whose counts changed, in one transaction per 100 clusters. A write the database
  still refuses is logged as a WARNING and retried on the next scan; the process keeps running
  (bug report 132).

<!-- release notes -->

- **The music server no longer restarts now and then while new downloads are being scanned in.**
