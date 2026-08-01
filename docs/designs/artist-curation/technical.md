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
