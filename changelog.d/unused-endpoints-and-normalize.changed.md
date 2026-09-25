- **Nine API routes that nothing in the repository calls are deprecated, and three redundant aliases are removed.**
  The deprecated routes are `GET /api/about`, the three `/api/rules/artist-redirects` routes,
  `POST /api/tagger/rescan/file`, `POST /api/songs/tracks/{id}/split`,
  `GET /api/downloaders/schedule/{source}`, `GET /api/users/permissions` and
  `POST /api/users/sync/lms-db`. They still work and are flagged `deprecated` in the OpenAPI
  schema. The first call to each one per process now logs an INFO event naming the caller, so any
  real use shows up in `/api/events`. Routes that stay unused are deleted on 2026-11-01. The
  removed aliases are `GET|PUT /api/users/{id}/lb-account` (use `/listenbrainz`),
  `POST /api/users/sync/lms` (use `/sync/muma-server`) and `POST /api/rating/server-event` (use
  `/lms-event`, which LMS calls). **Breaking** only for a client outside this repository that
  still calls one of those three aliases. `/api/listening/clock`, `/api/listening/sources`,
  `/api/curation/retag` and `/api/rating/ratings/{username}` were on the audit list but have a
  consumer and stay. See bug report 084.
- **Five identical genre-style name keys now share one implementation in
  `services/common/text_normalize.py`.** They are in `GenreRulesHelper`, `GenreNameAnalyzer`,
  `PodcastHelper`, `curation_rules`, plus the padded variant in `FestivalHelper`. The artist key
  in `ArtistNameAnalyzer` also moved there. A characterisation table pins every normalizer's
  output on the same tricky inputs, and none of it changed. The scrobble matcher, the artist image
  fetcher and `Tag.set` normalize differently on purpose and now say why.
  `scripts/restore_lms_ratings.py` imports `candidate_paths` instead of carrying a copy.
