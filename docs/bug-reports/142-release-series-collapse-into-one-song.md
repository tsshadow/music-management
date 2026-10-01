# Release And Series Markers In Download Titles Collapse Whole Series Into One Song

# status: fixed

# reported problem
Verified on production on 2026-10-01. Song versions (`services/music_manager/song_versions.py`)
groups on `artist ::: title`, and for SoundCloud and YouTube downloads both halves come out of the
upload title. Whole series ended up as one "work", so a collapsing list showed one upload and hid
the rest:

- `Luner - Holding On To You ｜ Q-dance presents SPEQTRUM` -> artist Q-dance, title SPEQTRUM (63
  tracks); the same for `｜ Q-dance presents NEXT` and `QORE`.
- `Deviouz & Matzic - Tomorrow (Gearbox Presents Lockdown 3.0)` -> artist Gearbox, title
  `Lockdown 3.0)` (29); `(Gearbox Presents Twin Turbo)` (18).
- `YunKe & MBK - You Dont Scare Me [DRS Presents： TSR Album 8.0 - TSR042]` -> artist DRS, title
  `TSR Album 8.0 - TSR042]`; without the colon the artist became `TSR Album 8.0`.
- `Krowdexx - Fastlane (Dungeon： The Mini Album)` -> artist Dungeon, title `The Mini Album)`.
- `KAASCOUSE ｜ The Next MC - Optreden ｜ 101Barz` -> artist 101barz, title Optreden;
  `Jimmy Huru - #BPMJIMMYHURU ｜ BPM ｜ 101BARZ` -> artist 101barz, title BPM.
- `QAPITAL 2019 ｜ Interview with Rejecta` -> artist Interview.
- `Qlimax 2010 ｜ Blu-ray ⧸ DVD Preview ｜ Zatox` -> artist Qlimax 2010.
- `Bowser's Castle (Mario Kart World) ｜ Cover by Gabocarina96` -> title Cover.
- `LNY TNZ & Ruthless - Fired Up Ft. The Kemist (Kayzo Remix)` -> title `Fired Up`, so every remix
  shared the key `lny tnz:::fired up` with the original (18 tracks).

# Possible reason
- `InferArtistFromPresentsOrColonRule`, the first sub-rule of `InferArtistFromTitleRule`, searched
  for `X presents`, `X presents:` or `X:` *anywhere* in the title with an unanchored `re.search`.
  The label inside a trailing bracket matched, was close enough to a known artist (it had become one
  on an earlier pass), and everything after it became the title.
- The pipe-based sub-rules turn both pipes into ` - ` and pick a segment by artist-name match. The
  channel's own name as the last segment ("101Barz") had become a known artist the same way, so it
  won. Interview, cover and preview uploads have no "Artist - Title" at all, so the first-segment
  fallback guessed.
- `InferFeatureFromTitleRule`'s unbracketed pattern (`ft. (.*)$`) took everything to the end of the
  title as the featured artist, remix bracket included, and removed it from TITLE. The remixer
  still reached REMIXER, but the grouping key reads only TITLE, and `library_tracks` has no remixer
  column.
- The song-version worker only groups tracks without a work; nothing re-keyed a grouped track.

# solution
Design: [docs/designs/release-series-markers/](../designs/release-series-markers/functional.md).

- `services/tagger/Song/title_markers.py` reads the markers before any sub-rule runs: a trailing
  `(<Label> Presents <Release>)`, `[<Label> Presents[：:] <Release>[ - <CAT>]]`, a `(<Name>： <...>
  Album/EP/LP>)` bracket and a last pipe segment `｜ <Label> presents <Release>` are stripped; trailing
  pipe segments that equal the channel (folder or uploader, case and punctuation ignored, fuzzy at
  0.85) are dropped, and with them a series segment after an `Artist - Title` first segment;
  interview, cover and event-preview uploads get their artist from their shape.
- The release name becomes ALBUM when ALBUM is empty or still the channel default
  (`Soundcloud (...)`/`Youtube (...)`), never over any other album; a catalogue number in the marker
  becomes CATALOG_NUMBER if there is none.
- The presents/colon sub-rule only matches at the start of the title, and not on an
  `Artist - Title:` candidate. `Bloodlust presents: The Assassination | ...` still works.
- The feature pattern stops at the first bracket, so `(Kayzo Remix)` stays in TITLE and the remix
  gets its own work through the existing key (an unknown word in a bracket keeps it in the key).
- `song_work_audit`: a work with more than 10 members is flagged `suspicious`. The automatic split
  threshold is unchanged.
- Recovery is automatic: `migrate_v54_retag_release_markers.sql` queues the affected files once
  (reason `release_marker`); the retag changes title/artist, the scanner gives the file a new track
  row, and the worker groups that row under the new key. Nobody has to run anything.

# Open
- Interviews and previews are not music. They now get a sensible artist and title, but they should
  get their own non-music marker (a form or a flag) later, so lists and mixes can leave them out. No
  issue filed from this branch.
- Two spellings of one release (`TSR Album 8.0`, `TSR ALBUM 8.0`) become two albums; the tagger
  keeps the upload's spelling.
