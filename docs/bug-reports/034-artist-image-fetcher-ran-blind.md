# The Artist-Image Fetcher Ran Without Credentials For A Month And Marked 45.000 Artists As Unfindable

# status: fixed — a provider without its credential is not asked, a run with no provider records nothing, the blind verdicts are reset by migrate_v30, and the keys now reach the container

# reported problem
After MR !884 (track rows fall back to the artist's portrait) the Home shelves still showed
title panels for Soulblast, Gabberhead, MYST. Measured on production, 2026-09-21:

| image_status | artists | last `image_updated_at` |
|---|---|---|
| active | 11.759 | 2026-07-26 |
| failed | 44.972 | 2026-08-22 → 2026-09-20, every day, not one `active` among them |
| null | 76 | — |

Sefa, Partyraiser, Dr. Peacock, Warface, Miss K8, Tha Playah, Evil Activities: all `failed`,
all dated 2026-08-22/23. Not one row in `library_artist_images` was created after July. The
last bulk run reported `Completed: 0 succeeded, 32 failed`.

`GET /api/config` on production: `spotify_client_id`, `spotify_client_secret`,
`lastfm_api_key`, `discogs_token` all empty. `docker exec music-manager env`: no `SPOTIFY_*`
at all.

# Possible reason
Three things, stacked:

1. **The credentials only ever reached the container inside the `.env` the image used to
   `COPY`.** `fetcher.py` calls `load_dotenv()`, and the July run had a `/app/.env` to read.
   `5553bc898` (2026-07-24, "remove faulty .env COPY from music-manager Dockerfile") took the
   file out of the image — correctly, it broke every fresh-clone build — on the stated grounds
   that "all runtime configuration is already injected via the container environment block".
   `SPOTIFY_CLIENT_ID` never was: `docker/docker-compose.yml` did not list it. The first fetch
   run on the image without the file was 2026-08-22.
2. **A provider without its credential answered an empty list, which the fetcher read as "I
   looked, there is nothing".** `SpotifyArtistImageProvider.get_artist_images` returned `[]`
   for a missing token, a 401, a 429, a 5xx and a network error alike — the same value as a
   search with no hits. `fetch_for_artist` then wrote `image_status = 'failed'` and moved on.
   Nothing distinguished "nobody could answer" from "everybody answered no".
3. **The Beheer > Config page had fields for exactly these keys, and nobody read them.**
   `ConfigStore` declares `spotify_client_id` and friends, but the fetcher's providers and the
   tagger's `ExternalArtistLookup` each read `os.getenv` directly. And even a value entered
   there died on the next redeploy: `ConfigStore` writes `data/config.json` under `/app/data`,
   which `docker-compose.yml` mounted only three sub-paths of — the directory itself lived in
   the container's own layer.

A side finding: `GET /api/artists/{name}/image` attached `trigger_fetch` as a background task
and then raised the 404. Starlette drops the background tasks of an exception response, so
that lookup never ran once — which is also why it never mattered that each miss would have
queued a MusicBrainz + Spotify round trip.

# Fix
- `services/common/config_store.credential(config_key, env_name)`: the config page's value,
  then the environment, then `None`. Every consumer of a Spotify/Last.fm/Discogs key reads it.
- `ArtistImageProvider.configured` and `ProviderUnavailable`. Spotify and Last.fm raise it for
  a missing or rejected credential, a rate limit, a 5xx, a transport failure or an unreadable
  body; only a 200 with no hits (or a 404 on a known Spotify id) is the empty list.
- `ArtistImageFetcher.configured_providers` / `.blind`: an unconfigured provider is not asked;
  a run with no configured provider (the SoundCloud stub does not count) looks nothing up and
  writes no status; an artist for whom any provider could not answer keeps its status and is
  asked again next run. `run_fetch_missing` stops before the loop with a message the Beheer page
  shows.
- `migrate_v30_artist_image_blind_failures.sql` resets `failed` rows dated on or after
  2026-08-22 to "never asked", and keeps doing so on every deploy until the first provider image
  lands after that date — then it is a no-op and later `failed` verdicts are real.
- `docker/docker-compose.yml`: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `LASTFM_API_KEY`,
  `DISCOGS_TOKEN` pass through from the stack env, and `${HOST_DATA_PATH}/music-manager` is
  mounted on `/app/data` so the config page survives a redeploy.
- The 404 route no longer pretends to schedule a lookup.

# To bring the portraits back
Set the Spotify client id and secret — in the Portainer stack env (they pass through now) or on
Beheer > Config (persisted now) — then start the bulk run from the Beheer artist-image page or
`POST /api/artists/fetch-missing`. The reset rows are eligible immediately; the run reports a
"no provider configured" failure instead of walking the list if the keys are still missing.
