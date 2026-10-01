# Release And Series Markers In Download Titles — Technical Design

Implements [functional.md](functional.md). Bug report 142.

## Data Model

No schema change. Tags written by the tagger: TITLE, ARTIST, ALBUM, CATALOG_NUMBER.
`migrate_v54_retag_release_markers.sql` only updates rows of `tagger_processed_files`
(`needs_rescan = TRUE`, `rescan_reason = 'release_marker'`) -- expand-only.

### Tagger

- `services/tagger/Song/title_markers.py`, `parse_title_markers(original_title, channel_names)`, a
  pure function returning `TitleMarkers(title, album, catalog, artist, final_title)`:
  1. Shapes that name their own artist, checked first: `<Event> ｜ Interview with <X>` (title
     `<Event> Interview`), `<Song> ｜ Cover by <X>` (title `<Song> (Cover)` -- the cover is a work
     of its own, the song name stays readable), and three or more pipe segments where the first
     ends in a year, every middle one has preview/trailer/teaser/aftermovie and the last has not
     (artist = last segment).
  2. One trailing release marker: `(<Label> Presents[：:] <Release>)` / the `[...]` form, a last
     pipe segment `<Label> presents <Release>`, or a `(<Head>[：:] <... album|ep|lp|compilation|sampler ...>)`
     bracket (album `<Head>: <Tail>`). A trailing ` - <CAT>` (capitals then digits) in the release
     is the catalogue number. Nothing is stripped when it would leave an empty title.
  3. Trailing pipe segments equal to a channel stand-in (`song.channel_stand_ins()`; compared
     lower-case without punctuation, or SequenceMatcher >= 0.85) are dropped. When one was dropped
     and the first segment holds ` - `, only that first segment is kept: the rest is the channel's
     series ("BPM"). The series is not written as album -- unlike a "presents" marker it is often a
     format name rather than a release.
- `InferArtistFromTitleRule.apply` calls the parser on ORIGINAL_TITLE, applies album/catalogue,
  writes artist + title directly for step 1, otherwise writes the stripped title to TITLE (when it
  differs) and hands it to every sub-rule as `title_override`. Sub-rules read
  `source_title(song, title_override)` instead of ORIGINAL_TITLE.
- **Album decision** (Teun): the release is the album. SoundcloudSong/YoutubeSong write the channel
  default `Soundcloud (<uploader>)` / `Youtube (<channel>)` into an empty ALBUM *before* the rules
  run, so `apply_release_album` replaces ALBUM only when it is empty or fully matches
  `(Soundcloud|Youtube) \(.*\)`. That covers a first tag and a re-tag of a file tagged earlier; a
  hand-set or other album stays. The channel stays derivable from ALBUM_ARTIST and PUBLISHER, which
  are unchanged.
- `InferArtistFromPresentsOrColonRule` uses `re.match` (start of the title) and refuses a candidate
  containing ` - `.
- `InferFeatureFromTitleRule`: the unbracketed feature pattern stops before the first `(` or `[`.

### Grouping

- The remixer reaches the key through TITLE: with `(Kayzo Remix)` kept in the title,
  `version_free_title` keeps the bracket (an unknown word), so the key differs from the original's.
  No remixer column or join is added -- the key stays a function of artist and title only.
- `song_work_audit.MANY_MEMBERS = 10`: more members adds the reason `"<n> members"` and makes the
  work at least `suspicious`. `AUTO_SPLIT_LENGTHS` (12) is unchanged, so only distinct lengths split.

### Recovery

1. Deploy applies `migrate_v54` once (`tools/apply_migrations.py` skips it while its hash is
   unchanged). It marks only files whose path matches the markers (`presents` in a bracket or after
   `｜`, a fullwidth colon in a bracket, `｜ Interview with`, `｜ Cover by`, `｜ ... preview ... ｜`,
   the `101Barz` folder, and `ft.`/`feat.` before a `(... remix|edit|bootleg)` bracket). A file
   already queued keeps its reason (`needs_rescan = FALSE` guard). A forced re-run re-queues the
   same bounded set, never a whole tree (see migrate_v7).
2. The tagger works the queue; the file's mtime changes.
3. The scanner reads the file; a changed title or primary artist is a new `track_uid` and so a new
   `library_tracks` row without `work_id`; the old row is relinked into it (`track_relink.py`).
4. The song-version worker groups the new row under the new key (respecting `work_locked`, which
   only applies to the old, now-deleted row). Nothing has to be run by hand.

## API Contract

No endpoint changes.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| none | | | |

## Cross-App Impact

None. LMS picks the new tags up through its normal scan.

## Technical Acceptance Criteria

1. `services/tagger/Song/TitleMarkersTest.py` covers every title in bug report 142, the hand-set
   album, the existing catalogue number, a re-tag over a misparsed title, and the remix bracket.
2. `InferArtistFromTitleRuleTest` stays green, including `Bloodlust presents: ...`.
3. `test_song_work_audit.py` covers the 10/11 member boundary.

## Related Docs

- [Bug report 142](../../bug-reports/142-release-series-collapse-into-one-song.md)
- [Song versions](../song-versions/functional.md), bug report 098 (the auto-split)
