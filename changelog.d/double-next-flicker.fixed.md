- **Two quick taps on "next" in the app no longer leave the player flickering between two tracks.**
  On the phone the web player worked out the next track itself and pushed it to the native
  service as a new queue position. A second tap before the service had reported the first move
  queued a second push; the report of the first move then pointed the UI back at the first
  target, and that mirror went across as a request too -- so each settled move re-queued the other
  one, indefinitely. "Next" and "previous" are now intents the service carries out (N taps move N
  tracks, shuffle and repeat are the service's own), a UI write that follows a service report is
  never sent back, and a report from before the newest requested move is dropped. The same race
  also hit two tracks picked from the list in quick succession. Bug report 095.

<!-- release notes -->

- **Tapping "next" twice quickly in the app no longer makes the player flicker between two tracks
  without settling.**
