- **33,590 releases showed no cover even though their folder had one** (issue #158, bug report 144). Scene
  releases name the cover after the release (`00-artist_-_title-(cat)-web-2026.jpg`), and LMS only
  looked for `cover`, `front`, `folder` and `default`. When none of those is there, LMS now takes
  the `00...` image. If there are several, it skips proofs, back covers, inlays and disc scans
  (`...-proof`, `...-back`, `...-cd1`) and prefers one marked `front` or `cover`. It looks only at
  the part of the name that differs, so a title such as `come_back` does not count. If a folder
  has no `00...` image but exactly one other image, that image is used. An embedded front cover
  still comes first. Run over production's folders, the rule finds a cover for 33,445 of the
  33,590 releases. The 145 left have only proofs, scans or back covers. The new
  `cover-fallback-*` and `cover-single-image-fallback` keys in `lms.conf` configure it.
- **New cover rules reach releases scanned long ago.** LMS database step 126 (version 127) records
  which cover rules the last library-wide scan applied. When the rules differ, the next
  library-wide scan recomputes the covers of every release, track and artist, even if no file
  changed. No file is re-read. Changing `cover-preferred-file-names` now takes effect the same way.

<!-- release notes -->

- **About 33,000 releases get their cover back.** Scene-style cover files (`00-...jpg`) are now
  recognised, and proofs, back covers and disc scans are skipped. The covers appear after the
  first full library scan following the update.
