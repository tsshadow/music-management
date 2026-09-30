- **Artist portraits are no longer removed from LMS and written back on every library scan.**
  music-manager wrote each portrait into LMS's database under its own mount (`/mnt/music/...`).
  Inside the LMS container that path does not exist, so every library scan removed about 20,000
  portrait rows at 0.2 s each, more than an hour per scan, and most artists had no portrait until
  the hourly sync wrote the rows back. The sync now uses the path LMS sees (`/music/...`), which
  is usually a row LMS's own scanner already made for the same file. A repair pass moves the rows
  written earlier. LMS also gets indexes on the seven columns that point at an artwork, so
  removing an image now takes microseconds instead of 0.2 s, whatever the reason for the removal
  (bug report 138).

<!-- release notes -->

- **Artist portraits stay put during a library scan.** Most artists lost their portrait while
  LMS scanned the library, and the scan spent more than an hour removing them.
