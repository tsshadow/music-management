- **Which version of a song plays is now decided by format first, then by the kind of edit.**
  The old order put "official release" first, and a release still waiting in `EPs/__TODO` has no
  label yet, so it counted as unofficial and lost to a SoundCloud or YouTube rip (549 songs on
  production, e.g. Hysta & RDØ – TOGETHER; 1,428 picked a worse format than a sibling). The new
  order: lossless over MP3 (or MP3 320 first when `prefer_lossless` is off), then pro edit > radio
  edit > edit > original > no marker > extended > instrumental > music video, then bitrate, then
  official release (anything under the label tree, including the import queue, counts), then the
  oldest. A pin still wins. Every song is re-ranked once after the deploy; the log says how many
  choices changed before it changes them (about 2,700 of 32,000 multi-version songs by a SQL
  estimate). Pinning a version now needs the `rules.manage` permission.
