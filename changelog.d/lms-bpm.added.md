- **Subsonic clients now see each song's tempo** (issue #150). LMS read the file's BPM tag but
  stored nothing, so third-party Subsonic clients showed no BPM even after 0.86.0 started writing
  the measured tempo into the files. LMS now keeps it per track (a new `track.bpm` column, database
  version 126) and returns OpenSubsonic's integer `bpm` on every song object -- `getSong`,
  `getAlbum`, `search3`, playlists and the rest share one serializer -- with `0` when the file has
  no tempo. The tag is read as `150`, `150.0` or `150,5` (rounded half up); anything else, or
  outside 40-500, counts as no tempo. The upgrade bumps the audio scan version, so the next scan
  re-reads every file once: that is what fills in the files whose tag was already right and which
  the writeback therefore never touched. An LMS image from before this change refuses the upgraded
  database. MuMa's own pages keep showing MuMa's measurement (docs/designs/lms-bpm/).

<!-- release notes -->

- **Other Subsonic apps now show the BPM** that is in the file. The first library scan after the
  update reads every file once to pick it up.
