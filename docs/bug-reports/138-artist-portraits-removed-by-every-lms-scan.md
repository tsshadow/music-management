# Artist Portraits Are Removed From lms.db By Every Library Scan, 0.2 s Per Row

# status: fixed

# reported problem
GitLab issue #145, found while analysing bug report 136. music-manager writes artist portraits
into LMS's `image` table itself (`routers/artist_images.sync_artist_images_to_server`), with paths
like `/mnt/music/artists/<n>/spotify-<hash>.jpg`. On every library-wide scan LMS removed about
20,000 of those rows, 0.2 s each, while every file still existed. Judging by the `image` id counter
(4.7 million for 512,000 rows) music-manager wrote them back afterwards, under new ids. The issue
also asked whether artists lose their portrait in the meantime.

# Possible reason
Measured read-only on production on 2026-09-30 (container mounts, `media_library`, and a
consistent `.backup` snapshot of `lms.db` copied to the workstation):

**What LMS's removed-files check does.** `ScanStepCheckForRemovedFiles` walks every row of
`track`, `image`, `track_lyrics`, `playlist_file` and `artist_info` in 200-row batches. Files under
LMS's cache directory are skipped. For every other row it asks, from inside the LMS container:

1. does the path exist, and is it a regular file? If not: "missing".
2. does it lie under a media library root (`media_library.path`), with no folder containing
   `.lmsignore` on the way? If not: "out of media directory".
3. does a scanner still handle the extension? If not: "file format no longer handled".

Any "no" deletes the row. Nothing about who wrote the row, or which media library it has, plays a
part: the path is all it reads.

**Why the portraits failed it.** LMS mounts the share at `/music`, music-manager at `/mnt/music`.
`/mnt/music/...` does not exist inside the LMS container, so every portrait row failed test 1.

**LMS already has the same files.** Production has one media library, root `/music`, and
`/music/artists` (43,000 folders) lies inside it without a `.lmsignore`. LMS's own scanner had
therefore indexed every portrait file itself: 447,317 `image` rows under `/music/artists/`, each
with its own `artwork` row. Each of the 6,376 portrait rows still under `/mnt/music` at snapshot
time had a twin under `/music` (checked by the repair below). So writing the LMS spelling adds
nothing new: the sync finds LMS's own row and uses it.

**Why each removal took 0.2 s.** Deleting an `image` deletes its `artwork` row, and SQLite then sets
`preferred_artwork_id` to NULL in `artist`, `medium`, `release` and `track`,
`preferred_media_artwork_id` in `track`, and `artwork_id` in `podcast` and `podcast_episode`. None
of those seven columns had an index, so every removal scanned `track` (342,933 rows) twice and the
other tables once. On a copy of the snapshot (workstation, `PRAGMA foreign_keys=ON`, 50 rows per
transaction like LMS):

| | 50 image rows | per row |
|---|---|---|
| before | 34 - 46 s | 0.7 - 0.9 s |
| with the seven indexes | 3 - 4 ms | under 0.1 ms |

Creating the seven indexes on that copy took about 1 s in total.

**Portraits were missing in between.** In the snapshot, taken during the removal, 271 LMS artists
pointed at a music-manager portrait. music-manager has 42,099 artists with one. 51,374 LMS artists
had no artwork at all. The web player falls back to music-manager's own image route, which hid
much of this. Other Subsonic clients got nothing.

# solution
Both parts from the issue.

**The portrait rows use LMS's path** (`services/music_manager`):

- `library_paths.server_path()` maps a path under `MUMA_MUSIC_ROOT` onto `LMS_MUSIC_ROOT`. It is
  the one helper for "a path muma *writes* into lms.db", next to `candidate_paths()`, which
  already covers reading (the rating webhook and the version sync). A path under neither root,
  or one already in LMS's spelling, is left as it is.
- `sync_artist_images_to_server` looks up and inserts the portrait under `server_path(cached_path)`.
  On production that finds LMS's own row and its artwork, so nothing is inserted. If music-manager
  gets there first, the row it writes is the one LMS's image scanner later finds by path and fills
  in (directory, write time) rather than adding a second one (`ImageFileScanOperation` only creates
  when `Image::find(path)` finds nothing).
- `_unset_cleared_artwork_on_server` matches both spellings of a cleared portrait, so it still
  finds rows an older sync wrote.
- One-time repair, `lms_portrait_paths.repair_portrait_paths()`, run at the start of every portrait
  sync (hourly and after startup) and idempotent. For each `image` row under muma's mount:
  - no row under LMS's spelling yet: rename in place. The image id, the artwork and every artist
    pointing at it stay as they are.
  - LMS already indexed the file: renaming would give one path two rows, and `Image::find(path)`
    expects one. So the artists on the old row's artwork are moved onto LMS's artwork for the same
    file. The old row is left for LMS's removed-files check to delete, which is cheap once the
    indexes below exist. The repair does not delete it itself: without `PRAGMA foreign_keys` the
    cascade would not run, and with it the write lock would be held for the unindexed cascade.
  - Write discipline from `lms_writes` (bug report 129): reads happen outside any transaction,
    batches of at most 100 rows take the lock up front with `BEGIN IMMEDIATE`, and the first busy
    batch ends the pass. The rows are still there, so the next hourly sync picks them up.
  - All artists on old rows are read in one query. Asking per row scanned the unindexed `artist`
    table 6,376 times: 46 s per pass on the snapshot copy. Now a pass takes 0.07 s. The first pass
    moved 271 artists and renamed none. The second wrote nothing.
- Rejected alternatives. A `.lmsignore` in `/music/artists`, or keeping portraits outside the
  library root: the check would then remove the rows as "out of media directory". Teaching the
  check to skip rows without a directory or media library: a row music-manager writes is no
  different there from one LMS left half-written, and it adds a second kind of image to LMS for no
  gain, since LMS already indexes the files.

**Indexes in LMS** (`services/music-management-server/src/libs/database/impl/Session.cpp`):
`artist_preferred_artwork_idx`, `medium_preferred_artwork_idx`, `podcast_artwork_idx`,
`podcast_episode_artwork_idx`, `release_preferred_artwork_idx`, `track_preferred_artwork_idx`,
`track_preferred_media_artwork_idx`. They sit in `createIndexesIfNeeded()`, like every other index
in this tree, including those for columns a migration added (`track_form_idx`, `track_work_id_idx`).
It runs on every start with `CREATE INDEX IF NOT EXISTS`, so an existing database gets them on the
first start of the new image. There is no `LMS_DATABASE_VERSION` bump: a migration step would add
nothing, and a bump makes an older image refuse the database, which would rule out a rollback. Any
image removal is now cheap, whatever causes it: a replaced cover, a moved release, or the old
portrait rows that are left.

Tests: `test-database` `Artwork_everyReferenceToAnArtworkIsIndexed` (every column that references
`artwork`, and `artwork`'s own two, has an index with that column first, and a database missing the
new indexes gets them from `createIndexesIfNeeded`); `test_library_paths.ServerPathTest`;
`test_lms_portrait_paths` (real WAL SQLite: rename, move onto LMS's row, duplicates, second pass
writes nothing, busy server loses nothing, batch size, non-lock errors raised);
`test_artist_images_router` (the sync writes LMS's path, the repair runs first, a failing repair
does not stop the sync, a cleared portrait under LMS's spelling is still unset);
`tests/integration/test_router_sql.py::test_the_portrait_sync_writes_the_path_the_server_sees`.

Not fixed here, filed as GitLab issue #146: on every scan with changes, LMS's
`ScanStepAssociateArtistImages` recomputes each artist's `preferred_artwork_id` from its own
sources (an MBID-named image, `artist.jpg`, or a release cover) and overwrites whatever
music-manager set, until the next hourly portrait sync sets it back. Image ids are stable after
this fix, but the artist pointer still flips back and forth.
