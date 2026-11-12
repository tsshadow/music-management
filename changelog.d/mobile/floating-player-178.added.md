- **MuMa can float as a small window above other apps.** "Zwevende speler" in the Now Playing
  menu shrinks MuMa to a 16:9 window with the cover, the title and the artist, and Android's own
  previous, play/pause and next buttons. With the setting "Zwevende speler bij verlaten" (Apparaat
  > Afspelen, off by default) MuMa floats by itself when you leave it while music plays. The
  activity declares `supportsPictureInPicture`, and its window parameters follow every play/pause
  and track change (issue #178, `docs/designs/miniplayer/`).

<!-- release notes -->

- **Zwevende speler.** MuMa kan als klein venster boven andere apps blijven staan, via het menu in
  Nu speelt, of vanzelf als je de app verlaat terwijl er muziek speelt (instelling "Zwevende speler
  bij verlaten").
