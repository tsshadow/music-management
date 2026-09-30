- **Correct a track's BPM by hand** (bug report 140). The track panel in the management library and
  the player's track details get ½×, 2× and a tempo field for users with the new `bpm.override`
  permission (admins by default). The tempo is stored separately (`library_track_bpm_manual`),
  wins over every measurement, is never overwritten by the analyzer, shows everywhere at once
  (library, BPM browse, feeds, analytics) marked "handmatig", is written into the file's tag by the
  next writeback round, and "Gemeten" takes it back. Every change is in the audit log
  (`bpm.manual_set` / `bpm.manual_cleared`). API: `PUT` / `DELETE
  /api/library/bpm/tracks/{id}/manual`.

<!-- release notes -->

- **Fix a wrong BPM yourself**: halve it, double it or type it in the track details (needs the new
  `bpm.override` permission; admins have it).
