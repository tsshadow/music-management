# BPM Octave Choice and Manual Override — Functional Design

## Overview

A tempo measurement cannot tell a song from its double or half time: a ballad at 128 has a pulse at
64 and at 256 as well, a hardstyle kick at 150 also pulses at 75, an industrial track at 115 also at
230. Until now the analyzer settled this by forcing every measurement into a fixed tempo range per
genre, and when a track had no genre, into the range of its artist's most common genre. That put
André Hazes's ballads at 256 (his "genre" in this library comes from hardstyle remixes of his songs)
and The Silence's "Nothing" at 230 (industrial hardcore's range starts at 140), and it marked those
guesses as reliable, so the 0.86.0 tag writeback wrote them into files (bug report 140).

This change makes the analyzer *weigh* the three candidates (half, as measured, double) on what the
collection itself knows: where the label's, the artist's own and the genre's confident measurements
sit, whether the file sits in a pop compilation folder, how clearly the audio pulses at each
candidate. A guessed octave is no longer marked reliable. And anyone with the right permission can
correct a track by hand: halve it, double it, or type the tempo.

## User Stories

- As a listener browsing by tempo, I want a pop ballad to show ~128 and not 256, so that the BPM
  browse and the daily mixes do not put it among uptempo tracks.
- As a curator, I want a genuinely slow track in a fast genre (industrial at 115) to keep its tempo,
  so that the genre does not overrule what the audio clearly says.
- As a curator, I want to fix a wrong tempo with one tap (½× / 2×) or by typing it, so that I do not
  have to wait for a better rule.
- As the owner of the files, I want a tempo only written into a file's tag when the octave is not a
  guess, and a wrong tag the writeback wrote earlier rewritten, so that other players get the right
  number.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A ballad on a Hitzone compilation, no genre, measured at 64 | Shown at 128; not "betrouwbaar"; not written into the file. |
| A pop song in the Spotify folder measured at 234 | Shown at 117. |
| A hardstyle track measured at half time (75) | Shown at 150, reliable (its own genre settles it). |
| An industrial hardcore track that really is 115 | Stays at 115 once its audio evidence is measured (below). |
| A genre-less uptempo track measured at 215 with a clear fast pulse | Stays at 215. |
| The same without a clear fast pulse, and no label or artist that plays that fast | Shown at 107.5, not reliable. |
| An artist whose only fast tracks are other people's remixes | Their remixes no longer decide the tempo of their own songs. |
| A user with `bpm.override` opens a track's details | ½×, 2×, a tempo field and "Set"; after a change the tile says "handmatig" and a "Gemeten" button undoes it. |
| A user without the permission | Sees the tempo, no controls. |
| A tempo set by hand | Shown everywhere (library, browse, feeds, player details) at once, marked reliable, written into the file's tag on the writeback's next round, and never overwritten by the analyzer. |
| The deploy of this change | Within minutes every existing measurement is re-decided from the database; over the following ~18 hours the analyzer re-listens to the tracks (the doubtful ~89k first) to add the audio evidence. |
| The writeback, once un-paused | Only writes tempos decided by the new rule with enough confidence; files it wrote before are rewritten when their tempo changed. |

## Acceptance Criteria

1. André Hazes's "Vaag en Stil" (Hitzone 33) shows 128, not 256, and is not marked reliable.
2. The Silence's "Nothing" shows 115 once re-measured, and is not doubled by its genre.
3. A pop track in the Spotify folder measured at 234 shows 117.
4. Half-time hardstyle readings still show at 150 and stay reliable.
5. The ground-truth evaluation set does not get worse on hard dance.
6. With the `bpm.override` permission, ½× / 2× / set / "Gemeten" work in the management track panel
   and in the player's track details; without it the controls are absent and the API refuses (403).
7. Every manual change is in the audit log with who, which track, from what and to what.
8. A manual tempo survives every analyzer round and is written into the file's tag.
9. The writeback stays paused until someone un-pauses it; when it runs, it rewrites the doubled tags
   it wrote before.

## Open Questions / Not Yet Decided

- **External lookups.** GetSongBPM (free key, attribution) is a prior for mainstream tracks without a
  label or artist prior: [getsongbpm-prior](../getsongbpm-prior/functional.md), issue #152. Deezer's
  `bpm` is always 0, Beatport has no public API, Spotify's audio features are closed to new apps and
  AcousticBrainz is gone.
- **A folder prior.** Soundcloud and YouTube files sit in a folder per uploader, which is often a
  better tempo predictor than the credited artist; not built, measured first (issue #153).
- **Genre-less uptempo in Soundcloud.** Without a label, artist or clearly fast pulse such a track is
  now halved (not reliable, not written). The re-measure adds the audio evidence; the manual override
  fixes the rest. Whether more is needed is decided after a week of data (issue #153).
