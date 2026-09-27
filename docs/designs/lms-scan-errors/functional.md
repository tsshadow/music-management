# LMS Scan Errors — Functional Design

> Background and measurements: [bug report 121](../../bug-reports/121-lms-scan-errors-and-queue-playlists.md),
> GitLab issue #95.

## Overview

The music server (LMS) ends every scan with one log line that includes an error count. On
production that count read 967 on every folder-sized ("scoped") scan, whether it had read one file
or a hundred, and nothing said what the errors were. They were all playlists: scene releases' own
`.m3u` files that name tracks which have since been renamed, moved, or are still in the import
queue. The count told the operator nothing, and the ERROR lines that do matter (unreadable audio,
corrupt images) were buried under 90,000 lines about files that had simply been removed.

## User Stories

- As the operator, I want the scan summary to say which kinds of errors it found, so that I can
  tell unreadable music from stale playlists without reading thousands of log lines.
- As the operator, I want a scan of one folder to report only problems in that folder, so that the
  same several hundred playlists are not reported every few minutes.
- As the operator, I want a release that is still in the import queue not to produce errors, since
  it is not finished yet.
- As the operator, I want real errors to stay visible: in the library-wide scan's summary and in
  the scan report on the admin page.

## Functional Flows

1. A scoped scan runs after MuMa moves or retags a folder. Its summary counts only errors found in
   the files it read and in playlists inside the folders it was asked about.
2. The library-wide scan still checks every playlist and reports every broken one, labelled by
   kind; the admin page's scan report lists each of them.
3. A playlist inside `__TODO` (the import queue) is matched to tracks as usual, but a missing entry
   there is never counted as an error.
4. A file that disappeared from disk is removed from the index quietly (DEBUG), as before; only
   failures other than "not there" (permissions, I/O) are logged as errors.

## Acceptance Criteria

- The summary line reads `errors = N: <count> <kind>, ...`, largest kind first; with no errors it
  reads `errors = 0` as before.
- A scoped scan of a folder with no playlist problems reports no playlist errors, however many
  broken playlists exist elsewhere.
- A `__TODO` playlist never contributes to the count, in any scan.
- `Error while checking file ...: No such file or directory` no longer appears at ERROR level.
- Unreadable audio and image files are still counted and logged at ERROR.

## Open Questions / Not Yet Decided

- Whether single-release scene playlists outside the queue (574 on production) should stop being
  reported, or be removed by the importer after tagging. Tracked as decision issue #96.
