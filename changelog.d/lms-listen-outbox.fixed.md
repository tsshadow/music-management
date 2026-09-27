- **LMS keeps a listen until music-manager has it** (issue #67, bug report 075). LMS relayed each
  listen to music-manager with two back-to-back retries and nothing else. Any listen played while
  music-manager was down or starting up (every deploy) was lost, and so was whatever was still
  queued when LMS itself restarted. The relay now writes each listen to an outbox in `lms.db`
  (`muma_listen_outbox`, LMS database version 125) before sending it. It delivers from there in
  play order, one at a time, retrying after 5 s and backing off to once a minute, and removes a
  listen only once music-manager has taken it. A retry sends the same start time, so a listen
  that arrives twice is counted once. The outbox survives restarts. It is bounded at 10,000
  listens and 14 days, and it logs a WARNING for every listen it drops. Delivery runs on LMS's
  background threads with its own HTTP queue, never on a request thread or in the `/muma` proxy's
  queue. music-manager's `/health` now shows, per LMS, how many listens wait and since when
  (`lms_listen_outbox`); it never turns the check red. The 15-minute `lms-listen-backfill` loop
  stays as the safety net behind the outbox.
<!-- release notes -->
- Plays made while the server restarts or updates are no longer lost: the music server now holds
  each one until the history has it.
