# Genre Curation States — Technical Design

Implements [`functional.md`](functional.md).

## Data Model

`rules_genres` absorbs `rules_ignored_genres` and `rules_genre_backlog` and carries the curation state itself.

| Column | Type | Notes |
|---|---|---|
| `id` | `INT` PK | |
| `name` | `VARCHAR(255)` | Display spelling, written to the tag |
| `normalized_name` | `VARCHAR(191)` UNIQUE | Lookup key: lowercase, accents stripped, runs of non-alphanumerics collapsed to a single space, trimmed |
| `state` | `ENUM('white','black','unknown')` | `white` keep, `black` drop, `unknown` awaiting curation |
| `canonical_id` | `INT` NULL, FK to `rules_genres(id)` | Legacy first correction target; superseded by `rules_genre_expansions` and no longer read by the tagger |
| `occurrences` | `INT` | How often an unjudged genre has been seen |
| `corrected_genre` | `VARCHAR(255)` | Legacy, superseded by `rules_genre_expansions`; kept so `tools/process_genres.py` keeps working |
| `detected_at` | `TIMESTAMP` | First sighting |
| `decided_at` | `TIMESTAMP` NULL | Set when a decision is made |
| `decided_by` | `VARCHAR(64)` NULL | `migration`, `system`, or a username; a row with a value here is never re-decided automatically |

Rewrite targets live in `rules_genre_expansions` (`genre_id`, `target_id`, `position`), not in
`canonical_id`, because a genre can stand for more than one: `Upterror` is `Uptempo Hardcore` plus `Terror`.
`canonical_id` still holds the first target so existing tools keep working, but the tagger no longer reads it —
one place decides a rewrite instead of two that can disagree.

Four behaviors from three states: `white` without targets keeps the genre; `white` or `black` with targets
rewrites it to all of them; `black` without any drops it; `unknown` leaves the tag untouched and only bumps
`occurrences`.

### Splitting composites

`Hardstyle/Hardcore` is two genres. The tag pipeline already splits on `;` and on ` & ` — `Tag.resplit` even
claims to handle `/`, but it only runs when `Tag.regex` changed something, and `ARTIST_REGEX` never matches a
slash, so these arrived as a single genre and filled the queue with combinations that never repeat.

`GenreRulesHelper.split_composite` does the split, and deliberately not `Tag.resplit`: artists really do
contain slashes (`AC/DC`) and must keep them, so this stays on the genre path only. A genre that has been
decided is never split, which means approving a name that genuinely contains a slash protects it for good.

`rules_ignored_genres` and `rules_genre_backlog` stay in place, unread by the tagger, so the tools under
`tools/` keep working. They can be dropped in a later change.

Migration `migrate_v3_genre_states.sql` is re-runnable: the whitening step keys off the empty `normalized_name`
that only pre-existing rows have, so a second run cannot promote a queued genre. Where a genre was both
whitelisted and ignored, ignored wins — that matches the old `CleanAndFilterGenreRule`, which checked the
ignore list first.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/rules/genres` | `state` (optional, one of `white`/`black`/`unknown`), `limit` (default 200) | Rows with `id`, `name`, `state`, `canonical_targets` (a list of `{id, name}`), `occurrences`, `detected_at`, `decided_at`, `decided_by`, ordered by `occurrences` descending then `name` | `400` invalid `state`; `401` missing/invalid API key; `500` no database connection |
| `POST /api/rules/genres/{genre_id}/decide` | `{"state": "white"\|"black", "canonical_ids": [int]}`; `canonical_id` is still accepted as the single-target form | `{"status": "ok"}` | `400` state is not `white`/`black`, a target equals `genre_id`, or a target does not exist; `404` unknown `genre_id`; `401`; `500` |

Not a breaking change: `GET /api/rules` keeps its existing shape, and `corrected_genre` is still selected
there.

## Frontend

`GenreCurationTab.svelte` is a management tab like any other: it takes `API_BASE`, `getHeaders`, `onMessage`
and `onError` from `Management.svelte` and owns its own fetching. Two requests keep it honest — the table
follows the active state filter, while the approved genres are fetched separately because they are the only
valid correction targets and stay needed while the table shows the unjudged queue.

The parts that are pure data live in `management/genreCuration.js` so they can be unit-tested without a
component: the filter definitions, the search key, the state summary, the sentence describing what a row does
to a tag, and `buildDecision`, which applies the same two rules the API enforces (state must be `white` or
`black`, a genre cannot correct to itself) before the confirm button is enabled.

`normalizeGenre` there is a deliberate copy of `GenreRulesHelper.normalize`, not a looser search: the box has
to group names the way the tagger does, so `hard style` and `hardstyle` stay two different genres rather than
suggesting a merge that would not happen.

Decisions apply from the next tagging run. The tagger is a one-shot process whose helpers preload at start, so
no cache invalidation is needed — the page states the delay rather than hiding it.

## Cross-App Impact

`music-manager` (tagger rules and management API), the shared helpers, and the Svelte frontend. Android and
LMS are untouched.

## Technical Acceptance Criteria

1. `GenreRulesHelper.normalize` maps `Raw  Hardstyle`, `raw-hardstyle` and `  RAW/HARDSTYLE  ` to the same
   key, and strips accents (`Frenchcöre` to `frenchcore`).
2. `GenreRulesHelper.resolve` returns state `white` with the stored `name` for an approved genre, `black` with
   an empty list for a rejected one, the target names when the genre has expansions in either state, and
   `unknown` with the input unchanged for a genre that is unseen or still queued.
3. `resolve` on a whitespace-only genre returns `black` with an empty list.
4. A row whose expansion points at itself resolves to its own `name` rather than looping.
5. `record_unknown` inserts one row per normalized key and increments `occurrences` on repeat sightings.
6. `ResolveGenreRule` writes the sorted, de-duplicated result once per song, and does not touch the tag when
   the resolved set equals the current set.
7. `ResolveGenreRule` calls `record_unknown` for an unjudged genre and leaves that genre in the tag.
8. An unjudged genre recorded in one pass still resolves as `unknown` in the next pass — the regression that
   `AddMissingGenreToDatabaseRule` plus `CleanAndFilterGenreRule` produced together.
9. `POST /api/rules/genres/{id}/decide` rejects `unknown` as a target state, rejects a self-referencing
   correction, and stores `decided_by` and `decided_at`.
10. `migrate_v3_genre_states.sql` run twice against MariaDB 10.6 leaves identical state counts, preserves backlog
    `detected_at` values, and converts every `corrected_genre` into a `canonical_id`.
11. `buildDecision` refuses `unknown` as a target state and refuses a correction pointing at the genre itself,
    matching the API, and coerces the select's string value to a number or `null`.
12. `correctionTargets` returns only approved genres, never the genre being decided, sorted by name.
13. `describeOutcome` lets a correction win over the state: a rejected genre with a correction target is
    described as replaced, not removed.
14. `normalizeGenre` produces the same key as `GenreRulesHelper.normalize` for casing, accents and separators.
15. `split_composite` splits on `/`, trims the parts, drops empties, strips a stray trailing slash, and returns
    the input unchanged for a genre that has been decided.
16. `resolve` returns every expansion target in `position` order, skips a target that no longer exists or that
    points at the genre itself, and lets targets win over the state.
17. `ResolveGenreRule` records the parts of a composite for curation, never the composite itself.
18. `migrate_v4_genre_expansions.sql` run twice leaves identical state counts and expansion counts, converts
    every `canonical_id` into an expansion, and turns a slash genre still marked `decided_by = 'migration'`
    into a rejected genre expanding into its parts — leaving a human-decided one alone.

## Related Docs

- [docs/database-design.md](../../database-design.md) — table inventory
- [docs/designs/tagger/technical.md](../tagger/technical.md) — the rule pipeline this plugs into
