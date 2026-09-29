# lms.db sync against a busy server — Functional Design

## Overview

Every hour music-manager writes what it decided about each track -- which version of a song is
canonical, and whether a file is a track, a set or a live set -- into the playback server's own
database, so the app's lists can filter on it. While the server scans the library it keeps that
database locked, and it scans often: for a minute after every download, and for hours during a
library-wide walk. Until now a write that met the lock was retried three times a minute apart and
then abandoned with a warning in the event log, 40 times a day (bug report 129). Nothing was lost
-- the next hourly pass found the same difference -- but the alert was noise, the correction could
take hours, and the sync sat idle for minutes at a time.

## User Stories

- As the owner, I want the alerts topic on my phone to fire only when the server really fell
  behind, so that an alert means something.
- As a listener, I want a song that was just grouped with its other versions to disappear from
  the lists as a duplicate within minutes, even while the server is scanning.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The server is idle during the hourly sync | Everything is written at once, as before. |
| The server is scanning during the sync | The sync finishes in seconds, logs how many rows it could not write yet (INFO), and writes exactly those rows a few minutes later. |
| The scan ends within half an hour | One INFO line says the deferred rows were written; no warning. |
| The server stays busy for the whole half hour | One WARNING for that hour, naming how many rows are still unwritten; the next hourly pass writes them. |
| The server disappears in between | The deferred rows are dropped quietly; there is nothing to write into. |

## Acceptance Criteria

1. A sync that meets a scanning server never produces more than one WARNING per hour.
2. No row a busy server refused is forgotten before it has been tried again.
3. While the server scans, the player's own writes (ratings, scrobbles) are never held up longer
   than one short batch of the sync's writes.

## Open Questions / Not Yet Decided

- None. The scanner's own long hold on the lock (which also affects the player's requests during a
  scan) is an LMS-side issue, tracked in GitLab issue #133.
