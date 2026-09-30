- **The app checks the server before restoring the queue, and can start offline.** A start used to go
  straight into one `getSong` per queued track, so with the home server off, or on a network that
  cannot reach it, the boot screen waited and the app came up with a broken queue and failing lists,
  without saying why. Now a single Subsonic `ping` (3 s at most, sent in parallel with the rest of the
  start) comes first. With no answer, a signed-in phone gets "Geen netwerkverbinding" or "Server niet
  bereikbaar" on the boot screen, with "Opnieuw proberen", "Wachten op server" (automatic attempts
  after 2, 5, 10, 20 and then every 30 s, and at once when a network comes up; the start continues by
  itself) and "Offline verder". Offline, the queue keeps only downloaded tracks, a banner says how many
  were left out, Android Auto shows the downloaded library, and the full queue comes back as soon as
  the server answers again. A server that refuses the password still leads to the login page, never to
  "offline". A normal start is unchanged; the ping's time is logged per start as `shell:reachability`.

<!-- release notes -->

- **Starting without the server.** When the app cannot reach the MuMa server at start-up it now says
  so, and you can try again, wait until the server is back (the app then continues by itself), or
  continue offline with the music on your phone. The full queue comes back once the server does.
