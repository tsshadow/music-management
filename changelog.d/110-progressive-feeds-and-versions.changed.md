- **Feeds, the release radar, the daily mixes and a song's versions open at once and fill in**
  (issues #110 and #111, `docs/designs/perceived-performance/`). A daily mix showed its header and
  then a bare "Laden..." until MuMa had answered and every `getSongsByPath` chunk had been
  resolved, one after another. The song page (`song:`) showed nothing but "Laden..." until up to
  five pages of `getSpotifyTracks` had come back. A tapped daily-mix card now leaves its title and
  subtitle, and a tapped versions button the track's title, artist and cover: both pages draw that
  header at once, with skeleton rows where the tracks go. A feed's chunks are resolved in parallel
  (`/rest` does not pass the serial MuMa gate, and a feed is at most two chunks) and each chunk's
  rows appear as it lands, always in MuMa's order. A chunk LMS fails to answer, or the feed itself,
  gets its own "Opnieuw" instead of being counted as 100 files missing from the server; the
  "N niet gevonden op de server" note (bug report 122), "Meer laden" and the queue continuation
  from !1084/!1087 work as before, and play pressed during loading starts the feed when it is in.
  Each page of versions is drawn as it arrives. A revisit within five minutes comes from the
  entity cache. The daily mixes page shows card-shaped skeletons, and the track details sheet
  shows skeleton rows while it asks MuMa for the tags, with a retry after a failure.

<!-- release notes -->

- Daily mixes, the release radar and a song's other versions now open straight away and fill in
  while you look.
