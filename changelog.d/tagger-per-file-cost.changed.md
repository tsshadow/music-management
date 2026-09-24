- **Tagger: one database connection per worker and one rule stack per round, instead of per file.**
  Every helper the tagger calls per file used to open its own MariaDB connection (three to six per
  file at ~14 ms each), and every song rebuilt its whole rule stack, including two 37k-name artist
  sets and two uncached list queries for SoundCloud, Telegram and YouTube files. A round now lends
  each thread one connection for its duration and builds each song type's rules once; the artist
  names still follow the helper's snapshot, so tagging results are unchanged. Each round that tagged
  something logs one `Tagging round: ...` line with files, wall time, ms/file and connections opened.
  A single-file scan no longer reloads the genre rules before it knows it can get the scanner lock.
  See bug report 063.

<!-- release notes -->

- **Tagging:** new and changed files are tagged with less overhead per file, which leaves more
  room for the app while a large retag runs.
