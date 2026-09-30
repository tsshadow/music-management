# LMS scanner write pacing — Functional Design

## Overview

The music server (LMS) keeps its library in one SQLite file, `lms.db`, and only one writer at a
time can hold the write lock. The scanner writes in many short transactions. It used to start
the next one straight after committing the last, so for as long as a scan had something to write,
nobody else got the lock. That included music-manager's hourly sync of song versions, track forms
and accounts. It gives up on a row after waiting 10 s and retries later (bug report 129). A rating
or scrobble stored during that time could also wait.

This change makes the scanner give the lock away regularly. After about half a second of writing
it waits briefly without the lock, so a waiting writer always gets a turn. It also covers the
related cleanup: the WAL file next to the database is capped in size, and the podcast and
ListenBrainz background tasks no longer take the server down when the database refuses a write
(bug report 135).

## User Stories

- As the listener, I want a rating or scrobble made during a library scan to be stored within a
  second, not after the scan finishes or never.
- As the operator, I want music-manager's hourly sync to finish its writes to LMS even while
  downloads keep triggering scans.
- As the operator, I want a locked database to cost a podcast refresh or a ListenBrainz sync one
  round, not a server restart.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A scan writes for several seconds without a break (many changed files) | Every ~0.5 s the scanner pauses 120 ms without the lock. Another writer waiting for the lock gets it inside that pause. |
| A scan with only a handful of changes | No change: it never writes long enough to pause. |
| The scanner paused at least once during a scan | One INFO line after the scan summary: how many times it released the lock, and the total pause. |
| music-manager's hourly sync runs during a write-heavy scan | Its transactions get the lock within about half a second instead of timing out after 10 s. |
| The WAL file (`lms.db-wal`) grew large during a long write burst | It is truncated back to 64 MB the next time the log is reset. |
| A podcast refresh step or a ListenBrainz sync hits a database that stays locked for more than 15 s | A WARNING in the log. The item or the refresh is retried on the next round, and the server keeps running. |

## Acceptance Criteria

1. While a paced bulk writer runs, a second SQLite connection's `BEGIN IMMEDIATE` succeeds within
   1.5 s. Without pacing it timed out after the full 10 s in every measured case.
2. While a paced bulk writer runs, another LMS thread's write transaction starts within 1.5 s.
3. A scan that pauses logs how often and for how long.
4. A refused write in a podcast step or ListenBrainz synchronizer is logged as a WARNING, does not
   end the process, and leaves no half-written objects behind for the next write on the thread.
5. A podcast refresh ended by a refused write lets the next refresh run.

## Open Questions / Not Yet Decided

- None. The pacing values (0.5 s of writing, 120 ms pause) are constants in `ScannerService.cpp`,
  not settings. They can be tuned after measuring on production.
