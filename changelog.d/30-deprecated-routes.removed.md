- **Breaking: nine deprecated API routes are deleted** (issue #30, bug report 084). They are
  `GET /api/about`, `GET|POST /api/rules/artist-redirects`, `DELETE /api/rules/artist-redirects/{id}`,
  `POST /api/tagger/rescan/file`, `POST /api/songs/tracks/{track_id}/split`,
  `GET /api/downloaders/schedule/{source}`, `GET /api/users/permissions` and
  `POST /api/users/sync/lms-db`. A call to one of them now gets a 404 or 405. Use
  `POST /api/users/sync/muma-server` in place of `/sync/lms-db`, and the artist curation page in place
  of the redirect routes. The production event log (976k rows back to 2026-08-13) has no call to any
  of them since they were deprecated, and no app, script or test in the repository calls them.
  `services/music_manager/deprecation.py` is deleted with them.

<!-- release notes -->

- **Nine old API routes that nothing called are deleted.** Scripts or sensors outside this repository
  that still call one get a 404. The changelog names the routes and their replacements.
