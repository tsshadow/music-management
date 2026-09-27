# LMS scan trigger — Functional Design

Status: implemented with bug report 120 (GitLab issue #93).

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
4. LMS does not answer: MuMa tries once more two seconds later. If that fails too, the folders are
   sent along with the next notification, and a failed library-wide request is sent again as soon
   as LMS answers anything. With no further request at all, LMS's own periodic scan picks the
   change up.

## Acceptance Criteria

- No "Failed to trigger LMS scan ... Read timed out" from the tagger's round.
- LMS logs "Scan complete" for a library-wide scan again (it only ever logged "Scan aborted").
- An LMS outage produces one WARNING, INFO for the rest of it, and an INFO when it recovers.

## Open Questions / Not Yet Decided

None.
