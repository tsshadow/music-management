- The orphan relink (`POST /api/scanner/relink-orphans`) now also matches on the file name. About
  50,000 fileless track rows from the first scan in May 2026 have the raw file name as their title
  and no artist or duration, so the metadata match could never find their successor. An orphan
  whose title is the file name (without extension) of exactly one track's file is now relinked to
  that track, and its listens and ratings move with it. A name that several tracks share is left
  alone. The totals, the event and `GET /relink-orphans` report how many rows each key relinked,
  and `?dry_run=1` counts without writing (bug report 104, issue #71).
