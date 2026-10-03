# Interviews and previews as non-music — Technical Design

> Status: **proposed, not agreed.** Implements [functional.md](functional.md) once its open
> questions are answered. Written for the two-form answer (`interview`, `preview`). A single form
> changes the names, not the shape.

## Data Model

No new column and no migration. `library_tracks.form` is `VARCHAR(16)` and LMS `track.form` is
`TEXT` (see [track-form/technical.md](../track-form/technical.md)), so both take the new values.

`services/common/track_form.py`:

- `INTERVIEW = 'interview'`, `PREVIEW = 'preview'`, appended to `FORMS`.
- `NON_MUSIC_FORMS = frozenset({INTERVIEW, PREVIEW})`, the one set every consumer below imports or
  mirrors.
- `derive_form` checks two rules first, before the duration check:
  1. `_INTERVIEW` (whole word `interviews?`) in the title, top folder `youtube` or `soundcloud`
     (`DOWNLOAD_FOLDERS`), and no `_MUSIC_WORD` (`sets?`, `live ?sets?`, `mix`, `intro`, `outro`,
     whole words) in the title: `interview`.
  2. `_DVD_PREVIEW` (`dvd` or `blu-?ray` within ten characters of `preview`, either order) in the
     title: `preview`.
- A non-music file with no duration is still non-music: the title decides, not the length.
- `derive_performance_date` returns `None` for both, as it does for every form but `liveset`.

The scanner and the hourly pass (`track_form_sync.classify_library`) call `classify` already, so the
first pass after the deploy rewrites the 251 rows and pushes them to LMS. No file is touched.

## Consumers

| Consumer | Change |
|---|---|
| Song versions, `song_versions.work_key` | A track whose form is in `NON_MUSIC_FORMS` gets `UNGROUPABLE_PREFIX + track_id`, like a long recording. `song_version_worker` selects `t.form` for it |
| Daily mix, release radar (`feeds/queries.py`) | `(t.form IS NULL OR t.form NOT IN ('interview', 'preview'))` next to the duration bounds, in the three candidate queries |
| Old hits (`feeds/old_hits_queries.py`) | No change: `_TRACK_FORM` already keeps only `track` and NULL |
| BPM analysis (`bpm/worker.py`) | `bpm_analysis_skip_forms` default gains `interview,preview` |
| Beheer statistics (`routers/stats.py`) | `total_tracks` counts `form IS NULL OR form NOT IN (...)`. New `total_non_music` |
| Listening statistics | No query change: the top lists group listens, and no listen points at these rows today. A future listen counts, as an unmatched listen does. Open for the owner if that is wrong |
| Advanced library filter (`analytics_filters.py`) | Takes `form=interview` / `form=preview` through `FORMS`, so the curator can list them |
| LMS, both query builders | `FindParameters::excludeNonMusic`, default `true`: `AND t.form NOT IN ('interview', 'preview')`. An explicit `forms` that names a non-music form switches the exclusion off. Search (`search3`, the Spotify search) and the artist page pass `false` |
| LMS radio and recommendations | Use `find` with the default, so they exclude non-music without a change of their own |
| LMS `parseTrackForms` | Accepts the two new values, so `form=interview` lists them |
| Web and phone (bundled frontend) | `trackForm.js`: the two values in `TRACK_FORMS`, not in `SET_FORMS`, so no chip offers them. Artist page: a section "Interviews and previews" from a second `getSpotifyTracks` call with `form=interview,preview`. Labels in `i18n` (nl, en) |
| MuMa Mobile native | `TrackForm.FORMS` gains the two values so `sanitize` lets them through. `SET_FORMS` stays. Android Auto, voice and presets offer nothing new and get non-music out by the LMS default |

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `getSpotifyTracks`, `getSongs` (LMS) | `form` also takes `interview`, `preview`. Without a non-music `form`, non-music tracks are left out | unchanged | unknown form: `BadParameterGenericError`, as today |
| `search3` and the Spotify search (LMS) | unchanged | still finds non-music tracks | unchanged |
| `GET /api/library/advanced`, `/api/analytics/*` (MuMa) | `form` also takes the two values | unchanged | unknown form: 422, as today |
| `GET /api/stats/` (MuMa) | unchanged | `total_tracks` counts music only; new key `total_non_music` | unchanged |

Breaking for a client that relies on every track coming back from `getSongs`: none exists in this
repository. Offline mode on the phone has no form and keeps showing a cached interview until the
next sync. The changelog states both.

## Cross-App Impact

LMS, music-manager, the frontend and MuMa Mobile change in one commit (AGENTS.md rule 7): the LMS
default exclusion, the new form values in all three closed lists, the artist-page section. The
contract tests (`scripts/test/contracts.sh`) get one case: a track with form `interview` is absent
from `getSongs` and present in `search3`.

## Technical Acceptance Criteria

1. `derive_form` unit tests: every production example from the functional design, the three keep-
   as-music examples, a label-tree "Interview" title (stays `track`), a 12-minute interview, a
   35-minute DVD preview, and an interview without a duration.
2. `work_key` gives a non-music track a key of its own.
3. The feed queries, the stats query and the advanced filter run against MariaDB in
   `tests/integration/test_router_sql.py` with the new conditions.
4. LMS `Track_excludesNonMusic_bothBuilders`: default excludes, `forms={"interview"}` includes,
   `excludeNonMusic=false` includes, for `find`, `findIds` and `find_advanced` / `countAdvanced`.
5. LMS `TrackForm` test: `parseTrackForms` accepts the two values.
6. A new web `trackForm.test.js` and MuMa Mobile `TrackFormTest`: both values survive `sanitize`,
   neither is in `SET_FORMS`.

## Related Docs

- [track-form](../track-form/technical.md), the form this extends
- [release-series-markers](../release-series-markers/functional.md), which gave these files their
  artist and title and left this issue open
- `docs/bug-reports/142-release-series-collapse-into-one-song.md`
