# Versions of one song stayed apart, and different songs shared one work

# status: fixed

# reported problem

Teun's Release Radar (10-26 September 2026) listed several songs more than once, because their
versions sat in different works. At the same time some works held many unrelated songs, so a
collapsing list showed one of them and hid the rest. Measured read-only on production on
2026-09-26:

- **Missed groupings.** "Lost On You - Official Hardcore Visualizer" and "Honor The Fight - Official
  Hardstyle Visualizer" each had a work apart from the plain title. Work keys still holding a
  marker the key did not know: `official audio` 859, `pro mix` 552, `official music video` 533,
  `official video` 340, `visualizer` 252. Artist mismatches: "CHEEVA & D-sire" vs "Cheeva",
  "Code:Red" vs "RED", "Dj Furax" vs "MANDY" on the same remix, and ~40 tracks whose artist was
  "Official Preview".
- **False merges.** `q dance:::next` held 88 tracks, `q dance:::speqtrum` 63, `gearbox:::lockdown`
  49, `q dance:::qore` 41. They are upload series ("Synapze - Neon Lights | Q-dance presents NEXT")
  that the tagger stored as title "NEXT" by artist "Q-Dance". The 88 tracks of `next` come in 61
  different lengths.

# Possible reason

The key (`services/music_manager/song_versions.py`, `work_key`) is `normalize(artist) ::: title
without its trailing bracket groups`. A bracket group was stripped only when every word was on a
fixed list. Three gaps followed from that:

- The list lacked `pro`, `audio` and `music`, and genre words ("Official Hardcore Visualizer").
- Only brackets were stripped. A dash suffix (" - Official Video"), an unbracketed "official video"
  tail, and decoration after the bracket ("(Official video) 🐆", "† - Official Preview [OUT NOW]")
  were all kept.
- The artist half used the whole primary-artist name, so a collaboration name never met its lead
  artist, and a kind phrase parsed as the artist became part of the key.

Nothing looked at a work as a whole, so a series that shared one misparsed key grew without limit.

# solution

- **Title.** `_strip_grouping_markers` peels markers off the end in a loop: a trailing bracket, a
  " - " / " – " / " | " suffix, or a bare tail starting with "official", after dropping trailing
  decoration. Each is stripped only when every word is known (`_is_version_marker`). Genre words
  count as known only when the marker also says "official" and names the upload (video, visualizer,
  audio, lyric, preview). One unknown word still keeps the suffix, so remix, VIP, bootleg, "Anthem"
  and a remixer's name stay apart. A dash suffix or "official" tail must have words in front of it.
- **Artist.** `grouping_artist` keys on the first artist of a collaboration ("A & B", "A x B", "A
  feat. B", "A vs B", "A, B") and treats a name that is only an "official" kind phrase as no artist.
  The title half still has to match exactly, so two different lead artists never meet. "Code:Red"
  vs "RED" and "Dj Furax" vs "MANDY" are different lead artists and stay apart on purpose. Merging
  them would need a guess the key cannot make.
- **False merges.** `song_work_audit.assess_work` counts a work's different lengths (within 3 s).
  More than 12 is marked `split`. On production no genuine work with 10 or more members had more
  than 9, and every work past 12 was a misparsed series. The song-versions worker splits such a work
  when a pass touches it: every unlocked member goes to a `split:<id>` work, locked, as the split
  endpoint does. More than 6 lengths, a spread above 1.5x with at least 4 lengths, or more than 12
  versions from more than 3 years only marks the work `suspicious`. Those are listed by
  `scripts/repair_song_works.py --report` for review in the Versies page and are never split
  automatically.
- **Existing rows.** `scripts/repair_song_works.py` can be re-run. Its dry run counts the tracks
  that move, which join an existing work and which found a new one, and which pinned tracks stay.
  It never reads a locked track and leaves a work's pinned version in place. With
  `--split-false-merges` it splits the `split` works first. `scripts/prod/person/regroup-song-works.sh`
  runs the dry run, backs up `library_works` and the work columns of `library_tracks`, then
  applies and verifies. It has not been run on production.

Design: [docs/designs/song-grouping-key/](../designs/song-grouping-key/functional.md). The production run is issue #66.
Tests: `services/music_manager/tests/test_song_grouping_key.py`, `test_song_work_audit.py`,
`test_song_work_split.py`, `services/tests/RepairSongWorksTest.py`.

Not fixed here: the tagger misparse behind the series ("... | Q-dance presents NEXT" stored as
title "NEXT"). Until the tagger reads such titles correctly, new uploads of a series collect in one
work again. The worker splits that work again once it passes 12 different lengths.
