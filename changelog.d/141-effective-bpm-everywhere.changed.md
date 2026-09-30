- **One track, one tempo.** Since 0.84.0 the BPM browse showed the *effective* BPM (the
  bpm-analyzer's measurement, else the file tag or the old analyzer value folded into the genre's
  band), but the library table (its BPM column, sort, BPM filter and a number typed in the search
  box), `/api/library/tracks`, the BPM chart and coverage under Beheer → Bibliotheek, the feeds and
  the player's track details still read `COALESCE(af.tempo, af.bpm_tag)` -- the old analyzer first,
  never the measurement, never folded -- so the browse could say 150 where the table and the details
  said 161. They all read the same value now, and every place that prints it marks a value that is
  not measured with "≈" (issue #141). The bpm-analyzer keeps a new table,
  `library_track_effective_bpm` (migrate_v51), in sync for the SQL readers: in full every 30 minutes,
  and right after each round for the tracks it just measured; the details sheet resolves its one
  track live. The APIs gain fields (`bpm_approximate`, and on `/tracks/by-path` also `bpm_source`,
  `bpm_confidence`, `bpm_folded`); nothing is removed or retyped. Until the worker's first sync after
  the deploy, the table and the chart show no BPM.
- **Sorting the library table by BPM took 7.5 seconds.** The query computed the label, genres and file
  path of all 328k tracks before sorting them. It now picks the page first and looks those up for its
  hundred tracks only: 1.5 s on production, measured with a stand-in for the new table that is
  slower than the real one (a non-unique join where the table has a primary key). Tracks without a
  BPM sort last in either direction, and ties are broken by id so paging no longer repeats or skips
  tracks that share a tempo.
<!-- release notes -->
- A track now shows the same tempo everywhere -- library table, search, BPM filter, chart, track
  details and the BPM browse -- with "≈" when it is not measured. Sorting the library by BPM went
  from 7.5 seconds to under two, with tracks without a BPM at the bottom.
