# LMS scan trigger — Functional Design

Status: implemented with bug report 120 (GitLab issue #93); announced folders during a
library-wide scan with bug report 126 (GitLab issue #125).

## Overview

MuMa tells the music server (LMS) about changes in two ways: "read these folders" (a scoped scan,
sent per folder the tagger, importer or downloader wrote to) and "look at the whole library for
anything that changed" (a library-wide scan). Before this change the library-wide request threw
away whatever scan LMS was running and started over, and the tagger sent one every ~5 minutes.
A library-wide scan on production takes the better part of an hour, so none ever finished, and
the request itself often ran out of time while LMS was busy throwing the old scan away -- about
ninety warnings a night on the alerts topic.

## User Stories

- As the owner, I want a new or retagged release to show up in the app within seconds, without
  LMS's library-wide scan being restarted every five minutes.
- As the owner, I want LMS's periodic library scan to actually complete, so files nobody announced
  and files that were removed are picked up.
- As the owner, I want one alert when LMS stops answering, not one per request.
- As the owner, I want a new download to show up within minutes even while LMS is scanning the
  whole library, which takes over an hour (bug report 126).

## Functional Flows

1. The tagger writes a file: LMS is told the folder (as before). The tagger no longer asks for a
   library-wide scan at the end of each round.
2. "Rerun parse" on one track: LMS is told the track's folder instead of being asked for a
   library-wide scan.
3. A library-wide scan is asked for (the hourly MuMa scanner run, or by hand):
   - if LMS is already scanning the whole library, the request joins that scan;
   - if LMS is reading a few folders, the library-wide scan starts right after;
   - otherwise it starts now.
   A request for a full re-read, an optimize or a compact still starts over, as before.
4. A folder is announced while LMS scans the whole library: the library scan does not stop and
   does not start over. At its next safe point -- every few files while it walks the library or
   checks for removed files, and between its steps -- it reads the announced folders first (a
   "priority pass", the same work as a scoped scan) and then carries on where it was. Folders
   announced within a few seconds of each other, or twice, are read together, once. After a pass the
   library scan gets at least two minutes to itself before the next one, and one pass reads at most
   50 folders (the rest go in the next pass), so a busy tagger cannot stall it. Removing rows for
   files that are gone does not hold a pass back either: it happens 50 rows at a time, with a look
   at the announced folders in between. Scan status shows how many announced folders are waiting and whether a pass is running;
   the progress shown stays that of the library scan.
5. LMS does not answer: MuMa tries once more two seconds later. If that fails too, the folders are
   sent along with the next notification, and a failed library-wide request is sent again as soon
   as LMS answers anything. With no further request at all, LMS's own periodic scan picks the
   change up.

## Acceptance Criteria

- No "Failed to trigger LMS scan ... Read timed out" from the tagger's round.
- LMS logs "Scan complete" for a library-wide scan again (it only ever logged "Scan aborted").
- An LMS outage produces one WARNING, INFO for the rest of it, and an INFO when it recovers.
- During a library-wide scan, a downloaded folder is readable in LMS within a few minutes (quiet
  period + at most the two-minute gap + the pass itself; no gap of half an hour while the scan
  removes thousands of rows, bug report 136), and LMS logs
  `Priority scan of N announced folder(s) complete`; the library scan still ends with
  `Scan complete ... priority passes = N (M folders)`.

## Open Questions / Not Yet Decided

None.
