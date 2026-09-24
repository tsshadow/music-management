- **The tagger rewrote files on every retag, and each rewrite could give a track a new identity.**
  `CheckArtistRule` edited the artist list while walking it, so a corrected first artist moved to
  the end (`ANGERFIST;outsiders;Dj Mad Dog` became `outsiders;Dj Mad Dog;Angerfist`) and the order
  changed again next pass; the scanner derives `track_uid` from the first artist, so ratings and
  listens ended up on a stale row. Every tag value was also split on '/', so AC/DC became two
  artists and `Live 24/7` three title parts; only genres are split on '/' now. On m4a, `REMIXER`
  and `ORIGINAL_TITLE` were written to atoms mutagen truncates to `REMI`/`ORIG` and never read back
  (title inference re-ran on the already-cleaned title each retag), and album / album artist went
  to atoms LMS does not read. They now go to `----:com.apple.iTunes:REMIXER`,
  `----:com.apple.iTunes:ORIGINAL_TITLE`, `©alb` and `aART`, and a file with the old atoms is
  migrated on its next retag. Bug report 037.

<!-- release notes -->
- The tagger no longer rewrites already-tagged files on every run, keeps the artist order and
  slashes in names like AC/DC, and writes album, album artist, remixer and original title on m4a
  files where LMS and the tagger itself can read them back.
