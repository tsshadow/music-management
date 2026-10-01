- **A ballad no longer shows 256 BPM, and a slow industrial track no longer 230** (bug report 140).
  The analyzer forced every measurement into a hand-set tempo range per genre, and a track without a
  genre borrowed its artist's commonest one: André Hazes's genres here come from hardstyle and
  uptempo remixes of his songs, so "Vaag en Stil" (measured 64) was multiplied by four; The
  Silence's "Nothing" (a clear 115) had no octave inside industrial hardcore's 140-230 and went to
  230 -- both marked as reliable as a real measurement, and 835 such doublings were written into
  file tags. The octave (half, as measured, double) is now weighed on what the collection knows:
  learned tempo priors per label, per artist (their own tracks only -- remixes, bootlegs and style
  edits are left out by title) and per genre, recomputed daily; a pop-compilation folder (Hitzone,
  Spotify, Lidarr, Top 100); and the estimator's comb scores, now stored, which say when a
  neighbouring octave is no real periodicity. An artist's prior alone can never double a track into
  hard dance, and a genre-less tempo above 205 is halved unless the pulse clearly says otherwise.
  The stored confidence now includes how sure the octave is, so a guessed octave is not
  "betrouwbaar" and is not written into a tag. Every existing measurement is re-decided from the
  database when the bpm-analyzer starts; the ~89k doubtful ones are re-measured for their comb
  scores first (~6 hours), the rest after (~12). On a 10% sample of production 3.9% of tracks get
  another tempo and tracks above 200 drop by 15%; the evaluation set stays at its octave ceiling
  (84.7% within 1 BPM, hard dance unchanged). The tag writeback only writes tempos the new rule chose
  with enough confidence, and rewrites the files it wrote before whenever their tempo changed.

<!-- release notes -->

- **Wrong double or half BPMs fixed**: a ballad no longer shows 256, a slow industrial track no longer
  230. The tempo is now chosen using what the label, the artist's own tracks and the genre usually
  play, and a guessed tempo is no longer marked reliable or written into the file.
