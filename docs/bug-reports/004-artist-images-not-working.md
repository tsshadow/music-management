# Artist Images Not Working (Manager Tab & Player)

# status: fixed

# reported problem
Artist images are not shown in the manager tab (`ArtistImagesTab`), and consequently not in the
player's Artists view either, even though the images are correctly stored at `/mnt/music/artists`
on production (confirmed: `library_artists`/`library_artist_images` correctly reference ~11.7k
cached image files on disk).

# Possible reason
Two independent bugs were found:

1. **Manager tab (root cause of the reported symptom)**: `ArtistImagesTab.svelte` requested
   `${API_BASE}/api/artists/{name}/image` without any authentication (no `X-API-Key` header, no
   `apiKey`/`u`/`p` query params). `music_manager`'s `/api/artists/{name}/image` route requires
   `verify_api_key`, and LMS's `MumaResource` `/api/*` proxy also requires the request to be
   authenticated before forwarding — so every image request returned `401 Unauthorized`, which the
   browser renders as a broken image.
2. **LMS DB sync path mismatch (production deployment only)**: `docker/docker-compose.yml` mounted
   `${HOST_DATA_PATH}/music-management-server/var/lms` and
   `${HOST_DATA_PATH}/alpha-music-management-server/var/lms` into `music-manager`'s
   `/app/data/stable` and `/app/data/alpha`. On production `HOST_DATA_PATH=/docker/music-management`,
   but the separate `lms` stack (`services/music-management-server/docker-compose.yml`) actually
   stores its SQLite DB at `/docker/lms/var/lms/lms.db` and `/docker/alpha-lms/var/lms/lms.db` (its
   own `DOCKER_DATA_PATH`, default `/docker`). The mounted directories were therefore always empty on
   production, so `run_lms_db_sync()`/`sync_artist_images_to_server()` never found an `lms.db` to
   write into — the player's native `artist.preferred_artwork_id`/`coverArt` was never populated by
   this path. This did not fully explain the player symptom (the player's own image URL logic already
   falls back to the authenticated muma proxy path, which works once bug 1 is fixed), but it silently
   broke a legitimate feature (native image sync, plus playlist import) and is corrected as part of
   this fix.

# solution
1. `ArtistImagesTab.svelte`: pass the manager's `apiKey` down from `Management.svelte` and append it
   as `?apiKey=...` on both artist-image `<img>` sources.
2. `docker/docker-compose.yml`: mount the `music-manager` service's `/app/data/stable` and
   `/app/data/alpha` from the *actual* LMS/alpha-LMS host data directories (new
   `${LMS_DATA_PATH:-/docker/lms}`/`${ALPHA_LMS_DATA_PATH:-/docker/alpha-lms}` variables, defaulting
   to the real production paths) instead of a path under this stack's own `${HOST_DATA_PATH}` that
   never existed.
