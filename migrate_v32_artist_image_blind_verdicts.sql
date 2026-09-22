-- migrate_v30 was meant to undo the verdicts a blind fetcher wrote. It ran, and did nothing.
--
-- Its guard was global: "reset every blind `failed`, unless any provider image has landed
-- since the blackout began". That reads as "has sight returned yet?", and it is the right
-- question to ask once -- but by the time the migration first reached production, 22 Spotify
-- portraits had already been fetched by hand (2026-09-21 12:56-12:58). One `NOT EXISTS` over
-- the whole table was therefore false for all 45.044 other artists, permanently, and every one
-- of them kept a `failed` it never earned. Measured 2026-09-22: 45.066 `failed`, 36.049 of them
-- still dated 2026-08-23.
--
-- The question belongs per artist: was *this* verdict written while the fetcher could not see?
-- The window runs from the day the credentials left the image to the first portrait a provider
-- delivered after it; a verdict inside it is worthless, one after it is real. COALESCE keeps
-- the statement correct on a database where no portrait has landed yet -- the window is then
-- still open and ends now.
--
-- Self-limiting and re-runnable, which matters because scripts/deploy.sh applies this on every
-- deploy: a reset row comes back as NULL and stops matching, and a `failed` written from here
-- on is dated after the window. Manual uploads (source 'music-manager') are not sight, so they
-- do not close the window.
UPDATE library_artists
SET image_status = NULL,
    image_updated_at = NULL
WHERE image_status = 'failed'
  AND primary_image_id IS NULL
  AND image_updated_at >= '2026-08-22'
  AND image_updated_at < COALESCE(
      (SELECT MIN(i.created_at)
       FROM library_artist_images i
       WHERE i.created_at >= '2026-08-22'
         AND i.source <> 'music-manager'),
      NOW());
