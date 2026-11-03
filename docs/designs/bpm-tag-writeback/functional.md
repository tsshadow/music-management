# Measured BPM into the file tags — Functional Design

## Overview

Browse by BPM ([bpm-browse](../bpm-browse/functional.md)) measures every track's tempo to 0.01 BPM
and keeps the result in MuMa's database. The files themselves still carry whatever BPM tag they
arrived with: for most of the library nothing, and for the rest mostly the old analyzer's coarse
steps (152, 161, 172 ...), a quarter of them an octave off. Anything that reads the file rather than
MuMa's database -- DJ software, another player, a copy of the file on a USB stick -- sees those.

Teun decided (issue #139): "Measured BPM must of course go into the tags." This change writes the
measured tempo into each file's own BPM tag, slowly and in the background, without touching anything
else in the file.

## User Stories

- As a listener, I want a track's file to carry the same tempo MuMa shows, so that DJ software and
  other players agree with MuMa.
- As a listener who tagged some tracks by hand (or bought them with a tempo in the tag), I want a
  tag that already says the right tempo to stay as it is.
- As the owner of the server, I want this to happen without slowing down the app, the tagger or the
  NAS, and to be able to pause it.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A track has a confident measurement (at least `bpm_tag_writeback_min_confidence`, 75%) and no BPM tag | Within a few days of the measurement, the file's BPM tag reads the measured tempo as a whole number (150.02 → 150). |
| The file's tag is the old analyzer's 152 and the track measures 150.02 | The tag becomes 150. |
| The file's tag is 76 or 304 and the track measures 152 | The tag becomes 152 (an octave off is always corrected). |
| The file's tag already says 150 and the track measures 150.3 | Nothing is written: it already matches. |
| The file's tag is 150 -- a whole number the old analyzer could not have produced -- and the track measures 150.9 | Nothing is written: a genuine tag within 1 BPM of the measurement is trusted. At 151.2 it would become 151. |
| The measurement is unsure (below the confidence threshold) | Nothing is written; the file keeps its tag. MuMa still shows the measurement. |
| A set, a podcast, a file in Livesets/Podcasts/Warm Up Mixes, a file under Lidarr, Hitzone or Spotify, or anything in a quarantine, recycle, or `__TODO`/underscore folder | Never written. |
| The file was replaced or changed since it was measured | Not written until it has been measured again. |
| A track is measured again (a new estimator version) and the value changes | Its file is looked at again and, by the same rule, updated. |
| Management > Configuration → BPM: "Write measured tempos into the files" off, or paused | Nothing more is written; switching it on or unpausing continues where it stopped. |
| The tagger has decisions, new downloads or a retag waiting | Those go first; the BPM tags wait for the next round. |
| LMS / the app after a file got its tag | LMS re-reads the folder, as after any tagger change. |

## Acceptance Criteria

1. After the backlog has been worked through, a sample of confidently measured tracks under EPs,
   Soundcloud and Youtube carries a BPM tag equal to the rounded measurement, or a tag that matches
   it within the rule above.
2. Every other tag of a rewritten file (title, artists, genre, label, festival, cover, comments ...)
   and its audio are unchanged.
3. The files the rule leaves alone (matching or genuine tags, unsure measurements, sets and podcasts,
   the excluded folders) are not rewritten; their modification time does not change.
4. The first pass over the library finishes in a few days at the default of 300 files per tagger
   round, and the app stays responsive while it runs.
5. Management > Configuration → BPM can switch it off, pause it, change the number per round and the
   confidence threshold.
6. Writing a tag does not make the BPM analysis measure the file again, and does not put it on the
   tagger's retag queue.

## Open Questions / Not Yet Decided

- **LMS does not show the BPM to Subsonic clients yet.** Its tag reader (TagLib) reads the `BPM`
  property, but LMS stores no tempo per track and its Subsonic answers carry no `bpm` field. Making
  the tag visible in the app through LMS is a separate server change (follow-up issue); MuMa's own
  pages already show the measurement.
- **A precise value in the file** (e.g. a `TXXX:MUMA_BPM` with 150.02) was considered and left out:
  nothing reads it, and the database keeps the precise value.
