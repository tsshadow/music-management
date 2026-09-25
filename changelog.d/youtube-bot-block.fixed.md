- **YouTube's "Sign in to confirm you're not a bot" is now one warning, not an error per video.**
  Bug report 076: since 2026-09-24 the event log took about 20,000 ERROR events a day (26,721 in
  under two days), plus the same number of "No title found in player responses" warnings. 0.72.2
  did not cause the refusals. It made them visible, because it was the first release that passed
  yt-dlp's output to the event log. YouTube downloads had already stopped at about 2026-09-20
  02:40 UTC. The YouTube worker now counts these refusals across the sweep. After
  `bot_check_threshold` in a row (default 5) it stops, pauses YouTube for `bot_check_pause`
  (default 6 hours, both adjustable in Beheer > Downloaders) and logs one WARNING that says to log
  in again in the Firefox container. Beheer shows the pause together with that instruction. A
  missing or unreadable Firefox cookie database is now one clear ERROR at the start of a round,
  not a failure for every video. The worker also reads its cookies from a checkpointed copy of the
  profile, as SoundCloud already did, so it no longer misses the newest cookies Firefox has only
  written to its write-ahead log. The downloads themselves only return once someone logs in to
  YouTube again in the `muma-firefox` container (see `docs/open-work.md`).

<!-- release notes -->

- **A blocked YouTube no longer floods the event log.** When YouTube asks the downloader to sign
  in, you now get one warning and a note in Beheer that tells you to log in again in the Firefox
  container.
