- **In split screen next to Google Maps, MuMa shows a large compact player.** When MuMa has a
  split-screen half lower than 480px (a phone in portrait), the half shows the cover, the title
  and an 80px play button between 64px previous and next buttons, with no stars. "Navigeren naast
  MuMa" opens Google Maps in the other half, with no destination, and is only there when Maps is
  installed. "Volledige app" shows the normal screens until the split changes. The screen stays on
  while the compact player shows and music plays. The shell reports the window mode
  (`windowModeChanged`), and `setKeepScreenOn` has a separate `keepOn` flag that car mode does not
  touch (issue #179, `docs/designs/miniplayer/`).

<!-- release notes -->

- **Split screen met Google Maps.** Zet je MuMa naast Maps, dan toont MuMa een grote speler met
  afspelen, vorige en volgende, en blijft het scherm aan zolang de muziek speelt. "Navigeren naast
  MuMa" opent Maps in de andere helft.
