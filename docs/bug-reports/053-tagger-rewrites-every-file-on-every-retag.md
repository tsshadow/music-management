# Tagger Rewrites Every File On Every Retag

# status: fixed

# reported problem
A retag of a file the tagger had already processed was supposed to write nothing (technical design,
acceptance criterion 7). It did write, for three independent reasons, and each write also changed
what the scanner indexed:

- **Artist order changed on every pass.** `ANGERFIST;outsiders;Dj Mad Dog` became
  `outsiders;Dj Mad Dog;Angerfist` after one pass of `CheckArtistRule`, and changed again on the
  next. The scanner takes the first artist as the primary one (`routers/scanner.py`,
  `artist_ids[0]`), and `track_uid` is a hash of title, duration and primary artist, so a reorder
  gave the track a new identity and left its ratings and listens on the old one.
- **Every tag value was split on '/'.** `Tag('title', ['AC/DC Tribute (Live 24/7)'])` became
  `['AC', 'DC Tribute (Live 24', '7)']` and was written back as `AC;DC Tribute (Live 24;7)`. The
  scanner reads through the same class (`ReadonlySong`), so AC/DC was indexed as two artists, `AC`
  and `DC`.
- **Four m4a tags went to the wrong atom.** `REMIXER` and `ORIGINAL_TITLE` were mapped to bare atom
  names, which mutagen truncates to 4 bytes (`REMI`, `ORIG`) and which were never read back. So every
  m4a with a remixer was rewritten on every retag, and `InferArtistFromTitleRule`, not seeing an
  `ORIGINAL_TITLE`, re-seeded it from the already-cleaned title and inferred again from the
  remainder: `A - B - C` gave artist A and title `B - C`, the next retag artist B and title `C`.
  `ALBUM_ARTIST` was mapped to `TALB` (the ID3 album frame name, not an MP4 atom) and `ALBUM` had no
  MP4 mapping at all, so LMS never saw album or album artist on an m4a the tagger wrote. YouTube
  downloads are m4a, so this is most of the library.

# Possible reason
- `CheckArtistRule.apply` looped over `song.library_artists()`, which returns the tag's live value
  list, and called `tag_item.add(canonical)` then `tag_item.remove(name)` on that same list: the
  correction was appended to the end and the loop skipped the element after every removal.
  `AddMissingArtistToDatabaseRule` did the same, and its removals used `get_item('ARTIST')` -- a
  tag nobody reads, the constant is `'artist'` -- so an ignored artist was never actually removed.
- `Tag.resplit` split every value on ';' and on '/'. Only genres use '/' as a separator, which is
  exactly what `GenreRulesHelper.split_composite` already documented ("artists really do contain
  slashes (AC/DC) and must keep them").
- `MP4Tags` in `services/tagger/constants.py` mapped `REMIXER: 'REMIXER'`,
  `ORIGINAL_TITLE: 'ORIGINAL_TITLE'` and `ALBUM_ARTIST: 'TALB'`, and had no `ALBUM` entry. The
  comment beside it already explained the 4-byte limit, but only as the reason to leave
  `ORIGINAL_ARTIST` unmapped.

None of it showed in the tests: `services/tests/mock_base.py` replaces mutagen for the whole session,
so no test under `services/` ever saw what landed on disk, and the rule tests used a `MagicMock` tag
that recorded `add`/`remove` calls without an order.

# solution
- `Tag.replace(old, new)` swaps a value at its own position (or drops `old` when `new` is already
  present). Both artist rules iterate over a snapshot and use it, and `AddMissingArtistToDatabaseRule`
  uses the `ARTIST` constant.
- `Tag.resplit` splits on '/' only for `GENRE`; ';' splitting is unchanged.
- m4a mapping: `REMIXER` and `ORIGINAL_TITLE` go to the freeform atoms
  `----:com.apple.iTunes:REMIXER` / `----:com.apple.iTunes:ORIGINAL_TITLE`, `ALBUM` to `©alb`,
  `ALBUM_ARTIST` to `aART`. `TagCollection._parse_m4a` decodes freeform bytes for mapped atoms and
  `BaseSong._set_m4a_tag` encodes them, so a written value reads back identical.
- Self-healing: `LEGACY_MP4_ATOMS` lists `REMI`, `ORIG`, `TALB` and the freeform `ALBUM`. When the
  correct atom is absent the legacy value is read and marked unsaved, and `BaseSong.save_file` deletes
  the legacy atoms, so a file is migrated on its next retag and left alone after that.
- `BaseSong.delete_tag` now removes an emptied tag from its m4a atom; it used to pop the tag name,
  which never matched an atom, so an emptied remixer came back on the next read.
- The ID3 side is unchanged: MP3 keeps `TXXX:remixer` / `TXXX:original_title` (EasyID3
  registration), WAV keeps `TXXX:REMIXER` / `TXXX:ORIGINAL_TITLE`.

`tests/unit/test_tagger_idempotence.py` runs against real mutagen, in a child interpreter, on an MP3
and an M4A fixture: write a full tag set, retag twice, and assert the second retag writes nothing,
artist order is kept, slashes survive, every m4a key reads back equal, and legacy atoms are migrated
once. All three tests fail against the unfixed code. `tests/unit/` now runs in `backend:unit`
(`scripts/test/music-management-unit.sh`); it did not run anywhere before, including the existing
`test_artwork_embedding.py`.

**Still open, and it is data rather than code:**
- Files already written stay wrong until something retags them. A deep retag run heals the m4a
  atoms and restores canonical artist order. It cannot restore slashes: a title already written as
  `AC;DC Tribute (Live 24;7)` is indistinguishable from a real three-part value.
- Every reorder or title split changed that track's `track_uid`, so ratings and listens may be
  attached to track rows that no longer match a file. See the open GitLab issues.
