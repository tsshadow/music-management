- **The web player's first screen loads another 70 kB less, and its translation file no longer
  waits for the app's code** (issue #118, `docs/designs/perceived-performance/technical.md`
  section 7). The artist, album, feed, preset and playlist pages, the filter bar and the
  collection grid and bar were still in the entry chunk; they are chunks of their own now, fetched
  on idle after the first frame and, for artist, album and feed links, the moment a finger goes
  down together with the page's data. The artist and album heading still appears at once: until
  the page's code is in, a small seeded stand-in (`EntityPageShell`) draws the same header from
  what the tapped link knew. `index.html` now carries a `modulepreload` for the listener's locale
  file, so the browser fetches it together with the entry instead of one round trip later. The
  entry went from 370 kB to 300 kB (107 to 89 kB gzip); everything the first screen waits for,
  one locale included, from 580 kB to 511 kB (184 to 168 kB gzip).
<!-- release notes -->
- The web player starts a little faster again, and artist and album pages still open instantly.
