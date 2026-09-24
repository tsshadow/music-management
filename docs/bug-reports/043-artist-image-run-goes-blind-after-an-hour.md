# The Artist-Image Run Goes Blind After An Hour, And The Config Store Leaks What It Should Keep

# status: fixed

# reported problem
A code review of the artist-image fetcher and the config store, after bug report 034 brought the
fetcher back, found eight defects. None was observed on production yet, because the Spotify keys
are still not set there; each would show the moment they are.

1. A bulk run over the ~45.000 artists without a portrait stops finding anything after an hour:
   every Spotify lookup answers 401 and every remaining artist is deferred.
2. Clearing a portrait in the manager is undone at the next restart: the start-up run fetches it
   again.
3. One CDN hiccup or a full disk while saving marks the artist `failed`, which hides it from the
   bulk run for 30 days although a provider had found it.
4. `manifest.json` in the artist-image storage directory is read and rewritten in full after every
   artist -- quadratic on the CIFS share, racing between concurrent runs -- and nothing reads it.
5. Last.fm's `artist.getinfo` returns the same grey-star placeholder for every artist. It was
   accepted as a candidate, and with an MBID it scored +100 as a "known match".
6. `POST /api/config` answers with the real value of every posted key, so a secret typed on the
   config page travels straight back to the browser in the clear.
7. The config store loads the environment and then `data/config.json`, and `config.json` holds
   every value -- secrets included -- as they were on the day of the first save. Disk wins over
   every later deploy, the persistent volume carries credentials in a world-readable file, the
   `db_*` fields are editable but nothing reads them, and the radio scheduler reads the LMS
   Subsonic key from the environment while the scan trigger reads the store first.
8. When LMS is down, the radio scheduler logs a WARNING per channel every five seconds -- each an
   event and an ntfy alert -- whose text is the requests error, which contains the full URL with
   `apiKey=` in the query string.

# Possible reason
1. `SpotifyArtistImageProvider._get_token` cached the first token forever and ignored
   `expires_in`; a client-credentials token lives 3600 s. A 401 raised `ProviderUnavailable`
   without retrying.
2. `/image/clear` set `image_status = 'none'`, and the fetch-missing query selects every artist
   without an image whose status is not `failed`. `main.py` runs that query at every start-up.
3. `fetch_for_artist` wrote `failed` from the `except` around download and save, although the same
   function already refuses a verdict when a provider could not answer.
   `ImageDownloader.download` retried three times back to back.
4. `_update_manifest` -- a leftover from before the database held the image rows.
5. `LastFmArtistImageProvider` took every `extralarge`/`mega` URL, and Last.fm has served only the
   placeholder (hash `2a96cbd8b46e442fc41c2b86b821562f`) since it removed artist photos.
6. `ConfigStore.update` returned `{key: self.get(key)}` -- the in-process, unmasked read.
7. `ConfigStore.__init__` called `_load_from_env()` then `_load_from_disk()`; `_persist_locked`
   wrote `{key: value for every field}`. `DatabaseConnector` and `database.py` read
   `os.getenv('DB_*')` directly. `lms_subsonic._auth_params` called `lms_api_key()` (environment
   only); `LmsScanTrigger._endpoint` read `lms_subsonic_api_key` from the store first. A stale key
   in either place authenticated one path and not the other -- a plausible part of the recurring
   "muma-radio wrong Subsonic key after deploy" reports, not verified against production.
8. `routers/radio.py` logged `e` verbatim; `requests` puts the URL into `HTTPError` and connection
   errors. `LmsScanTrigger` and the filter preview did the same, the preview also returned it to
   the browser.

# solution
1. The token is stored with its expiry and renewed 60 s early; a 401 from the API clears it and
   retries once. A second 401 is still `ProviderUnavailable`.
2. `/image/clear` sets `image_status = 'cleared'` (the column is `VARCHAR(50)`, no migration).
   The fetch-missing query and the CLI's `fetch-missing` exclude it; `fetch_for_artist` skips it
   unless `override_cleared`; `/fetch-image` passes that through as `?force=true`, which the
   manager's "search automatically" button sends. The manager labels such an artist "cleared by
   hand".
3. A failed download or save writes no status; the artist is asked again next run.
   `ImageDownloader` waits `backoff * 2**attempt` seconds (1 s, 2 s) between attempts.
4. The manifest code is removed. Existing files are left on disk and simply no longer updated.
5. URLs containing the placeholder hash are skipped.
6. `update` validates the whole payload first and returns the masked public value per key, the same
   thing `GET /api/config` shows.
7. Precedence is now: an API override, then the environment, then the default. Only overrides are
   persisted, only while they differ from env/default, in a file marked `__format__: 2` and written
   atomically with mode 0600. A pre-existing file still loads, minus entries equal to env/default,
   secrets the environment also sets, and read-only fields, and is rewritten in the new format at
   start-up. The `db_*` fields are `read_only`: shown on the page, refused by the API. The radio's
   Subsonic key comes from `LmsEndpoint.resolve_lms_api_key()`, the resolver the scan trigger now
   uses too. The rule is documented under "Runtime Configuration" in `AGENTS.md`.
8. `LmsEndpoint.redact_url()` replaces every URL query string in a message with `?<redacted>`; the
   radio scheduler, the filter preview and `LmsScanTrigger` log (and return) only redacted text. The
   radio warns once per channel per outage, then logs at DEBUG until the channel recovers, which it
   reports once at INFO.
