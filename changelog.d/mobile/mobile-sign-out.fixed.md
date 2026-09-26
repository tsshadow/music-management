- **"Uitloggen" signs you out again.** The app's sign-out cleared the playback queue on the wrong
  thread: Media3 threw, the call never finished, and neither the stored password nor the web
  session was cleared -- so the button did nothing, or the app restarted still signed in. The
  sign-out now runs on the main thread, clears the credentials (password, MuMa key and tokens, the
  Subsonic token) before the queue, and a queue that cannot be cleared no longer keeps them. The
  web side waits at most five seconds for the phone and marks the device as signed out, so the next
  start shows the login page even if the phone could not be cleared; the next sign-in lifts the
  mark. Bug report 106.

<!-- release notes -->

- **Uitloggen werkt weer.** Na "Uitloggen" stopt het afspelen en zie je het inlogscherm, ook als je
  de app daarna opnieuw opent. Je downloads blijven staan.
