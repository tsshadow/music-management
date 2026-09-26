- `POST /api/scanner/purge-orphans` (admin only, `?dry_run=1` supported) deletes fileless track
  rows that nothing a user made points at: no listen, no rating, no work pin and no reviewed ml
  label. It works in batches of 1000 and takes the rows' link rows with them. Orphans that do have
  references are kept and listed on `GET /purge-orphans` for a person to decide. The operator
  script `scripts/prod/person/relink-orphans-by-filename.sh` backs everything up first, then runs
  the relink and then the purge (bug report 104).
