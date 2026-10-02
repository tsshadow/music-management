# Release Info Enrichment — Functional Design

## Overview

A scene release arrives in the import queue with a folder name, audio files tagged with little more
than artist, title and year, and an `.nfo`. The folder name is the only thing the importer used to
place the release: the catalogue number in it routes the release to its label folder through
`rules_catid_label`. A release whose name has no catalogue number -- 2.759 of the 6.583 folders in
`__TODO` on 2026-10-02 -- waits for a person in Beheer > Labelvoorstellen, and only 11 proposals
were ever confirmed. Its tracks keep a year-only date, which makes "recently released" wrong:
LMS sorts on `COALESCE(original_date, date)` as text, so `'2026'` sorts below every dated 2026
track (`'2026' < '2026-01-01'`) and a release from yesterday shows up after one from January.
22.689 EPs tracks from 2024-2026 are year-only (9.918 of 14.341 for 2026).

The `.nfo` says more than the name. Sampled on production (all 6.546 `.nfo` files in `__TODO`): a
usable label in 5.849 (`Label` 4.505, `Company` 1.344), a usable catalogue number in 2.736, an album
link in most (Deezer 4.514, Beatport 1.482, Qobuz 118, Tidal 81; no Spotify or iTunes link at all),
a date line in a few hundred (files containing `Rip.date` 367, `Date` 130, `Release date` 78,
`Rls.date` 36, `Street date` 13, `Store date` 10). The 42.196 `.nfo` files in the label tree read
the same way: a label in 33.353, a catalogue number in 17.010, a Deezer link in 9.097. Deezer's
public album API returns the exact release date, the label and the UPC; in a sample of 60 albums
linked from year-only releases 59 answered with a full date whose year matched (one album was gone).

What that buys, measured against the queue as it stood on 2026-10-02 (6.583 folders, of which
2.759 misnamed and 3.766 with a catalogue number no rule knows): the `.nfo` alone places 2.159
releases in an existing label folder (1.462 of the misnamed, 681 of the unrouted, 16 others) --
4 of them through a catalogue number a rule knows, the rest by label name. Deezer adds little
for placement (0 of a sample of 48 Deezer labels matched a folder: those are labels the library
does not have yet) but nearly everything for the date: about 13.500 of the 22.689 year-only
tracks can be lifted to an exact date, 7.550 of them already in the label tree (backfill) and
5.980 in the queue (on import).

This feature makes the importer read that, and gives the date a precision ladder. It is for the
curator (fewer releases waiting for a decision, the right label without typing it) and for
everyone listening (a "recent" list that is actually recent).

## User Stories

- As the curator, I want a release whose `.nfo` names a label I already have to land in that
  label's folder by itself, so I only decide releases of labels the library has never seen.
- As the curator, I want a catalogue number the `.nfo` states to be used when the folder name has
  none, so the release can be routed by a catalogue rule like any other.
- As a listener, I want every newly imported release to carry its real release date, so "recently
  released" lists it where it belongs.
- As the curator, I want to see where a date came from, so a rip date or an arrival date is never
  mistaken for a store date, and so a better source can replace a worse one later.
- As the operator, I want a dry-run backfill for the year-only tracks already in the library that
  says how many each source would fix, before anything is written.
- As the operator, I want the importer to keep working exactly as before when the store cannot be
  reached.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Name has a catalogue number a rule knows | Unchanged: moved to the rule's label. |
| Name has no catalogue number, `.nfo` states one (`Catalog Nr: RAW046`) | The Renamer prefixes it (`RAW046 - <name>`); the Mover routes it by rule, or records a proposal carrying that number. |
| No rule for the release, `.nfo` label maps to an existing label folder (`Company.: B2S` -> `EPs/B2S`) | Moved there and tagged; the push names the label and says it came from the `.nfo`. |
| No rule, no usable `.nfo` label, Deezer link in the `.nfo` | Deezer is asked once (cached); a label that maps to an existing folder places the release. |
| No rule, label maps nowhere (a label the library has never seen) | Unchanged: a proposal for Beheer > Labelvoorstellen, now with the `.nfo` label (also from `Company`) as the proposed label. |
| Two sources name two different existing labels | Not placed; proposal as today. |
| Deezer unreachable, rate-limited, or the album is gone | The release is handled as if there were no link; nothing waits, nothing fails. |
| A backlog release (it already had a proposal row) gets placed | Recorded in the event log without a phone push, so placing a backlog does not send hundreds of pushes. |
| Release is tagged after the move | Its tracks get the best date available, and the tag `DATE_SOURCE` says which: `deezer`, `nfo-street`/`nfo-release`, `tag` (the file's own full date), `nfo-rip`, or `arrival`. |
| A track already has a full date from a better source | Left alone. A worse source never replaces a better one; a full date of unknown origin is never replaced. |
| A track's date came from a worse source and a better one appears later (Deezer cache filled) | The next retag replaces it and updates `DATE_SOURCE`. |
| New release, nothing but the year, year equals the year it arrived | The date it first arrived in the queue (`DATE_SOURCE=arrival`): within days for a scene release. |
| Backfill, dry run (default) | Per source: how many year-only tracks in the label tree a Deezer link, an `.nfo` date line, or nothing could lift. Nothing is written, nothing is fetched. |
| Backfill, `--lookup N` | Fetches up to N uncached Deezer albums into the cache (rate-limited); no file is touched. |
| Backfill, `--apply` | Queues the tracks whose release now has a better date for the tagger (reason `release_date_ladder`); the tagger writes them in its normal rounds. |

## The date ladder

Best first; the owner's own weighting of what a date is worth: exact 100%, a day off 75%, the same
week 50%, the year only 10%, nothing 0%. A week off is acceptable, the year alone is not.

1. **Store** -- the release date of the album the `.nfo` links on Deezer (exact).
2. **`.nfo` release date** -- a `Street date`, `Release date`, `Store date` or `Retail date` line.
3. **The file's own full date** -- a `DATE` tag at day precision (usually the store's, from a purchase).
4. **`.nfo` rip date** -- `Rip.date`, `Rls.date`, `Date`: when the group ripped it, usually within a
   day or a week (Minus Militia: rip 01.10, store 02.10).
5. **Arrival** -- the day the release first arrived in the queue, only for a new release whose
   year equals the year it arrived.
6. **Year only** -- as today.

Every rung except arrival must agree with the year in the release's folder name, the guard the
`.nfo` rule already uses so a rip date cannot redate a 1995 vinyl release.

## Acceptance Criteria

1. `Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-SINGLE-WEB-2026-UTNG`
   keeps its name in `__TODO`, is moved to `EPs/B2S/` in the next import cycle, and its track reads
   `ORIGINALDATE=2026-10-02`, `DATE_SOURCE=deezer`, `BARCODE=8719244873593`.
2. With Deezer unreachable the same release is still moved to `EPs/B2S/` (the label is in the
   `.nfo`) and gets `ORIGINALDATE=2026-10-01`, `DATE_SOURCE=nfo-rip`.
3. A release whose `.nfo` names a label with no folder is not moved; its proposal shows that label.
4. A track with `DATE_SOURCE=nfo-rip` is upgraded to the Deezer date on a later retag; a track with
   `DATE_SOURCE=deezer` is never downgraded; a full date without `DATE_SOURCE` is never touched.
5. The backfill dry run prints a count per rung and changes nothing.
6. Switching `import_place_by_label_name` off in Beheer > Configuratie restores today's placement
   (catalogue rules only).

## Open Questions / Not Yet Decided

- **Placement by label name is ~95% right, not 100%.** Measured on the label tree: of the releases
  no catalogue rule routes, the `.nfo` label maps to the folder the release is actually in for
  3.562 and to another folder for 188 -- almost all a parent label where the curator keeps a
  sub-label folder (`Cloud 9 Music` vs `Cloud 9 Dance`, `Hardcore Blasters` vs `... Jump`,
  `Enzyme Records` vs `Enzyme X`). Shipped switched on, behind `import_place_by_label_name`, because
  the alternative is the 7.186-row proposal backlog nobody works; whether to keep it on is Teun's
  call (decision issue).
- **Beatport links** (1.499 `.nfo` files) are counted but not looked up: Beatport has no public API.
  Qobuz and Tidal neither. Only Deezer is asked.
