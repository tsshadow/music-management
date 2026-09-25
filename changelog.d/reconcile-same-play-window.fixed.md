- **The LMS listen reconcile could insert one play twice.** LMS records a listen when playback
  starts; the app scrobbles to MuMa about a minute later (55 s on production). The check "is
  this the same play under another track, or unmatched?" used the 5-second pairing window, so it
  missed that listen. It now has its own 600-second window. Exact and shifted pairing are
  unchanged. The production dry run had called 254 LMS listens insertable under the old rule.
- **The reconcile treated `user` and `Teun` as two people.** Usernames are now compared without
  case. Every name is shown and inserted in MuMa's own spelling.
- **A stale `lms.db` without LMS tables is ignored everywhere, with a single warning.**
  Production's leftover `alpha/lms.db` (schema 114, no `user` table) made the song-version sync
  log "no version columns yet" every one to two minutes and retry as if a server were still
  migrating. `lms_db_targets()` now drops such a file for every consumer.
<!-- release notes -->
- The listen reconcile no longer counts one play twice or splits one user into two by
  capitalisation. A stale second server database no longer fills the log.
