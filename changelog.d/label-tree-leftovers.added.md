- **Three person scripts for what the label-tree cleanup left behind.**
  `park-duplicate-releases.sh` finds release folders that hold the same release twice in one label
  folder (838 groups on prod) and moves the weaker copy to `/mnt/music/.quarantine/`. A move happens
  only when the copies have the same format, the same source and tracks that pair on title and
  duration, and one copy wins on files, bitrate, scene name or .nfo (595 folders). Ties, vinyl next
  to web, scene fix releases and history held only by the weaker copy are listed for a person.
  `merge-stale-media-rows.sh` now also deletes the media rows whose file is gone from disk (8,372,
  mostly old `EPs/__TODO/` paths, `--gone`). It stops when a share looks unmounted.
  `fix-catalogue-tag-mismatch.sh` writes the folder's catalogue number into files whose
  CATALOGNUMBER disagrees with it, only where the release's .nfo agrees with the folder. All three
  back up first and have a rollback.
<!-- release notes -->
- Person scripts to park duplicate release folders, delete media rows of vanished files and fix
  catalogue-number tags that disagree with the folder and its .nfo.
