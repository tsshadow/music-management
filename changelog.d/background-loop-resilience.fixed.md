- **One MariaDB restart or CIFS hiccup stopped the tagger or the scanner until the next deploy.**
  Their loops had nothing around the loop body, and the radio, news and feeds loops took their
  connection outside their `try`. Every background loop now runs through one helper that logs the
  failure as an `ERROR` event, backs off (10 s, doubling up to the loop's interval) and carries on.
  Each loop also records a heartbeat, and `/health` answers 503 when a loop is alive but has not
  completed a round within its window (24 h tagger, 12 h scanner, 3 h news, otherwise three
  intervals and at least an hour); the new `heartbeats` field shows the detail.
- **`/health` said `database: ok` while MariaDB was down, and hung when the pool was exhausted.**
  It now runs `SELECT 1` on its own connection with short timeouts and answers within about two
  seconds. The connection pool no longer waits forever: after 5 s (`DB_POOL_WAIT_SECONDS`) a request
  gets a 503 instead of hanging.
- **During a database outage an alert push waited ~21 s per queued event before reaching the
  phone.** The event log's database write now runs on its own thread, so pushes go out immediately
  and only the rows are late. The 5-minute repeat brake still applies.

<!-- release notes -->

- **Background jobs (tagging, scanning, radio, news, feeds) now survive a database restart**
  instead of stopping until the next deploy, and the health check notices when one of them stalls.
- **The health check tells the truth about the database** and always answers within seconds.
- **Alerts reach the phone immediately during a database outage.**
