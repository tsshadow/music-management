- **The web player was slow most of the hour because LMS kept scanning the whole library for one
  file** (issue #154, bug report 141). Every download asks LMS to read its folder, about 45 times an
  hour. Each of those scoped scans read the one file in a fraction of a second and then spent about
  41 s recomputing the artwork of all 343,000 tracks, 54,000 releases, 55,000 artists and 49,000
  playlists, plus every genre count. So LMS was busy most of the time, and the default track list
  took 12-17 s instead of about 1.3 s whenever it was. A scoped scan now recomputes only what its
  folders can have changed: their tracks and the rest of those tracks' releases, the releases,
  mediums, artists and genres involved, and the playlists in the folders. It also recomputes any
  genre whose count went stale, such as the one a retagged track left. A library-wide scan is
  unchanged, and catches the rare case a scoped one leaves behind (an entity elsewhere whose cover
  image was deleted, a playlist elsewhere that lists the new file).
- **The "recent" track list no longer sorts the whole library for every page.** A new index on the
  release-date expression the list sorts by takes the query from 0.65 s to 2 ms on a copy of the
  production database. It is created at startup, so there is no database version bump.

<!-- release notes -->

- **The web player stays fast while new downloads come in.** LMS used to rescan the whole library's
  artwork and genre counts for every single downloaded file, which kept it busy most of the hour
  and made the track list take 12-17 s. It now only redoes what changed. The "recent" list is also
  much faster thanks to a new index.
