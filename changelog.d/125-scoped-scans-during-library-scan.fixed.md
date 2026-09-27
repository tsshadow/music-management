- **A new download stayed invisible in LMS for as long as its library-wide scan ran -- well over
  an hour** (issue #125, `docs/bug-reports/126-scoped-scans-wait-for-full-scan.md`). On production
  the library-wide scan started at 15:38 on 2026-09-27; by 17:23 LMS had received 225 scan
  requests, 224 of them folder announcements from the downloader and tagger, and started not one
  scan. Before 15:38 each announcement was read within about a minute. The cause: the "pause the
  library scan for a scoped one" path ran on the scanner's io thread, which is the thread the
  library scan itself occupies, so it could only fire once there was nothing left to pause.
  Announced folders now go into a queue the running scan reads itself: at a safe point in the file
  walk, the removed-files check and between steps, it runs a priority pass over them -- the
  ordinary scoped scan -- and carries on where it was, without restarting or aborting anything
  (bug report 120's loop stays closed). Two minutes of library scan between passes keep a busy
  tagger from stalling it. The scan summary in the log gains `priority passes = N (M folders)`,
  each pass logs its own `Priority scan of N announced folder(s) complete` line, and
  `getScanStatus` gains `pendingFolders` and `priorityScan`.
<!-- release notes -->
- **New downloads show up in the app while LMS is scanning the whole library**, within a few
  minutes instead of after the library scan (which takes over an hour) has finished.
