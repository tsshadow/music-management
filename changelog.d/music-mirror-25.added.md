- **A nightly copy of the music library to a second NAS (issue #25).** `tools/music_mirror.py`
  runs on the mirror NAS at 01:30. It pulls the library with rsync over SSH, read-only on the
  library side (`rrsync -ro`), and never deletes on the mirror: a file removed or moved in the
  library stays at its old path. A ZFS snapshot follows each good run, kept 14 daily, 8 weekly and
  12 monthly. A library under 90% of last night's file count, or more than 5% or 200 GB to copy,
  refuses the run until a person checks. Each night 200 files are compared by checksum, and once a
  month every file. `GET /health/music-mirror` answers 200 or 503 with no key and never shows a
  file name. The daily check at 09:42 (`muma-music-mirror-check.timer`) writes an `INFO` event for
  a good night, or an `ERROR` with a push for a failed, refused, stale or differing one.
  `scripts/music-mirror/install.sh` sets up both NAS sides: it shows every change first and
  applies nothing until you type `yes`. Nothing runs until a person installs it, see
  `scripts/music-mirror/README.md`.
<!-- release notes -->
- **The music library can now have a nightly copy on a second NAS.** Deleted files stay on the copy,
  and snapshots keep older versions. `/health/music-mirror` tells a monitor whether last night
  worked. A person must install it on both NAS machines first.
