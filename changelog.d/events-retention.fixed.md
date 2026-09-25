- **The event log no longer grows to tens of millions of rows.** On production the `events` table
  held 17.5 million rows (6.9 GB). Retention did run, but a 60-day WARNING window kept everything
  the importer wrote: about 380,000 WARNINGs a day since August, peaking at 821,000 on 2026-09-24.
  They were one warning per unplaceable folder per cycle, fixed separately in 0.73.1. Retention now
  keeps DEBUG 3 days, INFO 14, WARNING 30, ERROR 90 and CRITICAL 365, each configurable on the
  Beheer config page (group *Events*). It deletes at most 10k rows per statement by primary key
  and stops after 5 minutes, coming back after an hour instead of a day until the backlog is gone.
  A new size cap, `events_max_rows` (default 10 million), removes the oldest non-CRITICAL rows if
  the table is still too big. Each pass writes one summary line to the event log. The disk space
  InnoDB keeps after the clean-up is reclaimed by hand, see bug report 072 and
  `docs/deployment.md`, "Reclaiming space in the events table".

<!-- release notes -->

- **The event log no longer grows without limit.** Old events are removed per level (WARNING
  after 30 days, ERROR after 90), in small batches, and a size cap is the safety net. The windows
  can be changed on the config page.
