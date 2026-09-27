- **The app says what it is doing while it starts, and an artist or album opens at once** (issue
  #107, `docs/designs/perceived-performance/`). Until now a cold start showed a black page until the
  bundle had run. In the app it stayed black until the server, the session and up to 200 queued
  tracks had been restored. A tapped artist showed a bare "Laden..." until `getArtist` had
  answered, and only then asked for the tracks. `index.html` now paints a boot screen from the first
  frame: the MuMa mark, the stage ("Verbinden met de server…", "Inloggen…", "Wachtrij herstellen…"
  with a filling bar), a hint after 8 s and a retry button after 20 s. A link to an artist or album
  now leaves what it already knows (name, picture, cover, artist). The page draws its header from
  that at once, with skeleton rows and tiles where the data still has to come. The artist page
  starts `getArtist`, `getSpotifyTracks` and `getArtistInfo2` together instead of one after
  another. Each section loads, fails and retries on its own, and play pressed before the tracks
  arrive waits for them with a throbber. A revisit within five minutes renders from an in-memory
  cache and refreshes in the background. The page's main request starts on pointerdown and is
  shared with the page, one request per tap, never on hover or scroll. New building blocks:
  `entityCache.js`, `entitySeeds.js`, `entityLoaders.js`, `bootScreen.js` and
  `src/lib/loading/` (Skeleton, SkeletonRows, SkeletonTiles, Throbber, SectionState). The style
  guide's Loading States section now covers the boot screen, the optimistic page shell, section
  errors and the inline throbber.

<!-- release notes -->

- Starting the app now shows what it is doing instead of a black screen, and tapping an artist or
  album opens its page straight away while the tracks load in.
