# Artist Curation — Technical Design

Implements [`functional.md`](functional.md).

## What this change delivers

The first cut (0.0.54) was the analysis engine and a dry-run report, and nothing else: no schema
change, no tagger rule, no API, no UI. Thresholds cannot be chosen in the abstract, so the first
deliverable was the thing that lets them be chosen by looking at the real library.

The second cut (2026-09-16, `routers/artist_curation.py` + Beheer → Artiestcuratie) is the queue
itself, in the genre-curation shape:

| Component | Responsibility |
|---|---|
| `rules_artists` | The human decision per name: `white` keeps it, `black` drops it, `black` + `canonical_name` rewrites it. `decided_by`/`decided_at`, never written by an analysis run. |
| `rules_ignored_artists` | Unchanged, still what the ten tagger rules read. Every decision is mirrored into it by the API, so the tagger needed no new table. `migrate_v26` seeds `rules_artists` from its 2.658 rows as `legacy-redirect` decisions. |
| `rules_artist_proposals` | What the last analysis run advised per undecided name -- kind, target, evidence in words, confidence. Rewritten whole on every run. |
| `POST /api/rules/artists/analyze` | Runs `ArtistNameAnalyzer` over every undecided name with the **approved names as its dictionary** -- no bootstrap seed, which is what produced `Rbr -> RBR ©`. Adds two passes the analyzer does not have: normalised-name collisions (`Dr. Peacock` / `Dr.Peacock`) and a leading `DJ`/`MC` (`DJ Angerfist` / `Angerfist`) resolve to the spelling with the most tracks; a rewrite whose target has fewer tracks than the name is downgraded to a queue entry with that said in the evidence. |
| `POST /api/rules/artists/decide` | Names in bulk, one state, optionally one correction. A correction approves its target in the same call and refuses a rejected one. Refreshes the tagger's preloaded helper and marks a rejected name's files for retag. |
| `ArtistCurationTab.svelte` | The queue, most tracks first, with an **Advies** column per name; filter by advice kind, select a page, "Advies opvolgen" turns the page's advice into decisions. The first visit starts the analysis on its own; after that it is a button. |

The scanner's unguarded `INSERT IGNORE INTO library_artists` is still in place: a black name that a
tagger run has not yet stripped from a file re-enters the table on the next scan, but it re-enters
as *black* -- the decision is keyed by name and outlives the row -- so it stays out of the queue.
Since 2026-09-25 that insert no longer makes a name trusted either; see "Wiring the queue".

## Redirects that point at a decided name (bug 080)

A redirect `Y -> X` is only right while X is an approved artist. When X is decided again:

| X becomes | What happens to every `Y -> X` (both tables) | Why |
|---|---|---|
| approved | nothing | the premise still holds |
| rejected with a correction Z | re-pointed: `Y -> Z` | Y is X and X is Z, so Y is Z; no chain is left |
| rejected without a correction | forgotten; Y is back in the queue | the premise is gone and the right answer for Y is not known; a plain rejection would strip the credit from every file on the next retag |
| undone | forgotten; Y is back in the queue | same |

This runs in the same transaction as the decision, and the reply lists the names (`repointed`,
`returned_to_queue`). A new correction to a rejected name is refused on the curation page and on
the Tagger tab; the Tagger tab also refuses a redirect that would close a loop. For rows stored
before this, the tagger's preloaded helper follows every chain to its end with a depth bound and a
cycle guard (a looping name keeps its one-hop answer), and
`GET /api/rules/artists/redirects/issues` reports what is dangling or looping. That endpoint only
reports: which way a stored loop should be broken is a curation decision.

## Wiring the queue (2026-09-25)

Until this change the tagger's artist dictionary was `library_artists` itself -- the
`library_artists` entry of `Cache.databaseHelpers` was a plain `TableHelper` over that table --
and the scanner inserts every artist string it reads. A name a rule guessed out of a title was
therefore a trusted artist one scan later, and matched itself in every later title ("artist
poisoning is self-reinforcing"; `Premiere`, 9.188 tracks, was one instance of it).

### Trust is a decision, not a row

| Name is | Trusted by the tagger | In the queue |
|---|---|---|
| approved (`rules_artists.state = 'white'`, by a person or `auto-external`) | yes, even when no file carries it any more | no |
| grandfathered (in `rules_artist_legacy_trust`) and undecided | yes -- as before this change | yes, as "to review" |
| recorded by the scanner after this change and undecided | **no -- pending** | yes, flagged `pending` |
| rejected (`black`), with or without a correction | no | no |

| Component | Change |
|---|---|
| `services/common/Helpers/TrustedArtistHelper.py` | New. A caching `TableHelper` (same registry key `library_artists`, same table name) whose snapshot is `TRUSTED_ARTISTS_SQL`: grandfathered-and-undecided names first, approved names last, so an approved spelling wins a casing tie. `add()` -- the interactive prompt's "yes" -- writes a `white` decision signed `tagger-prompt`, not a bare library row. |
| `Cache.databaseHelpers['library_artists']` | Is that helper. Every artist rule (`InferArtistFromTitleRule` and its sub-rules, `InferRemixerFromTitleRule`, `CheckArtistRule`, `AddMissingArtistToDatabaseRule`) already took its dictionary from this key, so none of them changed; their per-rule fallbacks build a `TrustedArtistHelper` too. |
| `rules_artist_legacy_trust` (db_init + `migrate_v40_artist_curation_wired.sql`) | New. The names already in `library_artists` at the first deploy, seeded once. Keyed by name, so a library rebuild keeps it. |
| scanner (`routers/scanner.py`) | Unchanged SQL. It still records every name and links the track to it; recording is simply no longer approval. |
| `GET /api/rules/artists` | `state=pending` (the untrusted part of the queue) and a `pending` flag on every row. `GET /summary` adds `pending`. Additive, no consumer breaks. |
| `POST /decide`, `DELETE /{name}` | Also reload the trusted-artist snapshot, so an approval is matched and a rejection dropped by the running tagger at once. Other processes (importer, downloader) catch up within `TableHelper.STALE_AFTER_SECONDS`. |
| Artiestcuratie page | A yellow "Nieuw" badge on a pending row (style recorded in `docs/styleguide.md`). |

**Why grandfather instead of trusting approved names only.** On production (2026-09-25) 6.280
names are approved (5.903 `auto-external`, 377 by hand) and 49.068 are undecided. Trusting only
the approved ones would take ~88% of today's dictionary away from every retag of the existing
library in one deploy -- a change to what thousands of files come out as, not a fix for new ones.
Grandfathering keeps every existing file's result the same and closes the loop for everything
that arrives from now on. The legacy set only shrinks: a decision on a grandfathered name takes
it out, and emptying the table is the switch to "approved only" once the queue is worked down.

**Why the seed is guarded twice.** `scripts/deploy.sh` may re-run a migration (a changed file
re-runs; `db-integration.sh` applies every file twice). A second seed would grandfather every
name that arrived since and undo the point. The INSERT runs only while the table is empty *and*
the ledger (`schema_migrations`) does not yet record the file, so neither a re-run nor a
deliberately emptied table re-seeds it. A fresh install seeds an empty library: everything is
pending from the first scan, which is the intended end state anyway.

### A file whose only artist is pending

Kept exactly as it is. The ARTIST tag is not touched (no rule acts on a name it neither trusts
nor has a rejection for), the scanner links the track to the name so it is browsable and counted,
and the name is listed in the queue with the badge and its track count. Nothing is written to the
file to "mark" it: the mark is the queue row, and it disappears with the decision. What changes
is only what *other* files get: a pending name is not picked out of titles, not credited as a
remixer from `(X Remix)`, and not used to re-case a spelling.

### What a decision does to a pending name

Approve: trusted from the next snapshot (immediately in the music-manager process). The files
that already carry it are not retagged -- they already say the right thing. Reject: as before --
mirrored to `rules_ignored_artists`, files marked for retag with reason `artist_decision`.
Auto-approve (!874, `tools/artist_auto_approve.py`): unchanged. Its snapshot reads every undecided
name, so pending names are candidates like any other; an approval it posts is a `white` decision
and therefore trust. Nothing about pending names bypasses its brand blocklist or thresholds.

### Side effect: rejections now reach files the scanner had already recorded

`CheckArtistRule` and `AddMissingArtistToDatabaseRule` ask the artist dictionary *before* the
ignore list. With `library_artists` as the dictionary, a rejected name that the scanner had
inserted (which is every rejected name that was ever on a file) answered "known artist" and the
correction or removal branch never ran; only `InferArtistFromTitleRule`, which subtracts
uncorrected ignored names from its set, honoured a rejection. On production 996 rejected names
without a correction are still linked to 29.772 tracks, and 536 with a correction to 2.951. A
rejected name is never trusted now, so those rules apply the decision -- but only when a file is
next tagged. The files were marked for retag when the decision was taken and that retag already
ran without effect, so they change on the daily walk or a deep run, not at deploy. Re-marking
them is left as an explicit follow-up (GitLab issue #48), not done by the migration: it is a
large one-off retag and should be started deliberately.

### Expected queue growth (measured read-only on production, 2026-09-25)

`library_artists` on production has no `created_at` (schema drift: db_init declares it, the
table predates it), so first appearance is read from the auto-increment id, which grows
monotonically per insert attempt, calibrated against the earliest `library_tracks.created_at` of
the tracks each id links to.

| Window | New distinct names | Per day |
|---|---|---|
| 2026-08-27 .. 08-31 (includes a retag burst on 08-29) | 1.715 | ~340 |
| 2026-09-01 .. 09-06 | 120 | ~20 |
| 2026-09-07 .. 09-14 | 261 | ~33 |
| 2026-09-15 .. 09-20 (includes a burst on 09-19) | 1.248 | ~210 |
| 2026-09-21 .. 09-25 | 146 | ~29 |
| 30 days in total | 3.490 | ~116 average, ~20-35 on a quiet day |

Of the 3.490, 134 are already rejected and 8 approved; 3.332 undecided ones carry 4.370 tracks,
and 2.879 tracks have *only* such names as artists -- the files this change leaves as they are.
The bursts coincide with tagger deep runs and retag waves, which produce new variants of names
in bulk, and they are exactly the kind of growth that used to become trusted on sight. Expect the
pending list to grow by a few dozen a day and by one to two thousand after a mass retag;
`auto-external` has so far approved 8 of the recent names because the evidence run has not been
repeated since it was first applied. Running it on a schedule is not part of this change; it
followed as the next section.

## Scheduled evidence run (2026-09-27, issue #49)

`services/music_manager/artist_auto_approve_worker.py`, thread `artist-auto-approve`, started
with the other loops in `main.py` and run through `thread_registry.run_forever` with a stop event.

### Why a loop inside music-manager, not a separate scheduler

| Option | Against it |
|---|---|
| cron / systemd timer running the tool | The tool writes through `POST /decide` with the system key and keeps its state in a sqlite file on one host; prod has no host-side scheduler for this stack, a timer on the runner would reach prod over the network with a production key, and a lost sqlite file means re-asking every catalogue. |
| A new worker container | One more image, compose entry and deploy path for a job that is ~95% waiting on the network. |
| **A loop in music-manager** | Chosen. It has `ConfigStore` (Beheer settings, read every check), the database pool, the event log with the right `source`, `/health` heartbeats, and it can write the decision with the same helpers `decide` uses -- no HTTP, no key. |

The worry with an in-process loop is the API: the tagger backlog once starved it. This loop holds
no connection across a round (each read and write takes a pooled connection and returns it), its
queries are bounded by `LIMIT`, and between requests it sleeps on the stop event, so it costs the
API one thread that is almost always waiting.

### What is shared with the tool

The judgement moved to `services/common/Helpers/ArtistEvidence.py` -- normalisation, brand guards,
the three approval rules, the three keyless lookups and `resolve` -- because the music-manager
image does not contain `tools/`. The tool imports it back, so `tools.artist_auto_approve.resolve is
ArtistEvidence.resolve` (pinned by a test): one set of rules, one `POLICY`. What stays in each is
only how requests are cached and rate-limited: the tool into its sqlite file with `time.sleep`, the
loop in memory with `RateLimitedFetcher`, whose clock and wait are injectable and whose wait is the
stop event's (a stop ends a round between two requests; the name in progress is not stored).

Evidence sources and their limits, unchanged from the tool: **Deezer** (keyless, undocumented
limit, answers `Quota limit exceeded` as a 200 -- treated as 429; 0.25 s spacing),
**iTunes Search** (keyless, ~20 requests/min documented; 3.2 s spacing), **MusicBrainz** (keyless,
1 request/s with a real User-Agent, 503 above it; 1.1 s spacing, `Retry-After` honoured). No key is
needed; none is read. Sources are asked cheapest first and a name stops at its first approval.

### One round

1. **Due?** The loop wakes hourly. A round runs when the switch is on and the last row in
   `rules_artist_evidence_runs` started at least `interval_hours` ago (database clock) -- so a
   restart or a deploy neither repeats nor skips a day.
2. **New names**: pending names (undecided, not in `rules_artist_legacy_trust`, with at least one
   track, no `rules_ignored_artists` row) without a current verdict, newest id first. "New since
   the last run" is therefore not a watermark but the pending concept of "Wiring the queue": every
   name recorded after that deploy, less the ones already judged. `library_artists` has no usable
   `created_at` on prod, and an id watermark would drop names across a library rebuild.
3. **Backlog slice**: grandfathered undecided names without a current verdict, most tracks first,
   `backlog_slice` of them, within what `max_names` leaves after the new ones. A burst of new names
   after a mass retag fills the round with new names and the backlog waits.
4. **Current verdict** means: under the current `POLICY`, and either `approve`, or less than
   `recheck_days` old and not `incomplete`. A name whose approval was applied and is undecided now
   was undone by a curator and is never selected again.
5. Per name: `resolve()` over its local titles, verdict stored in `rules_artist_evidence`
   (upsert, one row per name). A name whose fold matches a `rules_ignored_artists` row gets
   `skipped`/`tagger-rule` without a request, as the tool's snapshot excludes them.
6. **Apply** unless dry run: stored `approve` verdicts not yet applied, name still undecided,
   batches of 100, each one transaction that first drops names decided meanwhile, then
   `artist_curation.record_approvals` (the rows `decide` writes for `white`, signed
   `auto-external`) and `applied_at`. The tagger snapshots are refreshed once.
7. **Report**: ledger row closed with its counts, and one INFO line on
   `music-manager.artist-auto-approve` (an allowed prefix, so it reaches the event log with source
   `music-manager`). Network errors are DEBUG and counted in the line, so a flaky catalogue never
   reaches the alerts topic. A database failure raises; `run_forever` logs it and backs off.

### Settings (Beheer -> Config, group "Artist curation")

| Key | Default | |
|---|---|---|
| `artist_auto_approve_enabled` | on | off: no round, no lookups |
| `artist_auto_approve_dry_run` | **on** | verdicts only; off applies them, earlier dry-run approvals included |
| `artist_auto_approve_interval_hours` | 24 | |
| `artist_auto_approve_backlog_slice` | 300 | 0 = new names only |
| `artist_auto_approve_max_names` | 1000 | ceiling per round, new names included |
| `artist_auto_approve_max_minutes` | 180 | a round stops here; the next continues |
| `artist_auto_approve_recheck_days` | 90 | when an unresolved name is asked again |

**Why dry run defaults to on.** The rules are the ones that produced the 5.903 approvals Teun
reviewed and applied, so the evidence is not the risk; the risk is a loop that writes decisions
unattended for the first time. Starting in dry run costs nothing -- the first live round applies
every approval the dry runs stored -- and the switch is one click after reading a round's summary
and its list under `GET /api/rules/artists/auto-approve/runs`. Enabled defaults to on so those
dry-run rounds happen without a deploy step.

### Review and undo

No new audit table: `rules_artists.decided_by = 'auto-external'` and `decided_at` are the audit,
`DELETE /api/rules/artists/{name}` is the undo, as for the hand-run tool. What was missing was a
way to find them among 6.300 approvals: `GET /api/rules/artists` gains `decided_by` and
`sort=decided`, and the Goedgekeurd tab a "Automatisch (bewijsronde)" chip (the existing advice
chip style, so no styleguide change). `GET /api/rules/artists/auto-approve/runs` lists the ledger
and what each round judged approvable, applied or not.

### Measured load (production, read-only, 2026-09-27)

49.382 undecided names; 325 of them pending (arrived since the wiring deploy two days earlier),
318 with tracks. By track count: 3.542 with none (never looked up), 41.285 with 1-4, 4.041 with
5-19, 514 with 20+. The hand-run of 2026-09-20 covered names with 5+ tracks, so most of those left
are its unresolved ones and wait for `recheck_days`.

Throughput from the hand-run: 40-60 names/min for big names (approval on the first source),
~16/min for 1-4-track names, where every source is asked -- iTunes' 3.2 s spacing dominates, about
4 s per name. A quiet day (20-35 new names) plus the 300-name backlog slice is ~330 names, **about
20-25 minutes a day**. A burst of 1.000-1.700 new names after a mass retag fills `max_names` (1.000
names, ~65 minutes) and spreads over two days. The backlog of ~45.800 names with tracks takes about
150 days at 300 a day; at the hand-run's measured rate of 48 approvals per 200 small names that is
~70 approvals a day for a curator to spot-check. Raising the slice is the lever if that is too
slow; the 180-minute bound caps it at roughly 2.500 names a round.

### Tests

`services/music_manager/tests/test_artist_auto_approve_worker.py`: the settings and their schema,
per-source spacing with an injected clock, `Retry-After`, the Deezer quota answer, a stop during a
pause, the round through the real `resolve` (approve on two titles, one title is not enough, brand
and tagger-ruled names skipped without a request), dry run writes no decision, turning dry run off
applies stored approvals, the time bound, the candidate bounds, the due check and the loop's stop
event and heartbeat window. `tests/integration/test_artist_auto_approve_worker.py`: every
`EvidenceStore` query against MariaDB (candidate order and exclusions, recheck, apply never over a
decision, an undone approval never returns, the ledger). `tests/integration/test_router_sql.py`:
the review list and the runs endpoint.

### Tests

`services/common/Helpers/TrustedArtistHelperTest.py` (the helper loads the trusted query only,
approved spelling wins, prompt approval is a decision), `services/tagger/Song/rules/TrustedArtistRulesTest.py`
(the Premiere title picks the marker while it is trusted and the real artist while it is only
pending; an untrusted remixer is not credited; a rejected name's correction is applied; a pending
name is left alone), `tests/integration/test_artist_curation_wired.py` (against MariaDB: the
trusted query, the scanner leaving a new name pending through two files, the seed running once,
decide/undo moving a name in and out of trust, and the auto-approve snapshot offering a pending
name).

## Components

| Component | Responsibility |
|---|---|
| `services/common/Helpers/ArtistNameAnalyzer.py` | Turns one raw name into a `Proposal`. Pure: no database, no network. |
| `tools/artist_curation_report.py` | Reads the artist list, runs the analyzer over it, prints the funnel and samples. Changes nothing. |

`Proposal` carries `kind` (`keep`, `rewrite`, `split`, `reject`, `unknown`), the resulting `values`, a
`confidence`, and `evidence` — the reasoning in words. `unknown` carries the input unchanged: it means "no
mechanical answer", which is a queue entry, never a decision.

## The pipeline

Order matters, and is chosen so the cheapest and most certain answers come first:

1. Exact match against the approved dictionary — keep, or rewrite to the approved spelling.
2. No letters at all — reject.
3. Strip affix noise, then match the remainder against the dictionary. This is one mechanism for
   `#1 Terrorclown`, `& R3trix` and `**FREE DOWNLOAD** DJ KURT`, which are the same case.
4. Junk score — reject if it clears the threshold.
5. Dictionary segmentation for glued names.
6. Fuzzy match against the dictionary.
7. Otherwise unknown.

**Junk is scored, and the score does not reject.** The signals are individually weak: four words is normal
for an artist, and so is a bracket. The first run over the real library showed they stay weak in combination
too — `Boaz Van De Beatz`, `We Are Loud` and `The Beholder (Neophyte)` are real artists that score exactly
like a stray quote does. The score is therefore reported and the name is flagged in the queue;
`reject_on_junk_score` turns it into a removal for anyone who wants that. What still rejects outright is
narrower and unambiguous: a name with no letters in any script, and a name with nothing left once the promo
noise is stripped — which is how `Premiere`, 9180 tracks on its own, gets dealt with.

**Segmentation is off by default.** It is dictionary-driven and refuses spaced input, and a name that is
itself approved is never segmented, which stops `Warface` becoming `War` + `Face`. That was not enough. On
the real library it produced 122 splits that were almost all wrong — `Technotronic` into `Techno` + `Tonic`,
`Freestyle` into `Free` + `Styles`, `Coldfire` into `Cold` + `Fire` — because a dictionary bootstrapped from
the data itself contains enough short common words to take any compound apart. The code and its tests stay;
`enable_segmentation` is worth turning on once the dictionary holds verified artists instead of a guess.

**The fuzzy threshold is arithmetic, not taste.** One wrong character in a name of n characters scores
`1 - 1/n`, so 0.90 would only reach names of ten characters and up. The default of 0.87 reaches down to
eight. Below that the same ratio starts matching genuinely different short names, so those are left to a
human — `ArtistNameAnalyzerTest` pins both sides of that boundary so the cost of the default is visible.

**The normalisation key is script-aware.** Deciding alphanumeric per character rather than with an `a-z0-9`
range is not pedantry: the library holds Cyrillic artists, and a Latin-only key collapses every one of them
to the empty string — indistinguishable from a name of pure punctuation, and the first run duly proposed
deleting all of them.

**Matching is blocked by first character and length.** Comparing every name against every approved artist is
quadratic and does not survive 51k names against a 7k dictionary; the first full run did not finish in twenty
minutes. Length blocking is free, because a required similarity bounds how far the lengths can differ.
First-character blocking is not free, and is the deliberate trade that makes a run practical: a typo in the
first character is not corrected automatically and lands in the queue instead. That is the safe direction to
be wrong in, and rarer than a typo anywhere else.

## Bootstrapping the dictionary

Matching against approved artists needs approved artists, and there are none yet. The seed is built from the
data itself: a name with no detectable noise, that is not sentence-like, that occurs on at least
`bootstrap_min_tracks` tracks **and across at least two folders**.

Spread rather than track count is the signal that matters. Junk sprayed by one bad tagger rule has a high
track count but sits in a single folder; a real artist turns up across many folders, labels and years. That
same concentration also identifies the rule that produced a class of junk, which is worth fixing at the
source — the lesson the genre work already taught.

This bootstrap is optimistic by construction: it approves clean-looking names on circumstantial evidence
alone. That is acceptable for a dry run whose purpose is to show what happens, and it is exactly what the
external-lookup phase is meant to replace. The report prints the seed size so its influence is never hidden.

The first run made the weakness concrete. It seeded 7081 names, and among the most widespread of them are
`Autektone Records`, `Sick Events`, `DJ Mag` and `The Boom Room` — a label, an event organiser, a magazine
and a radio show. All are real entities and none is an artist, which is a distinction no amount of string
shape can make. It also means a correction can point at the wrong spelling: `Rbr` is rewritten to `RBR ©`
because that variant happened to be seeded first.

## What the first run over the real library found

51378 names against a 7081-name seed: 7030 kept (13.7% of names but 76% of all track assignments), 3440
rewritten onto 1775 distinct targets, 255 removed, and 40653 left for a human or an external lookup — 16.3%
of track assignments, of which 1484 are flagged as sentence-like.

The shape of that result is the point. The mechanical answers are concentrated where the tracks are, and the
long tail really is a tail. The single largest win available is one name: `Premiere`, 9180 tracks.

## Configuration and re-runnability

Every threshold lives in `AnalyzerConfig`, with `from_dict` so `ConfigStore` can supply it later. Because the
analyzer is pure and holds no state between names, a re-run with different thresholds is just another run —
there is nothing to reset.

The rule that makes this safe when it eventually writes anything: raw name, derived proposal and human
decision must stay three separate things, and a re-run must never touch a decision a human made. That is the
same `decided_by` rule the genre work established.

## Technical Acceptance Criteria

1. Every one of the maintainer's real examples produces the specified `kind` and `values`.
2. `propose` on an unrecognised name returns `unknown` with the input unchanged, never `reject`.
3. `propose` returns non-empty `evidence` for every input.
4. `strip_affixes` reports what it removed and handles several layers in one name.
5. `segment` returns None for any input containing whitespace.
6. `segment` returns None when the whole name is itself an approved artist.
7. A single-character typo in an eight-character name is rewritten; in a seven-character name it is not.
8. Changing `fuzzy_rewrite_threshold` or `junk_score_threshold` changes the outcome for the same input.
9. `AnalyzerConfig.from_dict` ignores keys it does not know and falls back to defaults when given nothing.
10. `build_seed` excludes names below the track threshold, names confined to a single folder, names carrying
    noise, and sentence-like names.
11. Adding an artist to the dictionary changes a previously unknown variant of it into a rewrite.
12. A Cyrillic name is never rejected for having no letters, and two different Cyrillic names get two
    different keys.
13. `Boaz Van De Beatz`, `We Are Loud` and `The Beholder (Neophyte)` are not removed by the default config;
    `Premiere`, `FREE DOWNLOAD` and `OUT NOW` still are.
14. Turning `reject_on_junk_score` on turns a flagged sentence into a removal.
15. `enable_segmentation` is off by default, and turning it on restores splitting.
16. The length window always contains the length itself and narrows as the threshold rises.

## Related Docs

- [docs/designs/genre-curation/technical.md](../genre-curation/technical.md) — the curation model this mirrors
- [docs/database-design.md](../../database-design.md) — table inventory
