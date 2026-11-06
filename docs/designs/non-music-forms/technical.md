# Interviews and previews as non-music — Technical Design

> Status: **agreed** (2026-10-03). Implements [functional.md](functional.md).

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
| Song versions already grouped | `song_version_worker.detach_non_music` runs first in every round: a non-music track in a shared work, not `work_locked`, loses its `work_id`, `version_kind` and `version_score`, and the round then gives it a work of its own. `scripts/repair_song_works.py` reports such a track with the reason `non-music` |
| Daily mix, release radar (`feeds/queries.py`) | `(t.form IS NULL OR t.form NOT IN ('interview', 'preview'))` next to the duration bounds, in the three candidate queries |
| Old hits (`feeds/old_hits_queries.py`) | No change: `_TRACK_FORM` already keeps only `track` and NULL |
| BPM analysis (`bpm/worker.py`, `bpm/tag_writeback.py`) | `bpm_analysis_skip_forms` default gains `interview,preview`: talk has no tempo |
| Management statistics (`routers/stats.py`) | One query counts every row and `SUM(form IN ('interview', 'preview'))`. `total_tracks` is the difference, `total_non_music` the sum. The overview tab shows the second number under the first when it is not 0 |
| Listening statistics | No query change: the top lists group listens, and no listen points at these rows today. A future listen counts, as an unmatched listen does. Open for the owner if that is wrong |
| Advanced library filter (`analytics_filters.py`) | Takes `form=interview` / `form=preview` through `FORMS`, so the curator can list them |
| LMS, both query builders | `FindParameters::excludeNonMusic`, default `false`: when set, `AND t.form NOT IN ('interview', 'preview')`, in `whereFormAndYear` and `appendFormAndYear`. An explicit `forms` that names a non-music form switches the exclusion off. The default is off because 23 files build a `FindParameters`, among them the scanner, the syncs and playlists, and those must see every track |
| LMS endpoints that set it | `getSpotifyTracks` when it has no `query` (the songs and sets views, the artist page), `getSongs`, `getRandomSongs`, `getSongsByGenre` and `getSongsByFilter` (the radio). `search3` and `getSpotifyTracks` with a `query` leave it off, so search finds them |
| LMS `parseTrackForms` | Accepts the two new values, so `form=interview` lists them |
| Web and phone (bundled frontend) | `trackForm.js`: the two values in `TRACK_FORMS` and in a new `NON_MUSIC_FORMS`, not in `SET_FORMS`, so no chip offers them. Labels in `i18n` (nl, en). The artist page needs no change: its `getSpotifyTracks` call has no `query` |
| MuMa Mobile native | `TrackForm.FORMS` gains the two values so `sanitize` lets them through, plus `NON_MUSIC_FORMS`. `SET_FORMS` stays. Android Auto, voice and presets offer nothing new and get non-music out through `getSongs` |

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `getSpotifyTracks` without `query`, `getSongs`, `getRandomSongs`, `getSongsByGenre`, `getSongsByFilter` (LMS) | `form` also takes `interview`, `preview`. Without a non-music `form`, non-music tracks are left out | unchanged | unknown form: `BadParameterGenericError`, as today |
| `search3`, `getSpotifyTracks` with `query` (LMS) | unchanged | still finds non-music tracks | unchanged |
| `GET /api/library/advanced`, `/api/analytics/*` (MuMa) | `form` also takes the two values | unchanged | unknown form: 422, as today |
| `GET /api/stats/` (MuMa) | unchanged | `total_tracks` counts music only; new key `total_non_music` | unchanged |

Breaking for a client that relies on every track coming back from `getSongs`: none exists in this
repository. Offline mode on the phone has no form and keeps showing a cached interview until the
next sync. The changelog states both.

## Cross-App Impact

LMS, music-manager, the frontend and MuMa Mobile change in one commit (AGENTS.md rule 7): the LMS
exclusion and the new form values in all three closed lists. The LMS unit test covers the
exclusion in both query builders, so the contract tests get no new case.

## Technical Acceptance Criteria

1. `derive_form` unit tests: every production example from the functional design, the three keep-
   as-music examples, a label-tree "Interview" title (stays `track`), a 12-minute interview, a
   35-minute DVD preview, and an interview without a duration.
2. `work_key` gives a non-music track a key of its own.
3. `tests/integration/test_router_sql.py`: the release radar leaves an interview out and keeps an
   unclassified track, against MariaDB. The stats query keeps its existing case there.
4. `song_version_worker`: two interviews of one name get a work each, and a grouped interview
   leaves its work, which is then computed again.
5. LMS `Track_excludesNonMusic_bothBuilders`: the default returns everything, the flag drops
   interview and preview and keeps an unclassified track, `forms={"interview"}` lists the
   interview, for `findTrackIds`, `findAdvancedIds` and `countAdvanced`.
6. LMS `TrackForm` test: `parseTrackForms` accepts the two values.
7. A new web `trackForm.test.js` and MuMa Mobile `TrackFormTest`: both values survive `sanitize`,
   neither is in `SET_FORMS`.

## Related Docs

- [track-form](../track-form/technical.md), the form this extends
- [release-series-markers](../release-series-markers/functional.md), which gave these files their
  artist and title and left this issue open
- `docs/bug-reports/142-release-series-collapse-into-one-song.md`
