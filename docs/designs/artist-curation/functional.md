# Artist Curation — Functional Design

## Overview

`library_artists` holds tens of thousands of names of which the maintainer estimates roughly one in ten is
a real artist. The cause is the same shape as the genre problem solved in 0.0.52: the table that is supposed
to say what a real artist *is* fills itself. `services/music_manager/routers/scanner.py` inserts every artist
string it encounters, so anything a tagger rule ever produced counts as an artist from then on.

The pollution is not uniform, and that is what makes it tractable. It falls into recognisable classes:

- noise wrapped around a real name — `#1 Terrorclown`, `& R3trix`, `**FREE DOWNLOAD** DJ KURT`
- two real names glued together without a separator — `AngerfistHeadhunter`
- a misspelling of a name already in the library
- a sentence a tagger rule mistook for an artist — `Als wij samen komen(`
- names that are simply unknown, which includes real artists who are not on any streaming service

Each class has a mechanical answer, except the last. This feature is about generating those answers with
their reasoning attached, so a human decides only what genuinely needs deciding.

## User Stories

- As the library owner, I want the obvious cases resolved without me, so that I am not making fifty thousand
  decisions by hand.
- As the library owner, I want to see *why* something is proposed, so that I can trust a bulk approval.
- As the library owner, I want to tune how aggressive the cleanup is, because I cannot say up front what
  "good enough" means — and I want to re-run it after tuning without losing decisions I already made.
- As the library owner, I want an artist that exists but is on no streaming service to end up in my queue,
  not in the bin.
- As the library owner, I want to know what a run *would* do before it does anything.

## Functional Flows

| Situation | Proposed outcome |
|---|---|
| Name matches an approved artist | Keep it, in the approved spelling |
| Name differs only in casing, accents or punctuation | Rewrite to the approved spelling |
| Promo noise around an approved name | Rewrite to the name, listing what was removed |
| Name is two or more approved names glued together, without spaces | Split into those names |
| Name is one character off an approved name of eight characters or more | Rewrite, with the similarity shown |
| Name reads like a sentence: function words, brackets that do not close, sentence punctuation | Propose removal, listing every signal that fired |
| Name contains no letters at all | Propose removal |
| Anything else | No proposal — the name goes to the queue unchanged |

## Acceptance Criteria

1. Each of the maintainer's real examples resolves to the outcome they specified, and those examples are the
   test suite.
2. A name that is not recognised is never removed. Absence of evidence is not evidence of junk.
3. Every proposal carries the chain of reasoning that produced it, in words.
4. A proposal is never applied by the run that produces it — it is a report first.
5. Every threshold is configurable, and running with different thresholds produces different proposals from
   the same input without any state carrying over.
6. Names with spaces are never split. A spaced string that needs splitting is a delimiter bug in the tagger,
   and guessing there would invent artists that were never in the tag.
7. Approving an artist improves the next run: the same polluted variant that had no answer before resolves
   once its target is in the dictionary.
8. The report states how many names collapse onto how many distinct targets, so the size of the remaining
   work is visible rather than estimated.

## Open Questions / Not Yet Decided

- The auto-approve threshold for external evidence — proposed: an exact MusicBrainz match, or two
  independent sources agreeing — is not settled and no external lookups are performed yet.
- Whether the scanner should start placing new artists in an undecided state instead of approving them on
  sight. That is the actual bug fix, but it makes the queue start at its full size.
- Preserving the original name in `TXXX:ORIGINAL_ARTIST` during a tag pass the file needs anyway is agreed
  in principle, with the database as the source of truth. Not built.
- Splitting composite artist strings that already contain separators is deliberately out of scope here.
