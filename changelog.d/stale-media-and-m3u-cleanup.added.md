- **`scripts/prod/person/merge-stale-media-rows.sh` removes the 1,493 stale media rows the hourly
  syncs skip** (issue #124, bug report 093). Each one's hash is not the SHA-256 of its path, so the
  scanner never sees it, and it holds a stub track with the file name as title. The script finds
  the live track for the same file (1,481 by path, 10 more by the path with a doubled release
  folder collapsed), merges the stub's ratings keeping the highest per user, moves its listens
  (dropping a listen the live track already has), takes it out of its works, and deletes the row
  and the stub. Two folder rows nothing refers to are deleted outright; anything referenced that
  cannot be matched would be kept and listed (none on 2026-10-02). JSON backup first, `--rollback`,
  one transaction per row.
- **`scripts/prod/person/delete-stale-m3u-playlists.sh` deletes the 574 scene playlists LMS reports
  after every library scan** (issue #96, bug report 121). It decides "missing" the way LMS's scan
  step does, from LMS's own database, leaves the import queue and partly-matching playlists alone,
  tars every file first, and asks LMS to rescan the folders. 572 of the 574 predate 2026; nothing
  in the importer or tagger renames a track, so no code change stops new ones.

<!-- release notes -->

- **Two one-off cleanups for the library's leftovers:** 1,493 duplicate track rows from July are
  folded into the real tracks (ratings and listens kept), and 574 broken scene playlists that LMS
  complained about after every scan are deleted.
