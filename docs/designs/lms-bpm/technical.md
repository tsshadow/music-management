# LMS BPM — Technical Design

Implements [functional.md](functional.md). Issue #150.

## Data Model

- `track.bpm INTEGER NULL` in LMS's `lms.db` (`db::Track::_bpm`, `std::optional<int>`). NULL means
  "no plausible tempo in the file".
- Migration step `migrateFromV125` (database version 125 → 126): adds the column when it is missing
  (re-runnable, like steps 121–124) and bumps `scan_settings.audio_scan_version`.
- **The version bump makes older images refuse the database.** An LMS image from before this change
  sees version 126 > its own 125 and stops with "Outdated database". That is the normal price of a
  real schema change; a rollback past it needs the pre-upgrade `lms.db` back, or a rebuild.

### Filling it: the scanner

`TrackMetadataParser::processTags` reads `audio::TagType::BPM` (TagLib maps ID3 `TBPM`, the MP4
`tmpo` atom and a Vorbis `BPM` comment all onto the `BPM` property; the ffmpeg reader maps `BPM`)
and parses it with `scanner::utils::parseBpm`:

- leading/trailing spaces and tabs are trimmed;
- an integer part of 1–4 digits, optionally followed by one `.` or `,` and digits, nothing else —
  so `150`, `150.0`, `150,5`, `150.` parse; `-150`, `150 BPM`, `150.0.0`, `.5`, `abc` do not;
- the value is rounded half up on the first decimal (the writeback's rounding);
- a result outside `[40, 500]` is NULL: a `0` or a mis-parsed `1500` is noise, not a tempo. The
  same bounds the web UI's `parseBpm` and the writeback's plausibility check use.

Parsing is by hand, not `std::stof`, because that follows the locale and a decimal comma is common
in these tags. `AudioFileScanOperation` stores the result with `Track::setBpm` on every (re)scan, so
a tag that disappears or turns to garbage clears the column again.

### Existing tracks: the re-read decision

LMS re-reads a file only when its mtime/size changed, or when the track's `scan_version` differs
from `audio_scan_version`. Two groups need the column filled:

1. Files the 0.86.0 writeback rewrites (~140k over two to three days). Their mtime changes and the
   writeback announces their folders, so LMS rescans them regardless.
2. Files whose tag was already right and which the writeback therefore left untouched (`matches`,
   `kept`: the genuine off-grid tags, plus every file outside the writeback's scope — sets,
   podcasts, files outside the tagger's folders, and files measured with low confidence). Their
   mtime does not change, so without help they would never get a value.

Options considered for group 2:

- **Bump `audio_scan_version` in the migration (chosen).** The next scan re-reads every file once.
  It costs one full library walk, which is what step 119 (FESTIVAL) already did and what upstream
  does whenever it starts reading a new tag. It is complete by construction — it needs no list of
  "which files already had a good tag", which LMS cannot know without opening them anyway.
- A targeted re-read of files whose tag might hold a BPM: there is no such list in LMS, and
  building one from MuMa's `bpm_writeback` ledger would miss every file outside the writeback's
  scope. Rejected: more code for an incomplete result.
- No bump, rely on the writeback's announcements: leaves group 2 at NULL indefinitely. Rejected.

Overlap with the writeback is harmless: a file rewritten after the full walk has read it is
rescanned by its announcement like any other changed file.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| Every Subsonic endpoint that returns songs (`getSong`, `getAlbum`, `getMusicDirectory`, `search2/3`, `getRandomSongs`, `getSongsByGenre`, `getPlaylist`, `getStarred*`, `getPlayQueue`, `spotify/*` ...) | unchanged | the song object gains `bpm` (integer) for OpenSubsonic clients; `0` when unknown | unchanged |

All of them build the song through one serializer, `createSongNode` in
`src/libs/subsonic/impl/responses/Song.cpp`; `bpm` sits in its OpenSubsonic section, which already
sets every OpenSubsonic field unconditionally (`bitDepth` 0, `comment` ""), so a legacy client
(OpenSubsonic disabled for its client name) gets no `bpm`, as the spec expects.

This is additive, not breaking.

## Cross-App Impact

- **MuMa web UI** (`services/frontend`): none. It reads MuMa's BPM from `song.mumaBpm`
  (`lib/bpm.js`), never `song.bpm`, so the new field cannot shadow the measurement.
- **MuMa Mobile**: none. Its Subsonic client ignores unknown properties
  (`FAIL_ON_UNKNOWN_PROPERTIES = false`) and its song model has no `bpm`; the app's BPM comes from
  MuMa (`BpmRepository`).
- **music-manager**: none. It writes the tags; LMS reads them.

## Technical Acceptance Criteria

1. `parseBpm` unit test (`scanner/test/AudioFileUtils.cpp`): the formats and edge cases above.
2. `TrackMetadataParser` unit test: a `BPM` tag reaches `Track::bpm`; garbage and absence leave it
   unset.
3. Migration test (`database/test/Migration.cpp`): the column exists and is nullable, a re-run is
   harmless, and it bumps `audio_scan_version`.
4. Contract test (`tests/contracts/test_lms_subsonic_contract.py::test_song_carries_the_bpm_tag`):
   the fixture `ci-test-track-001.mp3` carries `TBPM 174`, and `getSong` and `search3` return
   `"bpm": 174`.

## Related Docs

- [bpm-tag-writeback](../bpm-tag-writeback/technical.md) — what writes the tags.
- `services/music-management-server/FORK.md` — the database version policy.
- `services/music-management-server/SUBSONIC.md` — the list of extra `Child` fields.
