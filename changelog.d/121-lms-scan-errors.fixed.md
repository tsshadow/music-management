- **LMS's scan summary says what its errors are, and folder scans stop re-reporting the same 967**
  (issue #95, bug report 121). Every scoped scan on production ended with `errors = 967`, even
  after reading two files. All 967 were playlists: scene releases' own `.m3u` files naming tracks
  the tagger has since renamed (439) or whose audio is gone (149), and releases already moved out of
  the import queue `EPs/__TODO` (49) -- 637 with every entry missing, plus 330 single
  missing entries that were counted but only logged at DEBUG. The playlist step walks the whole
  library, so each scoped scan re-reported all of them. A scoped scan now only reports playlist
  problems inside its own folders, playlists in `__TODO` never count, and the summary lists the
  count per kind (`errors = 967: 637 playlist-all-entries-missing, 330 playlist-entry-missing`).
  The library-wide scan still reports every broken playlist and every unreadable file, and its
  admin-page report still lists each one. Files that were simply removed are no longer logged as
  `[error] Error while checking file ...: No such file or directory` -- 92,000 lines in six hours
  that buried the real errors.
<!-- release notes -->
- The music server's scan log now says what kind of problems it found, and no longer repeats the
  same hundreds of playlist warnings after every small scan.
