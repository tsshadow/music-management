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

- ~~The auto-approve threshold for external evidence.~~ Settled in `tools/artist_auto_approve.py`
  (MR !874, three rules on matching recording titles) and run on a schedule since 2026-09-27, see
  "Scheduled evidence run" below.
- ~~Whether the scanner should start placing new artists in an undecided state instead of approving them on
  sight.~~ Decided and built 2026-09-25, see "Wiring the queue" below. The queue does not start at its
  full size: the names already in the library keep being trusted until someone decides on them.
- Preserving the original name in `TXXX:ORIGINAL_ARTIST` during a tag pass the file needs anyway: built.
  `CleanTagsRule` captures the artist string before its regex split discards the "feat"/"vs"/"&" wording,
  written to disk as `TXXX:ORIGINAL_ARTIST` and mirrored into `library_tracks.display_artist` by the
  scanner. Display only — never re-parsed, never matched against this analyzer's dictionary.
- **Correction to the line above, measured 2026-09-06.** "A file gains it at its next tag pass" is wrong.
  The capture only fires at the moment the split happens, so a file that is *already* split has nothing
  left to capture and never fills in — permanently, not temporarily. Of 400 files sampled under the EPs
  root, 120 carry a split artist and none still carry the original wording. The surviving source is the
  NFO that shipped with the release, which is written before any tagging;
  `scripts/backfill_original_artist_from_nfo.py` reads it back, guarded so a write can only restore
  wording and never change which artists a track names. Soundcloud, Youtube and artists have no NFOs at
  all, so nothing outside the EPs tree can be recovered this way.
- Splitting composite artist strings that already contain separators is deliberately out of scope here.

## Wiring the queue (2026-09-25)

The analyzer and the queue existed, but the tagger never consulted them: any name the scanner found
in a file counted as a known artist from then on, including names a tagger rule had only guessed
out of a title. The next title containing that guess was then read with the guess as its artist.

| Situation | What happens now |
|---|---|
| A name appears for the first time (download, import, retag) | It is recorded and listed in the queue as **Nieuw** (pending). The tagger does not recognise it in titles until it is approved. |
| A name was already in the library before this change and is undecided | Nothing changes: the tagger keeps recognising it, and it stays in the queue as "to review". |
| A name is approved -- by hand or by the external-evidence run | The tagger recognises it from then on. |
| A name is rejected | As before, it is removed or rewritten on the next tag pass -- and that now also happens for files where it used to be silently skipped (see the technical design). |
| A file whose only artist is pending | Left exactly as it is: its tag is not changed, the track stays findable under that name, and the name is in the queue with its track count. Nothing is deleted and nothing is written to the file. |

Acceptance criteria:

1. A name recorded by the scanner after this change is never used by an artist rule until it is
   approved, however many files carry it.
2. An approved or auto-approved name behaves exactly as before.
3. A name that was in the library before this change behaves exactly as before until it is decided.
4. The queue shows which of its names are pending, and the summary counts them.
5. The external-evidence run still considers pending names.

Expected growth, measured on production: about 20-35 new names on a quiet day and 1.000-1.700 after
a mass retag, ~3.500 in the last 30 days. See the technical design for the numbers.


## Scheduled evidence run (2026-09-27, issue #49)

The external-evidence run approved 5.903 names when it was run once by hand on 2026-09-20; since
then new names only left the queue when a curator decided them (8 of ~3.300 in the first thirty
days). It now runs by itself inside music-manager, once a day.

| Situation | What happens |
|---|---|
| A name arrived since the last round (pending, **Nieuw**) | Looked up in the next round, before anything else. |
| An older, grandfathered undecided name | Looked up a slice at a time, most tracks first (300 a day by default). |
| The evidence clears a name (the tool's three rules, unchanged) | Dry run (the default): recorded as approvable, nothing changes. Live: approved, signed `auto-external`, recognised by the tagger at once. |
| The evidence does not clear a name | Stays in the queue as it was. Looked up again after 90 days. Never rejected. |
| A curator undoes an automatic approval | The name goes back to the queue and the run never approves it again. |
| A curator decided a name while a round ran | The curator's decision stands; the run never overwrites a decision. |

**Dry run is on by default.** This is the first thing in the system that writes curation
decisions on its own every night. The first rounds show in the event log, and under Management ->
Curatie -> Artiestcuratie, what they would approve; one switch in Management > Configuration ("Artist
curation") turns approving on, and the first live round then applies everything the dry runs
judged approvable as well, so nothing is lost by starting in dry run.

**Review and undo.** On the "Goedgekeurd" tab, the "Automatisch (bewijsronde)" filter lists the
names the run approved, newest first, each with the existing undo button.

Acceptance criteria:

1. A round never looks up more than `artist_auto_approve_max_names` names and never runs longer
   than `artist_auto_approve_max_minutes`; what is left is continued the next day.
2. A dry run writes no decision.
3. A name is approved only on the tool's own rules; nothing is ever rejected automatically.
4. Each round writes exactly one INFO line to the event log with what it did.
5. An automatic approval can be found and undone in Management, and an undone name is not re-approved.
