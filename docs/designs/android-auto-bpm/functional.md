# Browse by BPM in Android Auto — Functional Design

> Issue #140. Follows [bpm-browse](../bpm-browse/functional.md) (the web/phone page, 0.84.0) and
> the car tree in [android-auto-browse](../android-auto-browse/functional.md).

## Overview

The web and the phone have a BPM page since 0.84.0; the car did not. This adds a **BPM** folder to
the car's browse tree: a short fixed list of tempos, each opening the tracks at that tempo, playable
with one tap. It is for picking music by energy while driving without typing anything.

## User Stories

- As a driver, I want to pick "150 BPM" and hear hardstyle at that tempo, without typing or
  scrolling through a genre tree.
- As a driver, I want to see roughly how many tracks each tempo has, so I do not open an empty one.
- As a driver, I want a tempo list to keep playing past the first hundred tracks.

## Where it sits

The root keeps its four tabs (Start | Nummers | Sets | Bibliotheek, "never a fifth"). **BPM** is one
more row in the **Nummers** tab's *Bladeren* group, after Lineups — the same place the web's
Bladeren grid lists it, and like there only for songs: a set has no one tempo, and the server's
BPM index holds tracks only. The issue's "under Meer" predates the four-tab tree; there is no Meer
any more.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Open Nummers → BPM | Ten rows: 140, 150, 155, 160, 170, 175, 180, 190, 200 BPM and 210+ BPM, each with "N nummers" below it. |
| MuMa unreachable when opening BPM | The same ten rows, without counts. |
| Open "150 BPM" | "Alles afspelen", then up to 100 tracks, nearest 150 first (a measured 150.0 before a tag that says 152). |
| Tap "Alles afspelen" | The list plays from the top; when three tracks are left the next hundred are appended, and so on to the end. |
| Tap a track | The list plays from that track, and continues the same way. |
| MuMa or the streaming server unreachable when opening a tempo | An empty list; opening it again a moment later asks again. |
| "210+ BPM" | Everything from 208 BPM up, slowest first. |

A tempo row means that tempo ± the server's tolerance (Management > Configuration → BPM, default 2).

## Acceptance Criteria

1. The Nummers tab has a BPM row; the Sets tab and the root do not change.
2. The BPM folder lists the ten tempos above, each with a count when MuMa answers.
3. A tempo opens a play-all row and its tracks in MuMa's order.
4. Play-all and a tapped track both keep playing past the first 100 tracks.
5. An unreachable MuMa never breaks the tree and is never remembered as "no tracks".

## Open Questions / Not Yet Decided

- Whether the car should offer "Betrouwbaar" (reliable measurements only) as a separate row per
  tempo. Left out: once the background measurement (0.85.0) has passed over the library nearly
  every track is measured, and a second row per tempo doubles the list a driver scrolls.
- Whether the counts shown are right in the car and the rows are readable at a glance: a drive
  (verify issue).
