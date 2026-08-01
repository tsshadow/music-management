# Genre Curation States — Functional Design

## Overview

Genres arriving from SoundCloud, YouTube, label promo folders and the inference rules are noisy: a track can
carry anything from `Hardstyle` to `Entertainment`, `Arts` or a misspelling of a genre we already know. Until
now the library accepted any genre it had seen before, because the rule that registered an unknown genre for
review ran immediately before the rule that accepted anything already registered. A genre was therefore
detected and approved within the same tagging pass, and the review list only ever grew.

This feature gives every genre one explicit curation state — kept, dropped, or awaiting a decision — and makes
the tagger act on that state instead of on the order its rules happen to run in. A genre nobody has judged yet
is left alone: it is not written into the library and it is not deleted from the file either, so no decision is
made on the user's behalf.

## User Stories

- As the library owner, I want genres I have approved (`Hardstyle`, `Uptempo Hardcore`) to be applied
  consistently, so that browsing by genre returns what I expect.
- As the library owner, I want junk genres (`Entertainment`, `Arts`) removed from my files automatically, so
  that I do not have to clean them up track by track.
- As the library owner, I want near-misses corrected rather than dropped (`uptempo` becomes
  `Uptempo Hardcore`, `rawstyle` becomes `Raw Hardstyle`), so that useful information is not thrown away.
- As the library owner, I want genres I have not judged yet collected in one list ordered by how often they
  occur, so that a few decisions clean up most of the library.
- As the library owner, I want my decisions to stick, so that the tagger never silently reverses them on a
  later run.
- As the library owner, I want to make those decisions from the management UI rather than by calling the API,
  so that curating the backlog is a few clicks per genre.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Track carries an approved genre | Genre is kept, in the spelling and casing recorded in the rules |
| Track carries an approved genre with a correction target | Genre is replaced by the correction, e.g. `rawstyle` becomes `Raw Hardstyle` |
| Track carries a rejected genre | Genre is removed from the track |
| Track carries a rejected genre with a correction target | Genre is replaced by the correction, e.g. `uptempo` becomes `Uptempo Hardcore` |
| Track carries a genre nobody has judged | Genre stays on the track untouched and appears in the curation list, with a counter of how often it has been seen |
| The same unjudged genre is seen again | Counter goes up; the genre is still not approved |
| Owner approves or rejects a genre from the curation list | The decision is recorded against their name and applies from the next tagging run onwards |
| Track carries an empty or whitespace-only genre | Genre is removed |
| Two spellings of the same genre (`Raw Hardstyle`, `raw-hardstyle`) | Both resolve to the same rule; no duplicate entries in the curation list |
| Track carries `Hardstyle/Hardcore` | Treated as two genres, each judged on its own; the combination never reaches the curation list |
| Track carries a slash genre the owner has explicitly decided on | Left whole, because a decision outranks the split |
| Track carries a contraction such as `Upterror` | Replaced by every genre it stands for: `Uptempo Hardcore` and `Terror` |
| Owner opens the Genre Curation page | The unjudged queue is shown first, most frequent genre on top, with what each genre currently does to a tag |
| Owner approves or rejects a genre from that page | The row disappears from the queue and the decision, with their name, shows up under the matching filter |
| Owner corrects a genre from that page | They pick a target from the approved genres only, and the page states the genre will be replaced by it |
| Owner changes their mind about a decided genre | The same actions are available on approved and rejected genres, so a decision can be reversed or turned into a correction |

## Acceptance Criteria

1. A genre marked as kept ends up on the track in the spelling stored in the rules, regardless of the casing
   or punctuation the source file used.
2. A genre marked as dropped no longer appears on the track after tagging.
3. A genre with a correction target appears on the track as the correction target, whether the genre itself is
   marked kept or dropped.
4. A genre no one has judged is left on the track exactly as it was, and is not written into the library.
5. The same unjudged genre seen on ten tracks appears once in the curation list with a count of ten.
6. The curation list can be requested filtered to unjudged genres, ordered by that count, highest first.
7. A decision made by the owner is stored with who made it and when, and is not overwritten by any later
   automatic run.
8. Genres approved, rejected or queued before this change keep their meaning afterwards; nothing that was
   already curated has to be curated again.
9. The management UI has a Genre Curation page that opens on the unjudged queue and can be switched to the
   approved, rejected and complete lists.
10. Every row states in words what the genre currently does to a tag, so no knowledge of the state model is
    needed to curate.
11. A correction can only point at an approved genre, and never at the genre being decided.
12. The page says that decisions take effect from the next tagging run, so nobody expects existing files to
    change immediately.
13. A genre containing `/` is split into its parts unless it has been decided on, so a name that genuinely
    contains a slash is protected by approving it once.
14. A genre can be corrected to more than one genre at a time, which is how a contraction is expressed.
15. Slash genres that only the migration ever approved are split automatically, without anyone having to
    review them one by one.

## Open Questions / Not Yet Decided

- Existing tracks are not re-tagged automatically after a decision — that requires a re-tag run, which is
  triggered manually for now.
- `library_track_genres` still has an unused `weight` column, and machine-learning genre predictions still
  live separately in `library_track_ml_labels`. Merging tag-derived and predicted genres into one weighted
  model is deliberately left out of scope.
