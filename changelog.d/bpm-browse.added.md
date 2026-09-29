- **Browse by BPM.** A new BPM page under Bladeren (phone) and in the sidebar (web), songs mode only:
  tap a tempo chip (128 ... 230) or a bar of the tracks-per-BPM chart, or type a from-to range, pick
  a margin (±0.5 to ±5, default ±2 from the new `bpm_browse_tolerance` setting), narrow to one genre,
  and switch on "Betrouwbaar" to keep only trusted tempos. The list plays as a queue that continues
  with the next page, and every row shows its BPM. The tempos come from one rule
  (`services/music_manager/bpm/effective.py`): a precise measurement from the new
  `library_track_bpm` table when there is one (nothing fills it yet; a background analysis follows
  in a separate change), else the file's BPM tag, else the old ml-analyzer tempo -- the last two
  folded by a factor of two into the tempo band of the track's genres, because the old analyzer
  often read a hardstyle track at half speed. Those old values sit on librosa's coarse lag grid
  (152.0, 156.6, 161.5 ...: a 150 and a 155 BPM track both read 152), so they show as "≈152" with
  one quiet line explaining it, and the ±2 default is what lets "150" find them. About 88,000 of
  the 267,000 tracks have a tempo today. API: `GET /api/library/bpm/tracks` and
  `GET /api/library/bpm/histogram` (docs/designs/bpm-browse/). New table `library_track_bpm`
  (migrate_v50), new settings `bpm_browse_tolerance` and `bpm_reliable_confidence` (Beheer →
  Config → BPM).

<!-- release notes -->

- **Browse by BPM.** A new BPM page under Bladeren: pick a tempo or a range, narrow it to a genre,
  and play everything at that tempo. Most tempos are still rough ("≈152"); precise measurements
  follow in a later update.
