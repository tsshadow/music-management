# Background Loops Died On One Exception, /health Lied About The Database, Alerts Waited On The Write

# status: fixed

# reported problem
A reliability review of `music-manager` found three defects that each let the service look fine
while it had stopped doing its work:

- **Background loops died for good.** `run_tagger_loop` and `run_scanner_loop` had nothing around
  their loop body. `run_full`, `Tagger.run`, `reload_rule_caches`, `get_db_connection` and
  `_scan_recursive` all raise on a MariaDB restart or a CIFS hiccup, so one such moment ended the
  loop for the lifetime of the process. `run_radio_scheduler`, `run_feeds_refresh` and
  `run_news_recorder` called `get_db_connection()` outside their `try`, and in the news recorder
  `_mark_source` inside the `except` could raise as well. `/health` only checked `is_alive()`, so a
  loop that was alive but stuck looked healthy.
- **`/health` reported `database: ok` while MariaDB was down, and could hang.** It took a pooled
  connection and ran no query. DBUtils (`ping=4`) pings a cached connection only when a query runs,
  so a dead cached connection counted as `ok`. The pool was `blocking=True` without a timeout, so an
  exhausted pool made `pool.connection()` — and with it `/health` — wait forever. Its docstring
  claimed the pool raised in that case.
- **Alert pushes waited behind the database write.** The single `EventService` worker wrote each
  event to MariaDB first (fresh connection, retries of 1 + 4 + 16 s) and dispatched to the ntfy sink
  only afterwards. During a database outage every queued event cost ~21 s before its push, so a
  `CRITICAL` behind N events reached the phone N x 21 s late — during exactly the outage it was
  about.

# Possible reason
Every loop was its own hand-written `while True`, and each one decided for itself what to catch.
The ones written later (events-retention, scrobble-rematch, song-versions, lms-db-sync) caught
everything; the older ones did not. Liveness was the only health signal, which a stuck or
backing-off loop still passes. The health check measured "the pool handed out a connection" rather
than "MariaDB answered", and the pool had no bounded wait at all. In `EventService` the database
write and the sink dispatch were two sequential steps on one thread, so the sink inherited the
write's retries.

# solution
- `thread_registry.run_forever(name, tick, interval, stale_after=..., backoff=True)` is now the one
  loop implementation. Each tick runs inside a catch-all that logs with `logger.exception` (logger
  `music-manager.threads`, so the failure reaches the events pipeline as an `ERROR`), then backs off
  10 s, doubling up to the loop's normal interval, and carries on. `KeyboardInterrupt`/`SystemExit`
  still end it. The tagger, scanner, radio, news, feeds-refresh and events-retention loops use it
  with backoff; scrobble-rematch, song-versions and lms-db-sync use it with `backoff=False`, which
  keeps their old behaviour of waiting the full interval after a failure. A tick may return its own
  next sleep, which the news recorder uses for its schedule.
- Every completed tick records a heartbeat. `thread_status()` reports a loop healthy only when its
  thread is alive *and* its heartbeat is younger than its `stale_after`; `thread_heartbeats()`
  carries the detail and `/health` returns it under `heartbeats`. The window counts from
  registration, so `/health` is green right after startup. Windows: three intervals with a one-hour
  floor by default; tagger 24 h (a round may include the daily walk), scanner 12 h (a full scan over
  CIFS), news 3 h (it sleeps up to an hour inside its tick).
- `/health` runs `SELECT 1` on its own short-lived connection (`database.check_database`, 1 s
  connect/read/write timeouts), on a two-worker executor with a 2 s deadline, so it answers within
  about two seconds whatever MariaDB or the pool is doing, and reports `database: unreachable` on any
  failure.
- The pool is now `blocking=False`; `get_db_connection` retries for at most `DB_POOL_WAIT_SECONDS`
  (default 5) and then raises `DatabaseBusyError`, which a FastAPI exception handler turns into a
  503 with `Retry-After: 5`.
- `EventService` hands each event to a separate writer thread with its own queue and dispatches to
  the sinks straight away. A database outage delays rows, not pushes; the ntfy 5-minute dedupe brake
  is unchanged. `is_alive()` now requires both threads. The writer keeps its own un-pooled
  connection because the module also runs in the downloader and importer, and the event log has to
  keep working when the API's pool is exhausted.
