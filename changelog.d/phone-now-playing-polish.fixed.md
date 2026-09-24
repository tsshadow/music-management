- **Web UI on a phone: the now-playing rating stars hung off the left edge.** The same full-screen
  player the app bundles (`NowPlaying.svelte`) now centres the rating row and shows an unrated
  track as grey outlined stars instead of a faded glyph that read as disabled. The desktop player
  bar is unchanged.
- **Web UI on a phone: the now-playing screen had no news button.** Only the desktop player bar
  rendered it; `NowPlaying.svelte` now has it next to the radio button, wired to the same
  `toggleNews` (bug report 059).

<!-- release notes -->

- **Phone player (web):** rating stars centred, unrated stars shown as outlines, and the news
  button is back next to the radio.
