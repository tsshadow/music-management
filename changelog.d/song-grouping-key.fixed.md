- **Versions of one song now meet, and a misparsed upload series no longer hides behind one
  song.** The grouping key strips "(Official Audio)", "(Official Music Video)", "(Pro Mix)",
  "(Pro Edit)" and "Visualizer" markers, a trailing " - Official ..." dash suffix ("Lost On You -
  Official Hardcore Visualizer") and a bare "official video" tail, and reads genre words only inside
  an official upload marker, so "(Official Hardcore Visualizer)" goes and "(Hardcore Mix)" stays
  its own song. Any unknown word still keeps a suffix, so remixes, VIPs, bootlegs and named edits
  stay apart. A collaboration ("CHEEVA & D-sire") groups on its first artist when the title matches
  exactly, and an artist field holding only a kind phrase ("Official Preview") counts as no artist.
  A work with more than 12 different lengths -- production's `q dance:::next` held 88 different
  songs -- is split automatically, each track locked in a work of its own; smaller suspicious works
  are listed by `scripts/repair_song_works.py --report` for review in the Versies page. The repair
  script now counts in its dry run how many tracks move and where, and leaves a work's pinned
  version where it is. Existing tracks move only when `scripts/prod/person/regroup-song-works.sh`
  is run. Bug report 098.
