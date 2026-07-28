# Artist Images Empty in Player UI

# status: fixed

# reported problem
`manager: artist images is empty, terwijl ik weet dat die vroeger gevuld was. mogelijk is dit een deployment issue, mogelijk een code issue. het gevolg is dat ik geen artist images heb voor artiesten in de player ui`

# Possible reason
1. **Deployment / Volume Persistence Issue**: The storage directory for artist images (configured via `STORAGE_PATH`, defaulting to `/mnt/music/artists`) or the database table `library_artist_images` may not be properly persisted across container deployments or volume mounts, causing previously cached images and database references to be lost.
2. **Missing Automatic Fetch Trigger**: Background artist image fetching (`run_fetch_missing`) may not have been triggered after a fresh deployment or database migration, leaving `primary_image_id` null across artists.
3. **Provider Failures / Rate Limits**: External artist image providers (e.g., Spotify, MusicBrainz) may have encountered rate limits or authentication failures during fetch cycles, leaving image lists empty.

# solution
1. Ensure `STORAGE_PATH` points to a persistent Docker volume that survives container recreation and deployments.
2. Verify database migration status for `library_artist_images` and `library_artists` (`primary_image_id`, `image_status`, etc.).
3. Implement or verify an automatic startup background task or explicit API trigger (`POST /api/artists/fetch-missing`) to populate missing artist images upon deployment.
