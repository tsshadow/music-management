- **Downloaded playlists waren onvindbaar zodra het toestel geen route naar de server meer had.**
  Ze bestonden alleen als `.m3u`-bestand met een weergavenaam en niets anders -- geen server-id, dus
  `OfflineSubsonic` had `getPlaylists`/`getPlaylist` niet geïmplementeerd en de webspeler zag nul
  playlists offline. `RESTMusicService.getPlaylist` -- de aanroep die zowel een simpele weergave als
  "download deze playlist" al deed -- schrijft de server-id, naam en tracklijst nu ook in een eigen
  Room-tabel (`offline_playlists`, migratie 9→10). Een playlist die alleen als oud `.m3u`-bestand
  bestaat verdwijnt niet: die wordt gelezen en krijgt een stabiel synthetisch id
  (`LegacyPlaylistFiles`). `getPlaylists`/`getPlaylist` in `OfflineSubsonic` beantwoorden beide uit
  die samengevoegde lijst, in dezelfde JSON-vorm als de server, met alleen de tracks die daadwerkelijk
  op het toestel staan.

<!-- release notes -->

- Gedownloade playlists blijven nu ook zichtbaar zonder verbinding, inclusief playlists die al voor
  deze update waren gedownload.
