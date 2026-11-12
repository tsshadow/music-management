- **A fast track was halved when nothing about the track said it was slow.** The octave rule folded
  a raw estimate above 205 BPM down to its half on the neutral prior alone, a broad guess around
  135 BPM that knows nothing about the track. On production that halved 4,209 tracks, 3,482 of
  them Soundcloud and YouTube uploads, where genre-less uptempo is common. A halving above 205 now
  needs real evidence: the track's own genre, its label, its artist, its GetSongBPM tempo or a
  mainstream folder must sit closer to the half. Without it the measured tempo stays, marked
  `unsettled` and not reliable (3,124 of the 4,209). `FOLD_VERSION` is 3, so the bpm-analyzer
  re-decides every measurement from the database within minutes of the deploy. The tag writeback
  never writes an unsettled tempo or a fold that only the general priors decided, whatever the
  confidence threshold, and also not into a file it wrote before (issue #153).
<!-- release notes -->
- **Fast tracks without genre are no longer halved on a guess.** A Soundcloud or YouTube track
  measured above 205 BPM keeps its tempo unless its genre, label, artist or folder says it is
  slower. Such a tempo is shown, but not marked reliable and not written into the file.
