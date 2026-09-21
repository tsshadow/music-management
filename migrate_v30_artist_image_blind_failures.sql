-- 45.000 artists were recorded as having no findable portrait by a fetcher that could not see.
--
-- From 2026-08-22 the artist-image fetcher ran without a single provider credential: the
-- Spotify client id and secret had only ever reached the container inside the .env the image
-- used to COPY, and that COPY went on 2026-07-24. Every provider answered "no candidates" to
-- every name, and the fetcher wrote `image_status = 'failed'` for each -- Sefa, Partyraiser,
-- Dr. Peacock, Warface, Miss K8 among them. Measured 2026-09-21: 11.759 artists with a
-- portrait, all dated July or earlier; 44.972 `failed`, all dated 2026-08-22 or later; not one
-- image stored since. The fetcher no longer records a verdict without a provider
-- (ProviderUnavailable, `ArtistImageFetcher.blind`), and this puts the verdicts it had no
-- right to give back to "never asked", so the start-up run asks again once the credentials
-- are in place.
--
-- Re-runnable on every deploy, and self-limiting: the reset only applies while no provider
-- image has landed since the blindness began. The first portrait Spotify delivers after the
-- credentials return turns this into a no-op, so a `failed` written by a sighted fetcher from
-- then on is a real verdict and stays. Manual uploads (source 'music-manager') do not count as
-- sight.
UPDATE library_artists
SET image_status = NULL,
    image_updated_at = NULL
WHERE image_status = 'failed'
  AND primary_image_id IS NULL
  AND image_updated_at >= '2026-08-22'
  AND NOT EXISTS (
      SELECT 1
      FROM library_artist_images i
      WHERE i.created_at >= '2026-08-22'
        AND i.source <> 'music-manager'
  );
