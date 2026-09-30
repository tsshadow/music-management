- **The measured tempo now goes into the files' own BPM tag** (issue #139). Until now the precise
  measurement lived only in MuMa's database, while the files kept the old analyzer's coarse steps
  (152, 161, 172 ...), a quarter of them an octave off, or no tempo at all -- which is what DJ
  software and other players read. Each tagger round now ends with a capped step (default 300
  files, after every retag reason) that writes confident measurements (at least 75%) as a whole
  number into ID3 `TBPM`, the MP4 `tmpo` atom or the Vorbis `BPM` comment, and changes nothing else
  in the file. A tag that already matches, a genuine whole-number tag within 1 BPM, sets, podcasts
  and files outside the tagger's own folders are left alone; an octave is always corrected. The
  analyzer, the scanner and the tagger's walk are told the new file date, so nothing is measured or
  retagged again. About 142k files qualify today; at the default that takes two to three days.
  Beheer → Config → BPM switches it off, pauses it and sets the rate and the threshold
  (docs/designs/bpm-tag-writeback/).

<!-- release notes -->

- **Measured tempos are now written into the files' BPM tag**, so DJ software and other players
  show the same tempo as MuMa. It runs slowly in the background (two to three days for the whole
  library) and can be paused under Beheer → Config → BPM.
