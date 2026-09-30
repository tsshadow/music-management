# Browse by BPM — Functional Design

## Overview

Teun asked to browse the library by tempo: "show me all the 150 BPM tracks". Today there is no way to
do that. There is also a data problem underneath it: not every track has a BPM, and the ones that do
are mostly not accurate enough to answer that question.

The BPM values in the library came from an old analyzer (the deprecated ml-analyzer and the tagger's
`analyze_bpm` rule, both librosa at its default settings). That analyzer can only produce a coarse set
of values, roughly 4 to 9 BPM apart around the tempos this collection plays: 143.6, 147.7, 152.0,
156.6, 161.5 and so on. A track at 150 and a track at 155 both read 152. The file tags were mostly
written from that same analyzer, so they carry the same steps. About 27% of the library has any BPM
at all (89,869 of 326,875 tracks on production on 2026-09-29), and where both a tag and an analyzer
value exist, about a quarter of the pairs are an octave apart, because the analyzer often reads a
hardstyle track at half its tempo.

Teun has decided that the incomplete data must not hold up the browse feature. It is built in two
changes:

1. **Browse now, on the data we have** (this design, first merge request). A BPM page under Bladeren
   that works with the existing values. It is honest about their coarseness, and its default margin
   is wide enough that "150" finds the tracks the old analyzer rounded to 152.
2. **Better data after** (second merge request). A background job measures each track's tempo
   precisely (to 0.01 BPM) from a short excerpt of the audio and stores the result. The browse page
   prefers a measurement over the old values the moment one exists, with no other change.

## User Stories

- As a listener, I want to see and play every track at a given tempo (150, 155, 200...), so that I can
  put on a run of tracks that mix together or that suit what I am doing.
- As a listener, I want to widen or narrow how exact that tempo is, so that I can choose between "only
  150" and "roughly 150".
- As a listener, I want to limit the list to one genre, so that 150 BPM hardstyle does not come mixed
  with 150 BPM techno.
- As a listener, I want to hide tempos that are only guesses, so that when I care about accuracy I only
  get tracks whose tempo is trustworthy.
- As a listener, I want to see how the library spreads over tempos, so that I can spot what is there
  and jump to it.
- As a listener, I want to see each track's BPM in the list, and whether it is exact or rough, so that
  I know how far to trust it.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Open Bladeren (phone) or the sidebar (web) in songs mode | A "BPM" entry with a gauge icon sits after Lineups. It is not shown in sets mode: a two-hour mix has no one tempo. |
| Open the BPM page | Title "BPM", a row of tempo chips (128, 140, 150, 155, 160, 165, 175, 190, 200, 210, 230), each with how many tracks it would find, a margin selector (±0.5, ±1, ±2, ±3, ±5; ±2 selected), a from-to range, a genre picker, a "Betrouwbaar" switch, and a bar chart of tracks per BPM from 60 to 260. Below: "Kies een tempo of een bereik om de nummers te zien." No list yet. |
| Tap the 150 chip | The chip turns green. The list shows every track from 148 to 152 BPM, the ones closest to 150 first and, at the same distance, the more trustworthy first. The header says "150 BPM · N nummers" and there is a play button. The chart bars from 148 to 152 light up. |
| Tap the same chip again | The selection is cleared and the prompt comes back. |
| Tap a bar in the chart | Same as a chip for that tempo. |
| Choose ±1 | The list narrows to 149-151. |
| Type 170 in "van" (and optionally 180 in "tot") | The list shows every track from 170 up (to 180), in tempo order. A picked chip is cleared. |
| Pick "Frenchcore" in the genre picker | The list, the chip counts and the chart only count Frenchcore tracks. The picker offers the 40 genres with the most tracks that have a BPM, each with its count. |
| Switch "Betrouwbaar" on | Only tempos MuMa trusts remain: a measurement (once the second change runs), or a tag that the old analyzer agrees with and that already fits the genre's tempo. Chip counts and chart follow. |
| A track's tempo is one of the old coarse values | Its row shows a small pill "≈152 BPM". Under the header, once, in muted text: "≈ betekent grof gemeten: de oude analyse kon alleen stappen van zo'n 4 tot 9 BPM (152, 156, 161 ...). Nauwkeurige metingen komen er nog aan; tot dan vangt de marge de afronding op." |
| A track's tempo was measured (second change) | Its pill shows "150 BPM" without the ≈. |
| Hover over (or long-press) a pill | It says where the tempo came from: measured, the file's BPM tag, or the old analysis, and whether it was doubled or halved into the genre's tempo. |
| Press play, or tap a row | The list plays as a queue in the order shown, named "150 BPM". Near the end of what is loaded the queue fetches the next page by itself, like a feed. |
| More than 100 tracks match | The list ends in the usual "Meer laden" pill. |
| Nothing matches | "Geen nummers op dit tempo." With Betrouwbaar on: "Geen betrouwbare tempo's hier. Zet Betrouwbaar uit om ook de grove waarden te zien." |
| MuMa or the server cannot be reached | The list area shows the usual section error with "Opnieuw". |
| A track's old value is half or double what its genre plays (a hardstyle track read at 76) | It is listed at the tempo that fits the genre (152), marked as low confidence. |

## Acceptance Criteria

1. Bladeren (phone) and the sidebar (web) have a "BPM" entry in songs mode, and not in sets mode.
2. Tapping the 150 chip with the default margin lists the tracks whose tempo is 152.0 in the old data
   (the "150-155 bucket"), and the tracks measured between 148 and 152.
3. The margin, the range, the genre and "Betrouwbaar" each change the list, the chip counts and the
   chart as described above.
4. Every row in the list shows its BPM; old coarse values show "≈", measured ones do not.
5. The note about coarse values appears once above the list when the list holds any, and never as a
   popup, banner or dialog.
6. The play button queues the list in its shown order, and the queue continues with the next page.
7. Sets and podcasts never appear in the list.
8. The default margin (±2) can be changed on Beheer → Config → BPM (`bpm_browse_tolerance`).
9. (Second change) Newly downloaded tracks get a measured tempo within minutes; the backlog is worked
   through newest first. Beheer → Config → BPM can switch the measuring off, pause it, and set how
   many tracks it measures at once and how much of each track it listens to. A measured tempo shows
   without "≈" and counts as reliable when the measurement is confident.
10. (Second change) The measuring never rewrites a file and keeps the server responsive: it runs
    apart from the rest, on at most two cores by default, at the lowest priority.
11. (Issue #141) A track shows one tempo everywhere: the track details sheet, the library table's BPM
    column (and its sort, where tracks without a BPM come last whichever way it sorts), the BPM
    filter and the search box's "type a number to search a tempo", and the BPM chart under Beheer →
    Bibliotheek all use the tempo the BPM browse shows (so do the daily mixes, where a track with no
    genre, label or artist to go by is placed by its tempo), and every place that prints it marks a
    value that is not measured with "≈". A new measurement appears in the library table within
    minutes of being made.

## Open Questions / Not Yet Decided

- **Writing a measured BPM back into the file's TBPM tag.** Not in either change. Decided later
  (issue #139): yes, see [bpm-tag-writeback](../bpm-tag-writeback/functional.md).
- **The same browse in Android Auto.** The car's browse tree is native (MediaLibrary), not this web
  page; a BPM folder there is a follow-up, not part of this change.
