# Endpoints without a consumer, and eight copies of `normalize()`

# status: fixed

# reported problem

The September 2026 repository audit raised two maintenance findings.

**C5, endpoints without a code consumer.** It listed `GET /api/listening/clock`,
`GET /api/listening/sources`, `/api/rules/artist-redirects`, `POST /api/tagger/rescan/file`,
`GET /api/about`, `POST /api/curation/retag`, `POST /api/songs/tracks/{id}/split`,
`GET /api/downloaders/schedule/{source}`, `GET /api/users/permissions`, `POST /api/users/sync/lms`,
`GET /api/rating/ratings/{username}`, and the aliases `/lb-account` and `/server-event` as having no
caller in the code base. Dead routes are attack surface and maintenance cost. But deleting a route only
because nothing in the repository calls it is a guess: a Home Assistant sensor, a one-off script or a
bookmark can still call it.

**C6, eight `normalize()` implementations.** These were `ArtistNameAnalyzer.normalize`,
`GenreNameAnalyzer.normalize`, `GenreRulesHelper.normalize`, `FestivalHelper.normalize`,
`PodcastHelper.normalize`, `scrobble_matching.normalize`, `ArtistNameNormalizer.normalize`
(artist image fetcher) and the inner `normalize` in `Tag.set`. On top of those, `candidate_paths`
existed twice, once in `services/music_manager/library_paths.py` and once as a copy in
`scripts/restore_lms_ratings.py`. Copies drift. Nobody could say which copies were meant to behave
the same and which were meant to differ.

# Possible reason

**C5.** Routes outlived the UI that used them. The About tab and the old Tagger tab were removed
from the management page (an agent plan, since removed),
and the artist curation page took over redirects. Aliases were kept "for compatibility" after the
LMS -> MuMa server rename, and nobody went back to remove them. Two of the listed routes turned out
to have a consumer after all. The audit's grep looked for literal paths, but the web player builds
them: `listeningStats.js` calls `get("clock")` and `get("sources")` on a base URL, and
`curationApi.js` calls `write("/retag", ...)` below `/api/curation`.

**C6.** Each helper was written with a copy of the genre key "to avoid importing a module that
needs a database driver" (the comment in `GenreNameAnalyzer`). No shared module without such
imports existed, so copying was the cheapest route every time. `restore_lms_ratings.py` is run as
a file, so its author copied `candidate_paths` rather than fix the import path.

# solution

## C5: re-verified against develop

The search covered `services/frontend/src` (including dynamically built URLs), `services/muma-mobile`
(Kotlin/Retrofit paths), `services/music-management-server` (C++), `scripts/` (nightly check,
crash triage, migrations), `tools/`, `docs/` (Home Assistant and design docs), `tests/contracts`,
`tests/bdd` and `tests/integration`.

Production usage could not be checked. nginx access logs are not reachable from an agent. The
`events` table is not an access log. The read-only production tool was unavailable during this
change (`prod_containers` returned an error), so no container logs were read either. That gap
is why the routes without a consumer were deprecated first and deleted only after a removal
period (see "Removal" below).

| Endpoint | Consumer found | Decision |
|---|---|---|
| `GET /api/listening/clock` | Web player: `listeningStats.js` `get("clock")` (statistics page) | Keep |
| `GET /api/listening/sources` | Web player: `listeningStats.js` `get("sources")` (statistics page) | Keep |
| `POST /api/curation/retag` | Web player: `curationApi.js` `retag()`, called from `ArtistEdit.svelte` and `LabelEdit.svelte` | Keep |
| `GET /api/rating/ratings/{username}` | `tests/bdd` rating round trip and unrated-playlist steps (the pipeline-gating chain test), `docs/designs/wrapped/research.md` | Keep. The chain test depends on it. The stale design-doc claim that the frontend reads it was corrected |
| `GET\|PUT /api/users/{id}/lb-account` | None. Alias of `/listenbrainz`, which the web player uses (`UsersTab.svelte`, `Management.svelte`) | Removed |
| `POST /api/users/sync/lms` | None. Alias of `/sync/muma-server`, which the web player uses (`UsersTab.svelte`) | Removed |
| `POST /api/rating/server-event` | None. Alias of `/lms-event`, which LMS (`MusicManagementBackend.cpp`, `lms.conf`) and `scripts/migrate_lms_history.py` call | Removed |
| `POST /api/users/sync/lms-db` | None (not in the audit list; the same alias as `/sync/lms`) | Deprecated, then removed (issue #30). It was the documented primary name, so it got a removal period instead of disappearing at once |
| `GET /api/about` | None. `AboutTab.svelte` was deleted in the management regrouping | Deprecated, then removed (issue #30) |
| `GET\|POST /api/rules/artist-redirects`, `DELETE .../{id}` | None. The artist curation page writes redirects through `/api/curation/artists/...` | Deprecated, then removed (issue #30) |
| `POST /api/tagger/rescan/file` | None | Deprecated, then removed (issue #30) |
| `POST /api/songs/tracks/{id}/split` | None outside its own tests. The song-versions UI was never wired to it | Deprecated, then removed (issue #30) |
| `GET /api/downloaders/schedule/{source}` | None | Deprecated, then removed (issue #30) |
| `GET /api/users/permissions` | None outside its own tests | Deprecated, then removed (issue #30) |

"Deprecated" meant three things for the period before removal. `deprecated=True` put the flag
in the OpenAPI schema. A dependency, `services/music_manager/deprecation.py` (`DEPRECATED_CALL`),
logged one INFO line the first time a route was called in a process, on logger
`music-manager.deprecation`, so the line landed in the `events` table. And
`docs/api-specification.md` listed every deprecated route with the removal date 2026-11-01.

## Removal (issue #30)

On 2026-11-11 a read-only query of the production `events` table (976k rows, the oldest from
2026-08-13) found no row with logger `music-manager.deprecation` and no title that contains
"deprecat". No deprecated route was called in that window. A new search of the monorepo found no
consumer either: the web player, MuMa Mobile, the LMS proxy and its route tests, `tools/`,
`scripts/`, `tests/contracts` and `tests/bdd`.

All nine routes are deleted, with their handlers, their unit and integration tests, and the
helpers only they used (`ArtistRedirect`, `_refuse_bad_redirect_target`). The artist curation
page is the one writer of redirects left, and it refuses a rejected target itself.
`deprecation.py` and its test are deleted too, because no route uses them any more. `services/music_manager/tests/test_route_mounts.py`
(`RemovedRouteTest`) fails if one of the thirteen removed routes is published again, or if one of
the routes a consumer uses disappears.

## C6: characterised first, then consolidated

`services/common/text_normalizeTest.py` was written first. It runs every implementation on one
table of 24 tricky inputs: empty/`None`, casing, double and edge whitespace, `&`, `feat.`/`ft.`/
`featuring`, `Beyoncé`, `Øystein Sevåg`, `Straße`, curly and straight apostrophes, a leading "The",
emoji, Cyrillic, `_`, dotted initials, a zero-width space, the `ﬁ` ligature and `Ⅳ`. It pins the
output each implementation had at the time. The table passed against the untouched code, the call
sites were then switched over, and the same table still passes.

The tables show three behaviours that are identical and four that differ on purpose:

- **Identical, now shared.** `GenreRulesHelper.normalize`, `GenreNameAnalyzer.normalize`,
  `PodcastHelper.normalize` and `curation_rules.normalize_genre` (a fifth copy the audit missed)
  now call `text_normalize.ascii_name_key`. `FestivalHelper.normalize` and `PodcastHelper.padded`
  now call `padded_ascii_name_key`. `ArtistNameAnalyzer.normalize` now calls `unicode_name_key`.
  Each keeps its name and signature, so no caller changed. `services/common/text_normalize.py`
  imports only the standard library, which removes the reason `GenreNameAnalyzer` kept a copy.
- **Different on purpose, left alone with a docstring.**
  - The artist key keeps non-Latin letters, and `Ø` and `ß`, which the genre key drops. The
    library holds Cyrillic artists, and an ASCII key would collapse them to `''`.
  - `scrobble_matching.normalize` casefolds (`Straße` -> `strasse`), folds every spelling of
    "featuring", deletes intra-word apostrophes and dots (`A.B.C.` -> `abc`), and keeps `_`. It
    matches free-text titles from other players. Each of those rules would merge names that
    curation keeps apart.
  - `ArtistNameNormalizer.normalize` only lowercases, spaces `_` and `-`, and cuts platform
    suffixes ("Official", "Records"). Accents and punctuation are part of the name a provider is
    searched with.
  - `Tag.set`'s inner `normalize` is a list cleaner (strip, drop empties), not a name key.
- None of the implementations strips a leading "The". Only `ArtistNameNormalizer.get_sort_name`
  treats it specially.

`scripts/restore_lms_ratings.py` now imports `candidate_paths` from `library_paths`. It puts the
repository root on `sys.path` itself, because it runs as a file. One small behaviour change: the
`LMS_MUSIC_ROOT` and `MUMA_MUSIC_ROOT` environment overrides now apply to the script as they do to
the service. The defaults are unchanged. `RestoreLmsRatingsTest` asserts that the function is the
shared one.

Out of scope and unchanged: `services/common/channels._normalize` (strip + lower, for set
membership), and `normalizeGenre` in the frontend, which the Python docstrings name as the same
rule as `ascii_name_key`.
