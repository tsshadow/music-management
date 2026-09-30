- **LMS no longer replaces the artist portrait music-manager chose on every scan with changes.**
  music-manager's hourly sync points each artist at its portrait, and LMS's artist-image step,
  which runs on every scan that found a change (every few minutes on production, for the folder
  scans the downloader and tagger announce), worked the artwork out again and overwrote it with a
  release cover or with nothing. Measured on production on 0.85.4: right after the hourly sync
  39,591 artists pointed at their portrait, 44 seconds later, after the next folder scan, 0. LMS
  now keeps an artist's artwork when it is an image under the managed portrait folder
  (`LMS_ARTIST_IMAGE_MANAGED_DIRECTORY`, `/music/artists` on the lms stack) and only chooses one
  itself for artists without one. The portrait-path repair's log line also names the server
  (`server-stable`) instead of `unknown` (bug report 139).

<!-- release notes -->

- **Artist portraits no longer flip back to album covers.** Other apps than the web player
  showed a release cover, or no picture, for most artists within minutes of every portrait sync.
