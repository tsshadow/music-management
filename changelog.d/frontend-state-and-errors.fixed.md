- **Logging out of the web player left the previous user's session behind.** The queue, current
  track, player state, equalizer, page size and every account setting survived a logout, so the
  next person to sign in on that browser started in the previous person's session. Logout now
  resets everything the web player persists (bug report 041).
- **Changing two settings at once could lose one, and a failed read could wipe them all.** Each
  setting did its own read-modify-write of the shared account blob, and a failed read wrote back a
  blob holding only the one changed key. Changes are now batched into one read and one write, and
  nothing is written after a failed read.
- **An expired password looked like an empty library.** Failed Subsonic answers and MuMa error
  responses were treated as data (and the feed list cached an error as "no feeds" for the whole
  session). They now surface as errors; a rejected password returns to the login page.
- **Sets mode stayed green** once the management pages had loaded: two components overrode the
  brand colour app-wide. Removed, and a test guards against it.
- **Going from one artist or album straight to another could show the previous one's details**,
  and the scrobble-import poll kept running after leaving its tab.

<!-- release notes -->

- Logging out now clears the previous user's queue and settings from the browser.
- Settings changed in quick succession are no longer lost.
- An expired password now returns to the login page instead of showing an empty library.
- Sets mode keeps its blue accent everywhere.
- Artist and album pages no longer show details of the previous one.
