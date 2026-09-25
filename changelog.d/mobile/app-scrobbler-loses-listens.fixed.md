- **The app lost listens: a failed send, a killed process, the car and offline mode each dropped
  them.** Since the web player inside the app stopped scrobbling (0.72.1), the native scrobbler was
  the only path, and it forgot a listen whose send failed, recorded nothing for a set whose process
  died mid-play, did not run at all when playback started from Android Auto or the notification
  without the app's screen, threw offline listens away, sent radio and news under ids the server
  refuses, and counted a track played twice in a row once. Every play of 5 seconds or more is now
  written to a queue on the phone as soon as it qualifies and kept there until the server has
  confirmed it; it is sent again after a failure, when the network returns and on the next start.
  Each listen carries its start time, so LMS and MuMa store it once however often it is sent, and
  both at the same second. Scrobbling now runs in the playback service (bug report 071).

<!-- release notes -->

- **Listens no longer go missing.** A track you played is remembered on the phone until the server
  has it, also when you were offline, in the car, or the app was closed in the middle of a set.
