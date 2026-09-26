- **The hourly track-form push into LMS converges.** 1,481 files had two `library_media_files` rows
  (the scanner's own and a stale one from July 2026 on a length-less stub track), and both were
  pushed, so LMS flipped ~1,700 files between `track` and empty every hour and took its write lock
  each time. The push now sends one row per path, the scanner's own first, and its UPDATE compares
  before writing, so an unchanged run issues no UPDATE at all. The scanner also re-reads a file
  whose row has no length even when mtime and size are unchanged, so ~38,000 files scanned in May
  2026 with only their file name as title get a length, a title and a form. Tracks without a file
  stay unclassified on purpose; the form pass now logs both counts. Bug report 093.

<!-- release notes -->

- **Fewer rating errors during the hourly sync, and about 38,000 older EP tracks get their proper
  title and track/set classification** after the next library scan.
