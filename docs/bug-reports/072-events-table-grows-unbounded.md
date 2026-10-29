# The events table grew to 17.5 million rows while retention reported healthy

# status: fixed

# reported problem

On 2026-09-25 the `events` table on production held about 17.5 million rows and 6.9 GB of data
(`information_schema.TABLES`: `TABLE_ROWS`, `DATA_LENGTH`), with indexes on `created_at`,
`(level, created_at)` and `(source, created_at)`. `/health` reported the `events-retention`
thread as healthy the whole time. The day before, one loop had written 3,278 artist-image
WARNINGs, and the tagger and scanner log at INFO, so the question was whether retention deleted
anything at all and whether it could keep up.

# Possible reason

## What the old retention did

`services/music_manager/events_retention.py` ran once at startup and then every 24 hours:

```python
RETENTION_DAYS = {'INFO': 14, 'WARNING': 60, 'ERROR': 365, 'CRITICAL': 365}
DELETE FROM events WHERE level = %s AND created_at < DATE_SUB(NOW(), INTERVAL %s DAY) LIMIT 10000
```

It repeated that statement per level until a batch came back short, committing after each one. So
it did delete, per level, in batches. What it lacked:

- no window for `DEBUG`, so a DEBUG row would never have gone (none exist today);
- no size cap, so the table size was whatever volume × window came to;
- no time bound and no pause between batches: a pass ran until nothing was left, however long
  that took;
- no per-statement timeout, and a range condition on the secondary index, which takes next-key
  locks on that index range rather than only on the deleted rows;
- no log line, so neither `/health` nor the event log showed whether it removed anything.

## What production measured (read-only, 2026-09-25)

Retention was keeping up with its own windows:

| level   | oldest row           | window  |
|---------|----------------------|---------|
| INFO    | 2026-09-11 05:42     | 14 days: exactly on the edge |
| WARNING | 2026-08-07 08:01     | 60 days: nothing old enough to delete yet |
| ERROR   | 2026-08-07 08:01     | 365 days |

The oldest row in the table is from 2026-08-07, when the events table was introduced. Before
2026-09-10 the table held 13,029,852 WARNINGs, 43,522 ERRORs and no INFO at all.

The volume was the problem. WARNINGs per day, second half of September:

| day        | WARNING |
|------------|--------:|
| 2026-09-10 | 178,572 |
| 2026-09-15 | 224,521 |
| 2026-09-18 |  74,672 |
| 2026-09-20 | 255,958 |
| 2026-09-22 | 300,357 |
| 2026-09-23 | 331,700 |
| 2026-09-24 | 820,927 |

On 2026-09-24 the table took 899,751 events: 820,927 WARNING, 56,155 INFO, 22,669 ERROR. The top
`(level, source, logger)` was `WARNING / importer / root` with 793,644 rows, 97 % of all
WARNINGs. On 2026-08-20 it was the same source, 186,002 of about 195,000 WARNINGs. A 10-minute
sample of it: 7,195 of 10,725 were `CAT ID <x> not found in database for folder <folder>` and most
of the rest `No valid CAT ID found for folder: <folder>` (both `services/importer/mover.py`),
each folder repeated every ~6-minute import cycle. The importer's own summary shows why: 6,462
unplaceable folders were re-resolved, and re-warned, on every cycle.

The artist-image fetcher (6,852 WARNINGs that day), the tagger (948 INFO) and the scanner (909
INFO) are small next to that.

## Verdict

Retention deleted, and its batched `DELETE` kept up with its windows. But the windows had been
sized for a trickle, not for ~380,000 WARNINGs a day. A 60-day WARNING window over that volume holds
about 23 million rows, and nothing capped it. The table was on its way there: 49 days in, it held
17.5 million, and not one WARNING was old enough to delete. `/health` could not show any of this,
because a thread that deletes nothing is still alive and still beats.

The flood itself was fixed separately by `c6e1faf08` ("stop re-reading unchanged __TODO folders
every cycle", released in 0.73.1). From the first cycle after that deploy (2026-09-25 05:29) the
importer logs `6462 checked, 6462 skipped as unchanged, 0 re-read`, and its WARNINGs fell from
~50,000 an hour to 212 in the 06:00 hour. In the first 50 minutes after the deploy the whole table
took about 6,800 events: INFO ~4,200 (downloader and importer), WARNING ~1,400, ERROR ~1,000. The
largest remaining sources are both in the downloader. One is yt-dlp's per-video ERROR `Sign in to
confirm you're not a bot` (21,880 on 2026-09-24). The other is its WARNING `No title found in
player responses` (976 in those 50 minutes). Both are WARNING or higher, so they stay in the table
by the AGENTS.md promise; no logger level was lowered in this change.

# solution

`events_retention.py` was rewritten:

- **Per-level windows, configurable.** `DEBUG` 3 days, `INFO` 14, `WARNING` 30, `ERROR` 90,
  `CRITICAL` 365, set as `events_retention_<level>_days` in the config schema (Beheer config page,
  group *Events*). 0 or empty falls back to the default. WARNING went from 60 to 30 and ERROR from
  365 to 90 because those levels, not INFO, carry the volume. At the post-fix rates above the table
  settles around 5–6 million rows (INFO ~1.7 M, WARNING ~1.2 M, ERROR ~2.6 M).
- **Primary-key batches.** Per level, up to 10,000 ids are picked through the
  `(level, created_at)` index, oldest first, and deleted with `DELETE ... WHERE id IN (...)`. Only
  those rows are locked, never an index range that inserts also write to. Each `DELETE` runs under
  `SET STATEMENT max_statement_time=30`, and there is a 0.2 s pause between full batches.
- **A hard bound.** A pass stops after 300 seconds, whatever is left. `retention_tick` then asks
  `run_forever` for the next pass in one hour instead of 24, so a backlog is worked off in hourly
  passes. The first pass after this deploy has about 7 million WARNINGs from before 2026-08-26 to
  remove.
- **A size safety net.** If the table still holds more than `events_max_rows` (default
  10,000,000) after the age pass, the oldest `DEBUG`, then `INFO`, `WARNING` and `ERROR` rows go
  until it is back under. `CRITICAL` is never removed by size. The trigger reads InnoDB's free
  `TABLE_ROWS` estimate and counts exactly only when that estimate is over the cap: right after a
  mass delete the estimate still includes the removed rows, and acting on it would over-delete. A
  pass that needed the cap logs a `WARNING`, because that means something writes far more than the
  windows were sized for.
- **One summary per pass** at INFO on `music-manager.events-retention`, e.g. `Events retention:
  removed 71234 row(s) in 12.3s; by age: INFO 60012, WARNING 11222; done`. A pass cut short ends
  in `stopped at the 300s bound, next pass in 1h`.

Not done on purpose: an automatic `OPTIMIZE TABLE`. InnoDB keeps the freed pages inside
`events.ibd`, so the file stays at ~7 GB after the clean-up. A rebuild copies the whole table and
needs that much free disk. A person runs it once retention has caught up, see
`muma-ops docs/deployment-production.md`, "Reclaiming space in the events table". It is listed under "Needs a person"
in the GitLab issues.

Tests: `services/music_manager/tests/test_events_retention.py` runs the pass against an in-memory
table. It checks the per-level windows, the primary-key batches with pauses, the stop at the time
bound, the size cap (oldest noise first, never CRITICAL, exact count before acting on a stale
estimate) and the single summary line. `tests/integration/test_router_sql.py::EventsRetentionSqlTest`
runs the same SQL against MariaDB.
