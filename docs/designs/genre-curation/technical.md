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
| `canonical_id` | `INT` NULL, FK to `rules_genres(id)` | Correction target; makes either decided state a rewrite |
| `occurrences` | `INT` | How often an unjudged genre has been seen |
| `corrected_genre` | `VARCHAR(255)` | Legacy, superseded by `canonical_id`; kept so `tools/process_genres.py` keeps working |
| `detected_at` | `TIMESTAMP` | First sighting |
| `decided_at` | `TIMESTAMP` NULL | Set when a decision is made |
| `decided_by` | `VARCHAR(64)` NULL | `migration`, `system`, or a username; a row with a value here is never re-decided automatically |

Four behaviors from three states: `white` without `canonical_id` keeps the genre; `white` or `black` with a
`canonical_id` rewrites it to the target's `name`; `black` without one drops it; `unknown` leaves the tag
untouched and only bumps `occurrences`.

`rules_ignored_genres` and `rules_genre_backlog` stay in place, unread by the tagger, so the tools under
`tools/` keep working. They can be dropped in a later change.

Migration `migrate_genre_states.sql` is re-runnable: the whitening step keys off the empty `normalized_name`
that only pre-existing rows have, so a second run cannot promote a queued genre. Where a genre was both
whitelisted and ignored, ignored wins — that matches the old `CleanAndFilterGenreRule`, which checked the
ignore list first.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/rules/genres` | `state` (optional, one of `white`/`black`/`unknown`), `limit` (default 200) | Rows with `id`, `name`, `state`, `canonical_id`, `canonical_name`, `occurrences`, `detected_at`, `decided_at`, `decided_by`, ordered by `occurrences` descending then `name` | `400` invalid `state`; `401` missing/invalid API key; `500` no database connection |
| `POST /api/rules/genres/{genre_id}/decide` | `{"state": "white"\|"black", "canonical_id": int\|null}` | `{"status": "ok"}` | `400` state is not `white`/`black`, `canonical_id` equals `genre_id`, or the correction target does not exist; `404` unknown `genre_id`; `401`; `500` |

Not a breaking change: `GET /api/rules` keeps its existing shape, and `corrected_genre` is still selected
there.

## Cross-App Impact

None. Backend-only: `music-manager` (tagger rules and management API) and the shared helpers. The frontend
consumes the new endpoints when the review screen is built; nothing existing changes.

## Technical Acceptance Criteria

1. `GenreRulesHelper.normalize` maps `Raw  Hardstyle`, `raw-hardstyle` and `  RAW/HARDSTYLE  ` to the same
   key, and strips accents (`Frenchcöre` to `frenchcore`).
2. `GenreRulesHelper.resolve` returns state `white` with the stored `name` for an approved genre, `black` with
   `None` for a rejected one, the target's `name` when `canonical_id` is set in either state, and `unknown`
   with the input unchanged for a genre that is unseen or still queued.
3. `resolve` on a whitespace-only genre returns `black` with `None`.
4. A row whose `canonical_id` points at itself resolves to its own `name` rather than looping.
5. `record_unknown` inserts one row per normalized key and increments `occurrences` on repeat sightings.
6. `ResolveGenreRule` writes the sorted, de-duplicated result once per song, and does not touch the tag when
   the resolved set equals the current set.
7. `ResolveGenreRule` calls `record_unknown` for an unjudged genre and leaves that genre in the tag.
8. An unjudged genre recorded in one pass still resolves as `unknown` in the next pass — the regression that
   `AddMissingGenreToDatabaseRule` plus `CleanAndFilterGenreRule` produced together.
9. `POST /api/rules/genres/{id}/decide` rejects `unknown` as a target state, rejects a self-referencing
   correction, and stores `decided_by` and `decided_at`.
10. `migrate_genre_states.sql` run twice against MariaDB 10.6 leaves identical state counts, preserves backlog
    `detected_at` values, and converts every `corrected_genre` into a `canonical_id`.

## Related Docs

- [docs/database-design.md](../../database-design.md) — table inventory
- [docs/designs/tagger/technical.md](../tagger/technical.md) — the rule pipeline this plugs into
