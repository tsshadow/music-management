- **Settings loads only the tab you open, and Now Playing left the web player's first file
  without opening any slower** (issue #119, `docs/designs/perceived-performance/technical.md`
  section 7). The settings page was one 79 kB chunk with all five tabs in it; each tab is its own
  chunk now, so opening settings on General fetches 36 kB instead of 81 kB (9 kB instead of
  18 kB gzip) and a browser never fetches the device tab. A tab still loading shows its own shape
  in skeleton blocks, and the next tab in the list is fetched in the background. The full-screen
  Now Playing moved out of the entry chunk; the mini player stays in it, the view is fetched on
  idle after the first frame and the moment a finger touches the mini player, and if it is still
  on its way a seeded stand-in draws the same screen at once -- cover, title, artist and a working
  play/pause -- so opening it never waits. The entry went from 300 kB to 255 kB (89 to 76 kB
  gzip); everything loaded before the first screen from 420 kB to 405 kB (137 to 133 kB gzip).
<!-- release notes -->
- The settings page opens faster, and the web player's start-up code shrank again while Now
  Playing still opens instantly.
