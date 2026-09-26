# The next button seems to stop playback

# status: reported

# reported problem

Teun, 2026-09-26, MuMa Mobile, most likely app 7.5.2 (server 0.77.0; 0.77.1 / app 7.6.0 was being
deployed at the time and was not on the device yet): "De volgende knop lijkt play te stoppen?" --
tapping next in the app's own UI seems to stop playback instead of skipping to the next track and
playing it. Follow-up detail: it happens on a tablet, with the next button of the app's UI (the
tablet layout of the web UI inside the Capacitor shell), not with the notification, the lock
screen or Android Auto.

# Possible reason

Not established yet. What has been ruled out, and what the production traces show:

**The web player's part in a skip is correct on every layout a tablet can show.** A coarse pointer
makes `isMobile` true at any width (bug report 090), so a tablet shows the phone's mini player and
the full-screen Now Playing, not the desktop bar. All three next buttons call the same
`Player.svelte` `playNext`, which on a native shell hands the service one `next` intent
(`platform.player.next()` -> `MumaPlayerPlugin.next` -> `MediaPlayerManager.seekToNext` ->
`MediaController.seekToNext`, bug report 095) and does nothing else. A simulation of the plugin
that reports a skip the way the device log of crash report 39 shows it -- Media3 masks the seek, so
the first state after it already names the new item as `loading` with `isPlaying` false, followed
by `pause`, and by `play` once the item has buffered -- shows the web player sending exactly one
`next` and no `pause`, `stop`, `setQueue` or `load`, ending on the next track with the play state
the service reports: playing when it was playing, paused when it was paused, and two quick taps
still moving exactly two tracks. `seekToNext` itself never changes `playWhenReady`.

**Subsonic URL signing (MR !1034) is not involved.** It is only in 0.77.1 / app 7.6.0. Every stream
request in the production proxy log around the report is still signed the 7.5.x way and answered
`200`/`206`; there is no `401` or Subsonic error 40 anywhere in the window.

**What the traces around the report show** (production `lms-reverse-proxy` access log, the only
stream activity since that container restarted at 14:59 UTC; stream requests come from the native
player, `getLyricsBySongId` and the Now Playing sections from the web UI whenever its current track
changes):

| UTC | web UI shows | native player requests | "now playing" sent |
|---|---|---|---|
| 16:59:51 | tr-1402535 | tr-1402535 | 16:59:55 |
| 17:00:07 | Now Playing opened on tr-1402535 | | |
| 17:00:12 | | tr-1402535 again, byte range (a seek or a reload of the current track) | |
| 17:00:18 | tr-1402550, then tr-1402551, same second | tr-1402550 (aborted after 262 KB), tr-1402551 | |
| 17:00:20 | tr-1402550 | tr-1402550 | |
| 17:00:22 | tr-1402535 | tr-1402535 | 17:00:24 |
| 17:00:26 | tr-1402550 | tr-1402550 | 17:00:29 |
| 17:00:31 | tr-1402551 | tr-1402551 | 17:00:36 |

The native scrobbler sends "now playing" the moment the player actually starts producing sound on
an item. Read that way, the two moves at 17:00:18 and the one at 17:00:20 never started playing
before the next move came; the later moves each started two to five seconds after the move. A
pause does not reach the server, so whether playback stopped after 17:00:36 cannot be seen here,
and the log cannot tell a quick double tap followed by previous/previous/next/next apart from moves
nobody asked for. There is no diagnostics report from the device for this window (the most recent
upload is crash report 39, app 7.4.5 on the phone, 2026-09-25).

Remaining candidates, none confirmed:

- Something on the native side between `seekToNext` and the new item playing, device-specific
  enough to show on the tablet and not on the phone. The one setting that changes how an item
  transition is rendered is hardware audio offload (`Settings.useHwOffload`, off by default): with
  offload on, `seekToNext` moves within a running offloaded `AudioTrack`, while app 7.5.0 and
  earlier replaced the queue for an in-app next and so rebuilt it.
- A web-UI state that the simulation does not cover (radio, a jam session, a queue that the
  service holds differently from the UI).

# solution

Not fixed yet. `services/frontend/tests/unit/playerNativeSingleNext.test.js` pins the web
player's side of a single tap on next on the desktop bar, the tablet's mini player and the tablet's
Now Playing: one `next` intent and nothing else, keeps playing when playing, stays paused when
paused, and two quick taps still move exactly two tracks. The device-side cause needs the app's own
action trail from the tablet: reproduce, then send a diagnostics report from the app right away, so
the `player.next` entry, the Media3 state lines after it and any player error land in
`crash_reports`. Tracked in GitLab issue #81 (`needs-person`, `verify`).
