- **The web player shows a floating layout when the app floats.** `CompactPlayer` has a `pip`
  variant with the cover, title and artist only, and `App.svelte` shows it while the window mode
  is `pip`. `platform.system.enterPictureInPicture()` asks the app to float (a browser tab does
  nothing), the track details sheet in Now Playing has a "Zwevende speler" entry in the app, and
  the Apparaat tab has the `pipOnLeave` switch (issue #178, `docs/designs/miniplayer/`).

<!-- release notes -->

- **Zwevende speler** in de Android-app: MuMa als klein venster boven andere apps.
