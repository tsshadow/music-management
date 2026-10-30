# The App Scrobbled Every Listen Twice Since The Web UI Moved Into It

# status: fixed — on the native shell the web player leaves scrobbling to the platform service

# reported problem
"Interne scrobbles mislukt?" — the app showed "Scrobble mislukt" toasts. Diagnostics report 37
(app 7.4.1, 2026-09-23) and production's `scrobble_listens` showed scrobbles arriving, but in
pairs. Measured on production for 2026-09-12 to 2026-09-23: of the `frontend` rows, 345 have a
`mobile`/`auto` row for the same track within 45 minutes (today 13 of 13, yesterday 46 of 47).
Before the shell went live (2026-09-08 to 2026-09-11) the same query finds zero.

Two further oddities in the `frontend` copies:
- six different tracks on 2026-09-23 carry the same `listened_at` (06:27:11);
- they arrive in bursts up to half an hour after the play (`created_at` 06:57–06:58 for plays
  starting 06:27).

# Possible reason
Since the Capacitor shell (2026-09-12), the Svelte `Player.svelte` runs inside the app. Two
components scrobble the same track through LMS `/rest/scrobble`:

- the native `service/Scrobbler.kt` (source `mobile` or `auto`), driven by the media3 service;
- `Player.svelte`'s `scrobble()` (source `frontend`), driven by the service's events relayed
  into the WebView.

The server de-duplicates on `(username, listened_at, track_id)` only, and the two copies carry
different timestamps, so both are stored.

The web copy is wrong on its own too. On native, track changes arrive as `command` or
`durationchange`; `handleNativeCommand`/`handleDurationChange` reset `hasScrobbledStarted` but
`handlePlay`, the only place that sets `listenStartedAtMs`, does not fire again while playback
continues — so every following submission reuses the first track's start time. And a WebView in
the background is throttled or suspended: its fetches fail (the toast) or leave in a burst when
the app returns.

# solution
`scrobble()` in `Player.svelte` returns immediately when `nativePlayback`
(`platform.player.ownsQueue`) is true; the browser keeps scrobbling as before.
`playerNativeMode.test.js` fires play, a timeupdate past the threshold and ended through the fake
plugin and asserts no `/rest/scrobble` leaves the WebView — it fails with three requests without
the guard.

The duplicate rows already on production are not removed by this change. Gaps in the native
scrobbler that the web copy used to paper over are listed in the open GitLab issues.
