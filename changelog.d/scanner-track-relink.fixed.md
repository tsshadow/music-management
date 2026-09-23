- **A retag that changed a title or the primary artist left the track's ratings and listens behind.**
  `track_uid` hashes title, duration and primary artist, so the scanner gave the retagged file a new
  track row and never touched the old one: ratings (`rating_tracks`) and listens (`scrobble_listens`)
  stayed on a row without a file, and the song-version worker could even pick that row as canonical
  and hide the real file in LMS. The scanner now moves ratings (newest wins), listens, analysis rows
  and work pins to the new row and deletes the old one, in one transaction; a fileless track can no
  longer be canonical. Rows orphaned before this are repaired by the new admin-only
  `POST /api/scanner/relink-orphans` (bug report 042).
- **A corrected publisher kept its old label link.** Label and channel links were only ever added;
  they are now recomputed from every file of the track on each scan.

<!-- release notes -->

- **Ratings and listening history now survive a retag that changes a track's title or artist**, and
  a corrected label replaces the old one instead of piling up next to it. Tracks damaged before this
  can be repaired with a one-off admin action.
