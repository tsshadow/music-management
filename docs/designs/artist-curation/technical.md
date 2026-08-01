# Artist Curation — Technical Design

Implements [`functional.md`](functional.md).

## What this change delivers

The analysis engine and a dry-run report, and nothing else. No schema change, no tagger rule, no API, no UI.
Thresholds cannot be chosen in the abstract, so the first deliverable is the thing that lets them be chosen
by looking at the real library.

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

**Junk is scored, not ruled.** The signals are individually weak: four words is normal for an artist, and so
is a bracket. Dutch or English function words plus unclosed brackets plus sentence punctuation together stop
being normal. Scoring keeps the threshold a single tunable number and keeps every contributing reason
reportable.

**Segmentation is dictionary-driven and refuses spaced input.** Every segment must match an approved artist,
so the dictionary decides where boundaries fall rather than the analyzer guessing. A whole name that is
itself approved is never segmented, which is what stops `Warface` becoming `War` + `Face`.

**The fuzzy threshold is arithmetic, not taste.** One wrong character in a name of n characters scores
`1 - 1/n`, so 0.90 would only reach names of ten characters and up. The default of 0.87 reaches down to
eight. Below that the same ratio starts matching genuinely different short names, so those are left to a
human — `ArtistNameAnalyzerTest` pins both sides of that boundary so the cost of the default is visible.

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

## Related Docs

- [docs/designs/genre-curation/technical.md](../genre-curation/technical.md) — the curation model this mirrors
- [docs/database-design.md](../../database-design.md) — table inventory
