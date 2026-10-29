- **Pillow goes to 13.0, which fixes 39 advisories in its image parsers.** The artist image
  fetcher opens photos from external sources with Pillow 12.3, whose JPEG, TIFF, GIF, PDF and
  OpenJPEG code had buffer overflows and decompression-bomb bypasses (among them
  GHSA-78g4-xqwv-q3g8). The fetcher only opens, scales and saves images, so none of the 13.0
  breaking changes touch it.
- **The frontend's dev tooling gets undici 8.12.3.** 8.12.1 had eight advisories, the worst a TLS
  certificate check that an `Agent` could drop. The scheduled dependency audit failed on it; only
  the build and tests use undici, not the shipped bundle.
<!-- release notes -->
- Security updates for the image library behind artist photos (Pillow 13.0) and for a build tool.
