# BPM Octave Errors: A Ballad At 256, An Industrial Track At 230

# status: fixed

# reported problem
Teun, 2026-09-30: "André Hazes shows 256 BPM, which can never be right. 'The Silence' shows 230 but
should be 115. How do you handle such doublings? There are surely more."

Measured on production the same day (read-only):

- André Hazes -- "Vaag en Stil" (`Hitzone/Hitzone 33`): `bpm` 256.00, `raw_bpm` 64.00, confidence
  0.500, `octave_corrected` 1. "Donker Om Je Heen" (`Hitzone 44`): 263.62 from a raw 131.81. Neither
  track has a genre of its own.
- The Silence -- "Nothing" (Genosha Records, genres Hardcore + Industrial Hardcore, four copies):
  230.00 from a raw 115.00 at confidence 0.97, `octave_corrected` 1. Re-measured on the workstation:
  the comb score of 230 is 0.47 of the score of 115.
- The whole table: 269,440 measurements, 43,916 octave-corrected; 47,342 above 200 BPM, 27,255 of
  them on tracks without a hard genre (core, uptempo, terror, zaag) of their own.
- The 0.86.0 tag writeback had already written 1,125 values above 200 into files, 835 of them on
  tracks without a hard genre. Teun paused it (`bpm_tag_writeback_paused=true`) and backed the old
  tag values up.

# Possible reason
The worker folded every estimate into a hand-set genre band (`bands.fold_into_band`, ×1, ×2, ×½,
×4, ×¼, first that fits) and stored the folded value with the estimator's own confidence.

**Hazes.** A track without genres borrowed its primary artist's commonest genre
(`worker.ARTIST_GENRES_SQL`). In this library André Hazes's genres come from hardstyle and uptempo
remixes and bootlegs of his songs -- "'t Rode Licht (Rectonize Remix)" (Hardstyle, 160),
"Leef (Unproven Uptempo Bootleg)" (Uptempo Hardcore, 200) -- none of which carries a remixer credit
(`library_track_artists` holds no `remixer` rows at all) or a `version_kind`. So the ballad got the
uptempo band (180-260) and its raw 64 was multiplied by four. The fallback was poisoned by remixes,
and it folded *up* into a hard band on nothing but that.

**The Silence.** The industrial hardcore band is 140-230. A genuinely slow industrial track at 115
has no octave inside it, so the fold took the nearest one, 230, and kept the pulse confidence 0.97
-- a folded value that looked as reliable as a measurement. The comb scores that would have said
"230 is not a real periodicity here" (0.47 of the estimate) were computed and thrown away.

**The rest.** Every genre-less track above 200 stayed there (the default band ran to 250), so pop
read at double time (Spotify, Top 100) stayed doubled, and the confidence never reflected that the
octave was a guess. The writeback, gated on that confidence, wrote them.

# solution
Docs: [docs/designs/bpm-octave/](../designs/bpm-octave/). The band is no longer the decision.

- **The octave is weighed, not forced** (`services/music_manager/bpm/octave.py`). The candidates
  are T/2, T and 2T; each gets a score from independent evidence: the estimator's own pick and, when
  known, the comb score of the neighbour (a neighbour far below the estimate is not a real
  periodicity -- this keeps The Silence at 115); learned priors of the track's label, its primary
  artist's own tracks and its genres; a mainstream path (Hitzone, Spotify, Lidarr, Top 100: pop
  around 105); a neutral prior around 135. A doubled value above 205 is only a candidate when the
  track's own genre or its label favours it -- an artist's prior alone never folds a track up into
  hard dance. Without such evidence a tempo above 205 or below 70 costs a plausibility penalty that
  only a clearly fast pulse can pay.
- **Learned priors** (`priors.py`, table `library_bpm_priors`, recomputed daily): the mean and
  spread of log2(BPM) per label, per primary artist and per genre, over confident raw estimates in
  88-200 (plus above 200 for a hard genre, and for an artist's genre-less tracks outside the
  mainstream folders). An artist's remixes, bootlegs and style edits are left out by title, which is
  what fixes Hazes. Coverage on a 10% sample of production: 81.9% of measured tracks have an artist
  or label prior (77.4% artist, 37.9% label).
- **The confidence includes the octave.** Stored `confidence` = pulse confidence × octave certainty
  (from the margin to the runner-up), ×0.9 when folded; a fold decided by the general priors alone
  (neutral, path) is capped at 0.6. The estimator's own confidence moves to `raw_confidence`. So a
  guessed octave is no longer "reliable" and no longer written into a tag.
- **Re-evaluated without re-measuring.** The raw estimate was always stored, so the bpm-analyzer
  refolds every row from the database at start and after the daily priors recompute
  (`refold.py`); `fold_version` records which rule chose. The comb scores are now stored too
  (`strength`, `half_score`, `double_score`); rows from before are re-measured in the background,
  the doubtful ones (above 200, below 70, folded, ambiguous) first -- about 89k tracks, ~6 hours at
  the analyzer's measured 12-17k tracks an hour, the other ~180k in another ~12.
- **Manual override.** The track details (management inspector and the player's details sheet)
  get ½×, 2× and a set field for users with the new `bpm.override` permission;
  `library_track_bpm_manual`, the effective BPM's first source, never overwritten by the analyzer,
  audited as `bpm.manual_set` / `bpm.manual_cleared`.
- **Writeback safety.** A measurement is only written once its octave was chosen by the current
  rule and it is confident; a manual tempo is always written; a file the writeback once wrote is
  queued again whenever its value changes, so the ~835 doubled tags are rewritten by themselves.

Dry run on a 10% sample of production (26,789 measured tracks, read-only): 1,053 (3.9%) get another
tempo; above 200 falls from 4,678 to 3,968, and among tracks without a hard genre from 2,782 to
2,177; the ground-truth set (399 tracks with genuine tags) goes from 84.5% to 84.7% within 1 BPM,
which is the octave ceiling of that set (84.7%); hard-dance tracks unchanged at 82.4%.
