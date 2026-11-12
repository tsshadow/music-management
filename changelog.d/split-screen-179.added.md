- **The web player knows when the app is in split screen.** `platform.system` has
  `windowMode()`, `onWindowModeChanged()`, `canNavigate()` and `navigateAdjacent()`, and
  `setKeepScreenOn` takes a `keepOn` flag. A browser tab is always `full` and cannot open Maps, so
  nothing changes there. `CompactPlayer` has a `split` variant with large buttons and the
  "Navigeren naast MuMa" and "Volledige app" pills (issue #179, `docs/designs/miniplayer/`).

<!-- release notes -->

- **Grote speler in split screen** in de Android-app, naast Google Maps.
