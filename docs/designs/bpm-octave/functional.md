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
| The same without a clear fast pulse, and no genre, label, artist or folder that says it is slower | Stays at 215, marked unsettled: not reliable, not written into the file (issue #153). |
| A fast reading whose genre, label, artist or mainstream folder sits at the half | Shown at the half. |
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
- **An uploader-folder prior.** Soundcloud and YouTube files sit in a folder per uploader. Measured
  on 2026-11-12 (below), it is about as good as the artist prior and covers more tracks, but it is
  weaker on exactly the fast tracks in question. Not built.

## Change: A Halving Needs Real Evidence (issue #153)

Measured read-only on production on 2026-11-12, a week after the octave rule shipped:

- 4,209 tracks with a library entry had a raw estimate above 205 BPM that the neutral prior or the
  mainstream path prior alone had halved: Soundcloud 1,856, YouTube 1,626, EPs 527, mainstream
  folders 145, other 55. 3,751 of them have no genre. Nobody corrected one by hand.
- For 3,049 of the 4,209 neither the label nor the artist had a prior. Where one did, it sided with
  the half 848 times and with the measured tempo 277 times: those 277 had been halved against the
  only evidence about them.
- The comb score of the half was at least 0.6 of the estimate's for 4,169 of them: the audio does
  not settle these, in either direction.
- The mainstream path prior agrees with the other evidence. On the 411 fast tracks in the
  mainstream folders, the artist prior sided with the half in 223 of 233 halvings, the track's genre
  in 176 of 177.

What changed:

- A track measured above 205 BPM is only halved when its own genre, its label, its artist, its
  GetSongBPM tempo or its mainstream folder sits closer to the half. The neutral guess around
  135 BPM no longer decides it.
- Otherwise the measured tempo stays, marked **unsettled**: shown, not reliable, never written into
  the file. A fast tempo that wins without any evidence on its side is unsettled too.
- The tag writeback never writes an unsettled tempo, or a fold that only the general priors
  decided, also not with a lower confidence threshold and also not into a file it wrote before.

Effect on production's rows (dry run of the new rule on a dump, 2026-11-12): 3,127 of the 4,209 go
back to their measured tempo, 3,124 of them unsettled. 1,082 stay halved because real evidence sides with the
half, still not reliable. No other track changes tempo, and no track becomes reliable that was not.

The uploader folder, measured like the artist prior (confident estimates, each track left out of its
own prior): it puts 96.9% of Soundcloud/YouTube tracks on their own octave, covering 99% of them,
against 97.1% for the artist prior, covering 67%. On tracks above 205 BPM it drops to 76.8% against
81.3%. It would decide 1,157 of the unsettled tracks towards the half, so it waits for a decision.
