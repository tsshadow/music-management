- **Precise BPM, measured in the background.** A new `bpm-analyzer` container (tools image) measures
  every track's tempo to 0.01 BPM from a 60-second excerpt, newest tracks first, and stores it in
  `library_track_bpm`, which the BPM browse already prefers over the old coarse values -- a measured
  track shows "150 BPM" instead of "≈152". The estimator is new (numpy only: spectral flux,
  autocorrelation summed over twelve beat multiples, so no lag grid), chosen by measurement on 399
  production files whose tags the old analyzer cannot have written: 84.5% within ±1 BPM and 83.0%
  within ±0.5 after folding into the genre's band, against 30-33% for Essentia's RhythmExtractor2013
  and 2.3% for the old librosa values (`tools/bpm_eval.py`, docs/designs/bpm-browse/technical.md).
  A 150 and a 155 BPM track no longer read the same. Sets, podcasts and files over 15 minutes are
  skipped; files are only read (an ffmpeg seek, so only the excerpt crosses the network), never
  retagged. Capped at 2 cores (`MUMA_CPUS_BPM`) and 768 MB (`MUMA_MEM_LIMIT_BPM`), nice 19 and idle
  I/O. Beheer → Config → BPM: on/off, pause, workers, excerpt length, skipped forms, maximum length,
  re-read every round. Progress: an INFO summary every ten minutes under the new event source
  `bpm-analyzer`, and `bpm_analysis` in `GET /health` (state, counts, rate, ETA; informational, it
  never turns /health red). Expect the first full pass to take roughly one to two days.

<!-- release notes -->

- **Precise BPM.** MuMa now measures each track's tempo itself, newest first, so browsing by BPM gets
  exact values ("150" instead of "≈152") as the measuring works through the library. The first pass
  takes a day or two; new tracks are measured within minutes.
