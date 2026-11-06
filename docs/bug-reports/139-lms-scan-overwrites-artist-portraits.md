# LMS's Artist-Image Step Overwrites The Portrait music-manager Set, On Every Scan With Changes

# status: fixed

# reported problem
GitLab issue #146, found while fixing bug report 138. music-manager's portrait sync
(`routers/artist_images.sync_artist_images_to_server`, hourly and after startup) points each LMS
artist's `preferred_artwork_id` at the artwork of the portrait music-manager chose. Since 0.85.4
those portraits are files LMS indexes itself (`/music/artists/<n>/spotify-*.jpg`), so the image ids
are stable. The issue expected the pointer itself to flip anyway: LMS's own
`ScanStepAssociateArtistImages`, which runs on every scan with changes, works out each artist's
artwork from LMS's own sources and overwrites whatever differs, until the next hourly sync sets it
back.

Separately, the repair pass from bug report 138 logged
`lms_portrait_paths.py:142 [INFO] unknown: portrait path repair ...`, where the server's name
(`server-stable`) belongs.

# Possible reason
**The step.** For each artist, `ComputeArtistArtworkAssociationsJob::run` computes an artwork in
this order: an image named after the artist's MBID anywhere in the library; an image next to its
artist-info file; `artist.jpg` (`artist-image-file-names`) in or above its release folders; and,
with `artistImageFallbackToRelease`, the first release's cover. None of these finds
`/music/artists/<muma id>/spotify-<hash>.jpg`: that folder is named after music-manager's artist
id, not after anything LMS knows. Whenever the result differs from the current pointer
(`artist->getPreferredArtwork() != preferredArtwork`), it is written, NULL included.

**How often.** `needProcess` is true for every scan with at least one change. The downloader and
tagger announce the folders they touch, and each announcement is a scoped scan: on production on
2026-09-30 LMS logged a scan with `Changes = 1` roughly every two and a half minutes. Every one
of them runs the step over all 55,600 artists.

**Measured read-only on production**, 2026-09-30, 0.85.4 live since 11:28 UTC
(a throwaway script run in the music-manager container: MariaDB's primary portrait per artist,
`library_artists.primary_image_id` -> `library_artist_images.cached_path` mapped with
`server_path`, against lms.db opened `mode=ro`, `artist.preferred_artwork_id` -> `artwork` ->
`image.absolute_file_path`, joined on artist name):

| moment (UTC) | muma artists with a portrait | in LMS by name | pointing at that portrait | NULL | LMS's own choice |
|---|---|---|---|---|---|
| 11:28:14 | sync: "Synced 42100 artist images" | | | | |
| 11:29 - 11:34 | three scoped scans, `Changes = 1` each | | | | |
| 11:34:19 | 42,100 | 39,624 | **0** | 39,476 | 148 |
| 12:29:31 | next hourly sync: "Synced 42100 artist images" | | | | |
| 12:29:32 | 42,100 | 39,624 | **39,591** | 33 | 0 |
| 12:30:08 | next scoped scan, `Changes = 2` | | | | |
| 12:30:16 | 42,100 | 39,624 | **0** | 39,476 | 148 |

(2,509 muma artists have no LMS artist of the same name; they are outside what either side can
fix here.) Right after a sync nearly every artist points at its portrait; 44 seconds later the
first scan with changes has taken every one of them back. 39,476 end up with no artwork at all,
148 on a release or podcast cover (e.g. Antenora on
`/music/EPs/Triple Six Records/TSR010 .../cover.jpg`).

So the pointer does not flip "for up to an hour": it is correct only from the sync until the next
scan with changes, seconds to a few minutes, and wrong for the rest of the hour. The web player hides this
because it falls back to music-manager's own image route; every other Subsonic client (MuMa Mobile,
Android Auto) sees a release cover or no picture.

**The log label.** `sync_single_server_db(muma_conn, db_path, source)` knows the server's name, but
called `sync_artist_images_to_server(muma_conn, sqlite_conn)` without it, which called
`repair_portrait_paths(server_conn)`, whose `source` defaults to `'unknown'`.

# solution
Decided in the issue: LMS keeps an artist's preferred artwork when it already points at a managed
portrait, and only computes its own choice when the artist has none.

**LMS** (`services/music-management-server/src/libs/services/scanner/impl/steps/ScanStepAssociateArtistImages.cpp`):

- New setting `artist-image-managed-directory` (lms.conf), overridable like every LMS setting with
  the environment variable `LMS_ARTIST_IMAGE_MANAGED_DIRECTORY`. Empty by default, which is
  upstream behaviour. A relative path is logged and ignored.
- Before computing anything, the job reads the artist's current artwork. If it is a standalone
  image (not an embedded track picture) whose path lies under the managed folder
  (`core::pathUtils::isPathInRootPath`, component-wise, so `/music/artists-old` is not inside
  `/music/artists`), the artist is skipped: no computation, no association, no write.
- Every other artist goes through the old path unchanged, including the "only write what differs"
  comparison bug report 132 depends on.
- "The current one is gone": when a portrait file disappears, the removed-files check deletes its
  `image` row, the delete cascades to `artwork`, and SQLite sets `artist.preferred_artwork_id` to
  NULL (indexed since bug report 138). The artist then has none, and the next run of the step gives
  it LMS's own choice. The step does not stat the file itself: that would be 40,000 `stat` calls on
  the network share on every scoped scan, every few minutes. Between the file's removal and the
  next library-wide scan the artist keeps a pointer to a missing file, exactly as any other image
  in LMS would; in practice music-manager replaces the pointer when it changes a primary portrait,
  well before that.

**Where the folder comes from.** The LMS stack and music-manager are separate compose files and
LMS cannot read music-manager's environment, so the value is set on the LMS side and checked
against music-manager's: `services/music-management-server/docker-compose.yml` passes
`LMS_ARTIST_IMAGE_MANAGED_DIRECTORY=${LMS_ARTIST_IMAGE_MANAGED_DIRECTORY:-/music/artists}`, and
`tests/ci/test_managed_portrait_directory.py` derives the expected value from music-manager's
`STORAGE_PATH` (`/mnt/music/artists`) and the two music mounts (`/mnt/music`, `/music`), and fails
when either compose file (or `docker/compose.test.yml`) moves on its own. Documented in
the operator's runbook.

**music-manager**: `sync_artist_images_to_server(muma_conn, server_conn, source)` takes the server
name and hands it to `repair_portrait_paths`; `sync_single_server_db` passes its `source`.

Rejected: running music-manager's sync right after every LMS scan (shortens the window, never
closes it, and writes to lms.db every few minutes); making `/music/artists/<muma id>/` one of LMS's
own sources (the folder name maps to no LMS artist, so music-manager would have to write MBID-named
files or markers).

Tests: `test-scanner` `AssociateArtistImagesTest` (a real SQLite database, the real step and job
scheduler): an artist on a managed portrait keeps it and is not written; an artist without one gets
the MBID image and a second run writes nothing; an artist on a cover or on a look-alike folder is
recomputed as before; an artist whose managed portrait's image row was removed gets a new choice;
with the folder unset, or relative, every artist is recomputed.
`test_lms_portrait_paths.test_the_log_line_names_the_server`,
`test_artist_images_router.test_the_repair_log_names_the_server`,
`test_users_endpoints.SyncSingleServerDbTest`, `tests/ci/test_managed_portrait_directory.py`.

Verify on production after the deploy: run the measurement again just after an hourly portrait
sync and again after the next scan with changes. "pointing at that portrait" should stay at the
figure the sync reached (about 39,600) instead of dropping to 0.
