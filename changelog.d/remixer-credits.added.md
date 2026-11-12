- **The library now records who remixed a track.** The scanner writes a `remixer` credit in
  `library_track_artists` for each name in a file's REMIXER tag, next to the artist's `featuring`
  credit. It was always empty on production, so MuMa Wrapped's "top remixer" card had nothing to
  count. Existing tracks get their credits on the next forced rescan.
<!-- release notes -->
- **Remixers are now credited in the library**, so Wrapped can show your top remixer.
