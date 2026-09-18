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

## Advice: `GenreNameAnalyzer`

The queue reached 821 genres, and the tagger's "one name at a time" page did not scale to that. The same
shape as artist curation (`docs/designs/artist-curation/technical.md`) sits next to the queue:
a pure analyzer in `services/common/Helpers/GenreNameAnalyzer.py`, a run that rewrites
`rules_genre_proposals` whole, and advice shown per row that a human applies or ignores.

### Three things stay separate

| Thing | Where | Written by |
|---|---|---|
| The raw genre | `rules_genres`, state `unknown` | the tagger (`record_unknown`) |
| The proposal | `rules_genre_proposals` (`genre_id` PK, `kind`, `targets` JSON `[{id, name}]`, `evidence` JSON, `confidence`, `analyzed_at`) | `POST /api/rules/genres/analyze`, rewritten whole per run, `ON DELETE CASCADE` from the genre |
| The decision | `rules_genres.state` + `rules_genre_expansions` | `POST /api/rules/genres/{id}/decide`, never by a run |

Targets are stored with their id at analysis time so the page can post a decision without a second lookup;
a target that has since been rejected still has a valid id, and the next run replaces the advice.

### The dictionary is the curator's own past work

`build_dictionary` takes, in `routers/genre_curation.py`'s `load_dictionary`:

- approved genres with their track count (`library_track_genres`), used to rank blends;
- every correction already made (`rules_genre_expansions`, white *and* black), as aliases resolved to
  approved names -- an approved genre that itself has a correction (`RAW` → `Raw Hardstyle`) is an alias,
  not a target, because the tagger never writes it; a `;`-joined legacy target name resolves to its parts;
- black genres without a correction, for "looks like something you rejected";
- artists (`rules_artist_genres` plus `library_artists` with at least `MIN_ARTIST_TRACKS`) and labels
  (`library_labels`) with the genre the tagger page links them to, if any.

There is no external knowledge and no bootstrap from the queue itself. `Tafelpoot` is not rejected because
the analyzer knows Dutch furniture; it is proposed for rejection at confidence 50 because it resembles no
approved genre and has no genre-like part (no word of an approved genre inside it, no `-core`/`-style`/
`-tempo` ending). `Energycore` has one, so it stays a queue entry with "reads as a genre, but matches
nothing approved".

### Passes, in order

1. Exact or space-insensitive match on an approved name or alias (`Uptempohardcore`, `Up Tempo`,
   `D&B` via `&` → `n`) — rewrite 95.
2. Artist or label by name: linked to a genre → rewrite 90; unlinked → reject 85, unless the name also
   reads as a genre (`Melodic`, `Future`), in which case the collision is a footnote on whatever follows.
3. Separators (`/ \ , | & + and en vs`): every part resolved → split 90; some dropped → split 60; a dropped
   part that reads as a genre blocks the advice (unknown); more dropped than resolved → no split.
4. Noise stripped (`2018`, `Classics`, `Mainstage`, `Add "…"`, `Toevoegen`) and the remainder resolved → rewrite 85.
5. Label words (`records`, `recordings`, …) and promo words (`podcast`, `weekly`, `sample pack`, …) → reject 80.
6. Whole-string fuzzy match ≥ 0.88 against approved names and aliases → rewrite at the ratio, minus 10 for
   keys under 8 characters (`Mental` / `Metal` is a different word as often as a typo).
7. Token segmentation: fewest known phrases covering the words, a phrase may be one typo off with the same
   word count. All covered → split/rewrite 85. A leftover word that an existing correction already dropped
   (`Vocal Trance → Trance` teaches `vocal`) → 70 with the lesson in the evidence; an unknown leftover
   (`dutch`) → 60; a leftover that reads as a genre (`melodic`, `phonk`) → unknown, the human decides.
8. Single words: glued known names (`Jungleterror`, longest piece first so `hardcore` is never
   `hard`+`core`) → split 80; a blend of the start of one genre and the whole of another (`Upterror`,
   `Euphoraw`) → split 65 with the runners-up in the evidence; two fragments of at least five characters
   (`Frenchtempo`) → split 55.
9. Fuzzy ≥ 0.9 against a rejected name → reject 75; two characters or fewer → reject 70; nothing
   genre-like → reject 50; otherwise unknown.

Every threshold and word list lives in `GenreAnalyzerConfig`, overridable through the
`genre_curation_analyzer` config key. Dry-run against production on 2026-09-18 (821 queued): 126 rewrite,
172 split, 372 reject, 151 unknown, in 0.5 s.

### Frontend

`GenreCurationTab.svelte` gains the summary strip (queue, approved, rejected, advice counts plus the
Analyse button), a proposal filter on the queue, an "Advies" column with the evidence and confidence, an
"Overnemen" button per row and "Advies opvolgen" per page. The pure parts are in `genreCuration.js`:
`describeProposal`, `decisionFromProposal` (a rewrite or split becomes black-with-targets, exactly what the
correction dialog produces; a reject becomes black; unknown becomes nothing) and `planFromProposals`,
which applies only advice at or above `BULK_CONFIDENCE_FLOOR` (60) and reports what it left alone. The
first visit without a run starts the analysis on its own; after that it is the button, because a run
rewrites every proposal. Bulk decisions are posted one at a time: each marks files for a retag and
refreshes the tagger's rules, and a burst of those is what the LMS proxy refuses.

### Technical Acceptance Criteria (advice)

19. `build_dictionary` turns an approved genre with a correction into an alias, resolves a `;`-joined
    target to its parts, and drops an alias whose target is not approved.
20. `propose` on `Frenchcore/Terror`, `Jungleterror`, `Upterror`, `Harddcore`, `Hardstyle 2018` and
    `Vocal Hardcore` yields the targets named above with the stated confidence; `Tafelpoot` is a reject at
    50 and `Energycore` is unknown.
21. An artist linked on the tagger page becomes its genre; an unlinked artist is a reject; an artist that
    reads as a genre is only a footnote.
22. A run deletes and rewrites `rules_genre_proposals` with targets carrying ids, and issues no `UPDATE`
    on `rules_genres` and no insert into `rules_genre_expansions`.
23. `GET /api/rules/genres` carries `proposal` per row (null before the first run), accepts
    `proposal=<kind>` and rejects an unknown kind with 400.
24. `GET /api/rules` returns approved genres only.
25. `decisionFromProposal` maps split/rewrite to black with the target ids, reject to black, keep to white
    and unknown to null; `planFromProposals` applies nothing under the floor.

## The page since the rules moved in

Curatie › Genres carries four sections (`SECTIONS` in `management/genreRules.js`): the queue with
its advice, the approved-genre overview, and one rule panel each for artist → genre and
label → genre. The tagger page (`TaggerTab.svelte`) is the tagger itself — rescan and the retag
pile — and points here; its "Genre Overzicht" and "Genre Koppelingen" sub-tabs are gone. The old
overview listed every row of `rules_genres`, rejected and queued included, and the artist/label
picker offered those as link targets.

- `GenreOverviewPanel.svelte` reads `GET /api/curation/genres` (approved only; `q`, `limit` ≤
  1000): id, name, hardness, occurrences, `track_count`, `artist_rule_count`,
  `label_rule_count`, `parents` (from `rules_subgenre_hierarchy`). The row opens `genre-edit:<name>`.
- `GenreRulesPanel.svelte` serves both rule kinds; `RULE_KINDS` in `genreRules.js` holds what
  differs (endpoint, name column, how to open the subject). `GET /api/rules/artist-genres` and
  `label-genres` now join the library row for `artist_id`/`label_id` and `track_count`, and carry
  `created_at`/`created_by`. A rule whose name has left the library is shown as such rather than
  hidden. The whole list is loaded once (480 + 49 rules on prod) and filtered client-side on name
  *or* genre with the same key as the queue's search box.
- `buildRule` refuses an empty name, a missing genre and a pair that already exists (the API
  would upsert and only re-stamp `created_by`), so the button and the request agree.
- Management.svelte no longer fetches `/api/rules`, `/api/artists` and `/api/labels` on open —
  ten calls instead of eleven behind the proxy gate.

Acceptance: 26. `GET /api/curation/genres` lists white genres only with the counts above and turns
`parents` into a list. 27. Both rule list endpoints carry the library id, track count and
provenance. 28. `buildRule` refuses a duplicate ignoring case; `sortRules` never mutates.
29. The tagger page renders neither "Genre Overzicht" nor "Genre Koppelingen" and its link opens
`genre-curation`. 30. The queue's state filter is hidden outside the queue section.
