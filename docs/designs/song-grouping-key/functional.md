# Song grouping key — Functional Design

## Overview

MuMa puts every version of one song in one *work*. Lists collapse to one row per work, and the
ranking chooses which version plays (see [song-versions](../song-versions/)). This change covers
only *which tracks share a work*, not which one wins. Bug report
[098](../../bug-reports/098-song-grouping-key.md) measured two faults. Versions of one song stayed
apart because their titles were spelled with markers the key did not know. And whole upload series
shared one work because the tagger misparsed their titles.

## User Stories

- As a listener, I want "Lost On You" and "Lost On You - Official Hardcore Visualizer" to be one
  song, so that my Release Radar shows it once.
- As a listener, I want a remix, a VIP or a bootleg to stay a song of its own, so that collapsing
  never hides it.
- As the curator, I want a work that holds a whole series of different songs to be split, or at
  least listed, so that I can fix what collapsing hides.
- As the curator, I want my pins and splits to survive a regroup.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Title ends in "(Official Audio)", "(Official Music Video)", "(Pro Mix)", "(Pro Edit)", "(Visualizer)", "(Official Lyric Video)" | Same work as the plain title |
| Title ends in " - Official Video", " - Official Hardcore Visualizer", " \| Official Visualizer", "† - Official Preview [OUT NOW]" | Same work as the plain title |
| Title ends in "(Hardcore Mix)", "(Wildstylez Edit)", "(Remix)", "(VIP)", "(Bootleg)", " - Official Defqon.1 Anthem" | Its own work |
| Artist "CHEEVA & D-sire" with the same title as "Cheeva" | Same work |
| Artist "Code:Red" vs "RED", same title | Different works (different lead artists) |
| Artist field "Official Preview" | Treated as no artist |
| A work holds more than 12 different lengths | Split: every track gets a work of its own, locked like a manual split |
| A work looks odd but is below that line | Listed in the false-merge report, left alone |
| The regroup script runs | Dry run first with counts. Hand-split tracks and pinned versions stay where they are |

## Acceptance Criteria

1. The Release Radar examples of 2026-09-26 group with their plain titles after the regroup.
2. No remix, VIP, bootleg, named edit or genre rework joins the original's work.
3. `q dance:::next`, `q dance:::speqtrum`, `gearbox:::lockdown` and `q dance:::qore` no longer
   hide their songs.
4. A pin or a manual split made before the regroup is still in place after it.

## Open Questions / Not Yet Decided

- Whether the tagger should parse "... | Q-dance presents NEXT" titles correctly. That is a separate
  tagger change. Until it lands, the worker splits a regrown series again.
- Remixer-as-artist ("Dj Furax" vs "MANDY" on one remix) stays apart. Merging it would need a
  guess about who the lead artist is.
