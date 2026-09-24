# Router Key-Check Copies and Repeated Image-Provider Warnings

# status: fixed

# reported problem
Two leftovers from the September 2026 audit.

- **Audit item C2, the rest.** Eleven routers under `services/music_manager/routers/` (analytics,
  artist_images, config, feeds, library, listening, rating, scanner, scrobbler, stats, tagger) each
  defined a `verify_api_key` of their own. Some caught every exception from `verify_token` and
  answered `401 Invalid API key`, so a database outage told every client its key was wrong; bug
  report 052 and MR !934 turned the rest into thin wrappers around `routers.users.verify_api_key`,
  but every wrapper was still a place the swallowing copy could come back, and four more routers
  (songs, downloaders, radio, news) borrowed the check from one of the wrappers. Seven routers also
  had their own "connection or raise" helper (`_connect`, `_require_db`, `_connection`) answering
  a missing pool with `500` and four different messages, where the key check answers `503`.
- **The artist image fetcher repeated its setup complaints.** After bug reports 058 and 060 a run
  logs at most two `WARNING`s, but constructing an `ArtistImageFetcher` still logged "Spotify API
  credentials not found" and "Last.fm API key not found" as `WARNING` and "no configured image
  provider" as `ERROR`. `trigger_fetch_by_id` builds a new fetcher for every single-artist fetch
  from the manager, so each fetch repeated them, and each was a push on the alerts topic once the
  five-minute brake (level, source, logger) had lapsed.

# Possible reason
- The wrappers were kept "as a name tests override", and a lazy import inside each one was
  assumed to avoid an import cycle with `users.py`. `users.py` imports no other router at module
  level, so there is no cycle; `management.py`, `events.py` and `diagnostics.py` already imported
  the check directly.
- The provider constructors log whatever they find at the moment they are built, with no memory
  of having said it before in the same process.

# solution
- Every router imports `verify_api_key` from `routers/users.py`; no router defines one. `config.py`
  needs none (its routes all go through `rbac.require_permission`). Behaviour is unchanged: unknown
  key `401`, disabled account `403`, database outage `503` with `Retry-After`; RBAC untouched.
- `database.require_connection(conn)` raises `DatabaseUnavailableError` for a missing pool, which
  `main.py` answers with `503` and `Retry-After: 5`, the same as `DatabaseBusyError`. The routers'
  own helpers call it, so they keep patching `get_db_connection` in their own module.
- `providers.base.log_once(logger, key, level, message)` logs a setup complaint at its full level
  the first time in a process and at `DEBUG` after; a provider (or the fetcher) that finds its
  configuration present again re-arms the key, so a later regression is reported again. The
  Spotify, Last.fm and no-provider messages use it. The run summary is unchanged.
- `services/music_manager/tests/test_router_api_key_dependency.py` asserts `401` for an unknown key
  and `503` for three kinds of outage on one protected route per router, and that no router module
  defines its own key check.
  `services/music_manager/artist_image_fetcher/tests/test_setup_warnings.py` builds two fetchers
  without credentials and expects each complaint once at full level, then at `DEBUG`.
