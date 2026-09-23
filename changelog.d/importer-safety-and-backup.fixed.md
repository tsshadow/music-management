- **A half-extracted archive could land in the library.** Every backend extracted straight into the
  import folder, so when `unrar-free` gave up after 13 of 44 releases, those 13 stayed there and the
  fallback extracted the rest on top of them (7z renamed each collision to `name_1.mp3`). The same
  cycle then moved whatever was there. Each attempt now extracts into its own staging folder, and
  only a complete extraction reaches the import folder. (bug report 046)
- **A release still being copied into `__TODO` could be renamed or moved half-done.** The
  flattener, renamer and mover now leave a folder alone until nothing in it has changed for
  `import_settle_minutes` (new setting, default 5).
- **A second download of a release already in the library stayed in `__TODO` for ever.** The
  duplicate check compared byte sizes, and the library copy gets new tags right after the move, so
  the two never matched. The mover logged "contents differ ... manual intervention" about it on
  every cycle. Releases are now compared by track list and track length.
- **Every import cycle read the tags of every folder it could not place again**, over CIFS: about
  2.266 folders every five minutes. A folder is now read again only when something in it changed.
- **Split RAR sets failed on every cycle.** Only the first volume is extracted now, and the other
  volumes are quarantined together with it.
- **A full backup disk never recovered.** Old dumps were only pruned after a successful dump, and a
  dump that ran out of space left its half-written file behind. The job now prunes first (never the
  newest daily), refuses to start when the last dump would not fit, and removes a partial file
  whatever went wrong. The monthly copy is streamed and verified instead of being read into memory,
  and `latest.json` can no longer be left half-written.
- `scripts/restore_db.sh` and `tools/backup_db.sh` no longer put the database password on a
  command line.

<!-- release notes -->

- **Importing a large archive can no longer put a half-finished release in the library**, and a
  release still being copied into the import folder is left alone until the copy is done.
- **A second download of a release you already have is now recognised as a duplicate** instead of
  sitting in the import folder for ever.
- **Split RAR archives import cleanly.**
- **The nightly database backup recovers on its own when its disk fills up.**
