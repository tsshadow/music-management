# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.93.1] - 2026-10-15

### Fixed
- SoundCloud downloads work again. Since 2026-10-13 SoundCloud serves only AAC streams, and the
  downloader asked for MP3 only, so every new track failed with "Requested format is not
  available". A track without MP3 now downloads its best AAC stream as `.m4a`, without a transcode.
  The tracks missed since then have no archive row, so the next run picks them up.

## [0.93.0] - 2026-10-04

### Added
- **The Now Playing screen shows the track's place in the queue.** The position ("4/100") sits
  right-aligned on the artist line and follows shuffle and reordering.

## [0.92.0] - 2026-10-04

### Added
- **The queue list shows each track's place in the queue.** A row has the title on the first line,
  the artist and the position ("3/500") on the second line, and the album and the date on the third.
  The position counts in the current play order, so shuffle and reordering update it.

## [0.91.1] - 2026-10-04

### Security
- **The LMS request log printed the token and salt of a Subsonic request.** Its parameter list
  replaced only `p`, `password` and `apiKey` with `*REDACTED*`, so every logged request showed `t`
  and `s`. A failed request is logged at `ERROR`, which production keeps. A signed `getCoverArt`
  URL that the app sent as an `id` also put the user name, token and salt in the line. LMS now
  redacts `t` and `s`, and the `u`, `t`, `s`, `p` and `apiKey` values in a parameter value that is
  a URL itself, also when it is percent-encoded (bug report 150).

## [0.91.0] - 2026-10-04

### Added
- **Interviews and DVD previews are no longer songs.** Two new track forms, `interview` and
  `preview`, mark 231 interviews and 20 Q-dance DVD and Blu-ray previews on production. The title
  decides, at any length: "interview" in a YouTube or SoundCloud title without "set", "mix",
  "intro" or "outro", and "DVD" or "Blu-ray" next to "preview". The about 5,400 song previews,
  trailers, teasers and aftermovies stay music. LMS leaves the two forms out of the songs and sets
  views, the artist page, `getSongs`, `getRandomSongs`, `getSongsByGenre` and the radio. Search
  still finds them, and `form=interview` lists them. The daily mix and the release radar skip them,
  song versions never group them (a grouped one leaves its work in the next round), BPM analysis
  skips them, and Beheer counts them apart from the tracks. The hourly form pass reclassifies the
  existing files, no migration. A client that expects every track from `getSongs` misses these
  now, and the phone's offline cache shows a cached interview until the next sync.

## [0.90.0] - 2026-10-03

### Added
- **`fix-catalogue-tag-mismatch.sh --from-folder-name` fixes the stale catalogue tags no .nfo
  confirms (#172).** The default mode left 272 releases whose files still hold the whole scene
  folder name as CATALOGNUMBER and where the folder and the .nfo agree on no number (268 without an
  .nfo, 4 whose .nfo names another one). The new mode writes the catalogue number in brackets in
  the folder name (`D-Teq_-_Arcade-(BIR047)-WEB-2012-SRG` gets BIR047), only when it passes
  `services/common/catalogue_number.py`. A folder without a passing bracket is listed with the
  reason and never written. An .nfo that states another number makes the release a conflict for a
  person: listed with both numbers, never written, the same decision the tagger's
  `HealStaleCatalogueNumberRule` makes. Dry run by default, a JSON backup before the first write, `--rollback`, and a second
  dry run finds nothing.

- **Three person scripts for what the label-tree cleanup left behind.**
  `park-duplicate-releases.sh` finds release folders that hold the same release twice in one label
  folder (838 groups on prod) and moves the weaker copy to `/mnt/music/.quarantine/`. A move happens
  only when the copies have the same format, the same source and tracks that pair on title and
  duration, and one copy wins on files, bitrate, scene name or .nfo (595 folders). Ties, vinyl next
  to web, scene fix releases and history held only by the weaker copy are listed for a person.
  `merge-stale-media-rows.sh` now also deletes the media rows whose file is gone from disk (8,372,
  mostly old `EPs/__TODO/` paths, `--gone`). It stops when a share looks unmounted.
  `fix-catalogue-tag-mismatch.sh` writes the folder's catalogue number into files whose
  CATALOGNUMBER disagrees with it, only where the release's .nfo agrees with the folder. It also
  replaces the whole folder name the tagger wrote as CATALOGNUMBER before bug report 145 with the
  bracketed number the .nfo confirms (76 releases). All three
  back up first and have a rollback.

### Fixed
- The importer no longer places a release folder that holds no audio, only scene files such as `00-*.m3u`, `.nfo`, `.sfv` and a cover. It deletes the folder from the import queue and writes an event that names the files it held. Before, such a folder went to the label tree, and LMS reported its playlist as missing entries after every scan. A folder with audio in a sub folder, an archive that is not extracted yet, or any other file stays (#167).

- **1,314 label releases had a date in their .nfo that the tagger did not read.** `NfoDate` allowed
  no more than 10 characters between a date label and its date, so it skipped labels padded with
  dots to a column: `Date..........: 11.23.2022` (AOV, AOV_INT) and `* street date .........:
  2024-03-17` (JUSTiFY). The date ladder then fell back to the arrival date or the year. The reader
  now allows the dot padding. A padded `Date` stays a rip date, and a padded street, release or store
  date keeps its own rung. Measured on production over the 48,769 .nfo folders of the label tree:
  1,314 folders get a date for the first time. One EDML folder changes from its `Release Date` to
  the `Store Date` above it, which is the same rung. No "Last Updated" stamp or other non-release
  date is read. `migrate_v57` adds the five month-first groups the seed script could not measure
  before (AOV, BMI, CMC, DDS, SCL), so `08.11.2023` from AOV reads as 11 August. Issue #169.

- The scanner now removes the library entry of a file that is gone from disk. A moved or deleted release folder used to leave its rows behind for good: 8,372 of 354,222 media rows on production on 2026-10-03. The track stays, with its ratings and listens. A track whose file was moved and retagged takes its history to the track the file became. Nothing is removed when the share is not mounted, a library folder is empty, or more than 10% of the files look gone. It is off by default (`scanner_drop_vanished_media`): the backlog goes through `merge-stale-media-rows.sh --gone` first, with its backup, and then a curator switches it on in Beheer > Config (#170, bug report 149).

- The deprecated `GET /api/downloaders/schedule/{source}` answers 200 again for a source with checked accounts. It answered 500 for each such source, because it read the check record as a date. The response shape is unchanged. The whole-tree type check (`backend:typecheck-all`) has no errors left and now fails the pipeline on a new one (#171, #41, bug report 148).

- A label track whose `CATALOGNUMBER` still holds the whole release folder name, written before bug report 145 (`D-Teq_-_Dark_Energy-(BIR030)-WEB-2011-HB`), gets a real number on its next retag. The tagger writes the number in the folder name's brackets when it passes the catalogue number test, with or without an `.nfo`, and clears the tag when the name has no such number. When the `.nfo` states a different number, the tag stays for a person to decide. Any other value, such as a number a person typed, stays as it is (#172).

### Security
- The weekly dependency audit (`security:dependency-audit`) is green again. It had failed on develop since pipeline 4434 with two findings. The frontend's `brace-expansion` moves from 5.0.9 to 5.0.12 for three denial-of-service advisories (GHSA-q2hr-2g5m-vwhr, GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p). Only ESLint loads it, at build time. Two urllib3 advisories (CVE-2026-97687, CVE-2026-97689) are accepted in `security/trivyignore`: they hit the copy that pip 26.2.1 bundles, which runs only while an image is built. No pip release bundles a fixed urllib3 yet. The urllib3 the services import is 2.8.0, the fixed version.

## [0.89.4] - 2026-10-03

### Fixed
- **The release-date backfill read month-first .nfo dates day-first.** `release_date_backfill`
  ignored `rules_scene_group_date_format`, which the tagger rule obeys. For the 29 groups that write
  month-first (OMA, PUTA, BC, NBD and others) its dry run took `Rip.date: 05.09.2022` for
  5 September. The rule and Deezer agree on 9 May. A correct date therefore looked like a person's,
  and a date stored day-first before the table existed looked like the rule's own. On production
  that made 765 swapped files in 120 releases look correct. The backfill now reads the dates the
  way the rule does.

## [0.89.3] - 2026-10-03

### Fixed
- **19 release folders in the label tree still had a festival anthem as their catalogue number.**
  The old Renamer's `Official_Hardbass_2026_Anthem - ...` names also reached `EPs/<label>/`, and
  the tagger wrote the anthem into each file as its catalogue number. `repair-word-prefixed-import-folders.sh --label-tree`
  renames them to the name the Renamer gives today. It moves the stored paths of their files with
  them, so track ids and ratings stay, and it clears a catalogue-number tag that holds exactly the
  word. The label stays the same. It never renames 3 ambiguous folders and lists them for a person
  (`I_Am_Frenchcore_05`, `I_Am_Frenchcore_12`, `NERKOLOG!K40`). Dry run first. Bug report 145.

## [0.89.2] - 2026-10-03

### Fixed
- The release-date backfill now asks Deezer about a release even when its tracks' date already
  equals the `.nfo` rip date. It skipped those tracks as "already at the best date" before Deezer
  had answered, so it never asked, and a single like Minus Militia and Nolz "Recover The Archive"
  kept its rip date (2026-10-01) instead of the Deezer date.

## [0.89.1] - 2026-10-02

### Fixed
- The release-date backfill now also picks up tracks that already have a full date from a lower
  rung of the date ladder (an `.nfo` rip date, the arrival date, or the file's own date) when
  their release now offers a better one, such as a Deezer date. Before, only year-only tracks
  were selected, so a track dated from the rip date stayed a day or a week off after its Deezer
  answer came in. The dry run counts these as `upgrade-from-<source>` (and `upgrade-pending`
  while Deezer is not asked yet). A person's date, or one from an equal or better rung, is never
  selected.
- The release-date rule no longer skips a full date without `DATE_SOURCE` that equals the
  release's `.nfo` date or the file's own `DATE`. Those dates were written by the same rule before
  the date ladder existed, and were taken for a person's date: the first backfill round on
  production left 4.141 of 15.385 files unchanged for that reason, some of them days off the
  Deezer date. Such a date now counts as its source, so a better source replaces it, and
  otherwise it gets its `DATE_SOURCE`.

## [0.89.0] - 2026-10-02

### Added
- **The importer reads the release's `.nfo`, and the Deezer album it links, for what the folder name
  lacks.** A release no catalogue rule routes goes to the existing label folder its `.nfo` names
  (`Label`, `Company`) or its Deezer album names; a catalogue number the `.nfo` states is used when
  the name has none. Measured on the queue of 2026-10-02 the `.nfo` alone places 2.159 releases that
  were waiting for a label decision. Switch: `import_place_by_label_name` (Beheer > Configuratie,
  group Importer). Backlog releases placed this way are logged without a phone push.
- **Where your filing and the `.nfo` disagree, you choose once per label.** Releases whose `.nfo`
  says `Cloud 9 Music` sit in `Cloud 9 Dance`: such a release is not moved but proposed with both
  folders in Beheer > Labelvoorstellen, and the folder you confirm is remembered for every later
  release with that label (`rules_label_name_choices`, migrate_v56, seeded with the 104 labels found
  in the label tree on 2026-10-02; re-learn with `scripts/prod/person/learn-label-name-history.sh`).
- **Release dates follow a precision ladder** instead of stopping at the year: the Deezer release
  date, then an `.nfo` release/street date, the file's own full date, the `.nfo` rip date, and for a
  new release the day it arrived. The rung is written to `DATE_SOURCE`; a better rung later replaces
  a worse one, never the other way round. The UPC goes to `BARCODE`. Year-only dates sort below
  every dated track of their year in "recently released"; 22.689 EPs tracks of 2024-2026 had one.
- `scripts/prod/person/backfill-release-dates.sh` (dry run first) lifts the year-only tracks already
  in the label tree; about 7.550 of them link a Deezer album. New table `release_store_lookups`
  (migrate_v55). Design: `docs/designs/release-info-enrichment/`.

- **`scripts/prod/person/merge-stale-media-rows.sh` removes the 1,493 stale media rows the hourly
  syncs skip** (issue #124, bug report 093). Each one's hash is not the SHA-256 of its path, so the
  scanner never sees it, and it holds a stub track with the file name as title. The script finds
  the live track for the same file (1,481 by path, 10 more by the path with a doubled release
  folder collapsed), merges the stub's ratings keeping the highest per user, moves its listens
  (dropping a listen the live track already has), takes it out of its works, and deletes the row
  and the stub. Two folder rows nothing refers to are deleted outright; anything referenced that
  cannot be matched would be kept and listed (none on 2026-10-02). JSON backup first, `--rollback`,
  one transaction per row.
- **`scripts/prod/person/delete-stale-m3u-playlists.sh` deletes the 574 scene playlists LMS reports
  after every library scan** (issue #96, bug report 121). It decides "missing" the way LMS's scan
  step does, from LMS's own database, leaves the import queue and partly-matching playlists alone,
  tars every file first, and asks LMS to rescan the folders. 572 of the 574 predate 2026; nothing
  in the importer or tagger renames a track, so no code change stops new ones.

### Changed
- **The app shows its home screen before the queue is restored** (issue #113). Inside the Android
  shell the web UI used to wait on the boot screen for one `getSong` per queued track (up to 200)
  before it mounted. It now mounts as soon as the server and session are known; the mini player
  says "Wachtrij wordt hersteld…" with a spinner and fills in when the restore finishes. A track
  started before then cancels the restore, so a late answer never replaces it; "add to queue"
  meanwhile keeps its tracks behind the restored ones. Nothing is pushed to the player service
  while the restore runs -- not the empty queue the UI starts with, not yesterday's queue from
  `localStorage` -- and a restore that finishes goes across paused, as before. LMS has no endpoint
  that resolves a list of track ids (`getSongs` filters by cluster, artist, work and form), so the
  lookups themselves are unchanged; they just no longer hold the first paint back.

### Fixed
- The folder-label cleanup script (`clear-folder-labels.sh`) gives a file whose label was its release folder's name the label folder above that release folder (`247 Hardcore`) instead of leaving it empty.
- The same script also repairs the label tree's own name (`EPs`, `Eps`) written as a label: it becomes the label folder the file sits in, and is cleared in `__Free&None`.

- **A festival anthem in a release name was taken for its catalogue number, and a name without one
  got an empty prefix.** `Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-...`
  became `Official_Hardbass_2026_Anthem - ...` and never reached `EPs/B2S`; 2.663 folders in
  `__TODO` were named ` - <release>`. The Renamer now only accepts something that looks like a
  catalogue number (rule derived from the label tree: it rejects none of the 21.408 prefixes the
  old Renamer produced there) and otherwise leaves the name alone.
  `scripts/prod/person/repair-word-prefixed-import-folders.sh` gives the 2.759 misnamed folders
  their name back (dry run first). Bug report 145.

### Security
- **The ListenBrainz import list and account deletion are admin matters now** (issue #38, left open
  by bug report 052). `GET /api/scrobble/import/latest` showed every account's last ten imports --
  name, ListenBrainz name and error text -- to anyone signed in; it now returns every account's
  rows to an admin or the system key and only the caller's own to anyone else.
  `DELETE /api/users/{id}` let a plain account delete itself (the check was "self or
  `users.update`"); it now takes `users.update` for every account. **Breaking** for a client that
  relied on self-delete: that call is a `403 Missing permission: users.update` now (no client in
  this repository made it). The last-admin guard is unchanged, and Beheer > Gebruikers shows the
  server's reason when a delete is refused instead of a generic error.

## [0.88.2] - 2026-10-02

### Fixed
- **`__Free&None`, `__TODO` and release folder names no longer become a label** (bug report 146).
  Production LMS listed 236 releases under `__Free&None`/`___Free&None`, 29 under `__TODO`, and
  371 "labels" that were a release folder's name (`STH685RMXBP - Bassjackers_-_...-SINGLE-WEB-2026-SRG`).
  The label is read from the folder a release is filed in, and the importer filed `FREE ...`
  releases into `__Free&None` and then tagged them with that folder as their publisher, without
  asking whether it was a label. One predicate now decides it for the tagger, the importer's
  label proposals and the scanner: a name starting with `_`, the import queue's name, or a name
  shaped like a scene release folder is never a label. A release in `__Free&None` gets no label at
  all, and a retag removes one it already carries. Real labels such as `DWX Copyright Free`,
  `Freestyle` and `I AM HARDSTYLE - Amplify` are unaffected.
- **`scripts/prod/person/clear-folder-labels.sh` removes the backlog.** The tagger cannot: it
  writes one publisher key per format, while the release folder names LMS shows sit in ID3 `TPUB`
  (LMS reads that first) and the `__Free&None`s partly in a FLAC `LABEL` the tagger never writes.
  The script cleans every label key per format and the muma label rows, backs up first, supports
  `--rollback`, and asks LMS to rescan.

## [0.88.1] - 2026-10-01

### Fixed
- **33,590 releases showed no cover even though their folder had one** (issue #158, bug report 144). Scene
  releases name the cover after the release (`00-artist_-_title-(cat)-web-2026.jpg`), and LMS only
  looked for `cover`, `front`, `folder` and `default`. When none of those is there, LMS now takes
  the `00...` image. If there are several, it skips proofs, back covers, inlays and disc scans
  (`...-proof`, `...-back`, `...-cd1`) and prefers one marked `front` or `cover`. It looks only at
  the part of the name that differs, so a title such as `come_back` does not count. If a folder
  has no `00...` image but exactly one other image, that image is used. An embedded front cover
  still comes first. Run over production's folders, the rule finds a cover for 33,445 of the
  33,590 releases. The 145 left have only proofs, scans or back covers. The new
  `cover-fallback-*` and `cover-single-image-fallback` keys in `lms.conf` configure it.
- **New cover rules reach releases scanned long ago.** LMS database step 126 (version 127) records
  which cover rules the last library-wide scan applied. When the rules differ, the next
  library-wide scan recomputes the covers of every release, track and artist, even if no file
  changed. No file is re-read. Changing `cover-preferred-file-names` now takes effect the same way.

## [0.88.0] - 2026-10-01

### Added
- **Correct a track's BPM by hand** (bug report 140). The track panel in the management library and
  the player's track details get ½×, 2× and a tempo field for users with the new `bpm.override`
  permission (admins by default). The tempo is stored separately (`library_track_bpm_manual`),
  wins over every measurement, is never overwritten by the analyzer, shows everywhere at once
  (library, BPM browse, feeds, analytics) marked "handmatig", is written into the file's tag by the
  next writeback round, and "Gemeten" takes it back. Every change is in the audit log
  (`bpm.manual_set` / `bpm.manual_cleared`). API: `PUT` / `DELETE
  /api/library/bpm/tracks/{id}/manual`.

### Fixed
- **A ballad no longer shows 256 BPM, and a slow industrial track no longer 230** (bug report 140).
  The analyzer forced every measurement into a hand-set tempo range per genre, and a track without a
  genre borrowed its artist's commonest one: André Hazes's genres here come from hardstyle and
  uptempo remixes of his songs, so "Vaag en Stil" (measured 64) was multiplied by four; The
  Silence's "Nothing" (a clear 115) had no octave inside industrial hardcore's 140-230 and went to
  230 -- both marked as reliable as a real measurement, and 835 such doublings were written into
  file tags. The octave (half, as measured, double) is now weighed on what the collection knows:
  learned tempo priors per label, per artist (their own tracks only -- remixes, bootlegs and style
  edits are left out by title) and per genre, recomputed daily; a pop-compilation folder (Hitzone,
  Spotify, Lidarr, Top 100); and the estimator's comb scores, now stored, which say when a
  neighbouring octave is no real periodicity. An artist's prior alone can never double a track into
  hard dance, and a genre-less tempo above 205 is halved unless the pulse clearly says otherwise.
  The stored confidence now includes how sure the octave is, so a guessed octave is not
  "betrouwbaar" and is not written into a tag. Every existing measurement is re-decided from the
  database when the bpm-analyzer starts; the ~89k doubtful ones are re-measured for their comb
  scores first (~6 hours), the rest after (~12). On a 10% sample of production 3.9% of tracks get
  another tempo and tracks above 200 drop by 15%; the evaluation set stays at its octave ceiling
  (84.7% within 1 BPM, hard dance unchanged). The tag writeback only writes tempos the new rule chose
  with enough confidence, and rewrites the files it wrote before whenever their tempo changed.

- The "Zachter" daily mix (and any mix holding a track whose hardness comes from its measured BPM) no longer fails with a server error (bug report 143).

- **A release series no longer collapses into one song.** The tagger read "｜ Q-dance presents
  SPEQTRUM", "(Gearbox Presents Lockdown 3.0)", "[DRS Presents: TSR Album 8.0 - TSR042]" and
  "(Dungeon: The Mini Album)" as the artist and title, so 63 SPEQTRUM uploads were one song by
  "Q-dance". The marker is now stripped and becomes the album (only over an empty or channel-default
  album); a catalogue number in it fills an empty catalogue number. A channel's own name as the last
  title segment (101Barz) is no longer the artist, and interviews, covers and event previews get the
  right artist. A featured artist no longer swallows the remix bracket behind it, so a remix is its
  own song again. A work with more than 10 versions is now marked for review. Affected files are
  re-tagged and regrouped after the deploy on their own (bug report 142).

## [0.87.1] - 2026-10-01

### Changed
- **Track lists show their first rows in the time a 50-row answer takes, whatever the page size.**
  The songs and sets lists, genres, labels, podcasts, festivals, years, lineups and search asked
  the whole page (up to 500 rows) in one `getSpotifyTracks` call; on production a 200-row page
  took 1.3 s idle and 12-17 s while LMS scanned. The first request now asks 50 rows and the rest of
  the page follows behind them, with versions folded across both; a revisit shows the whole page
  from the cache. Leaving a list for a page that is not a track list now aborts its request too,
  so it no longer holds an LMS connection the next page needs.

### Fixed
- **The web player was slow most of the hour because LMS kept scanning the whole library for one
  file** (issue #154, bug report 141). Every download asks LMS to read its folder, about 45 times an
  hour. Each of those scoped scans read the one file in a fraction of a second and then spent about
  41 s recomputing the artwork of all 343,000 tracks, 54,000 releases, 55,000 artists and 49,000
  playlists, plus every genre count. So LMS was busy most of the time, and the default track list
  took 12-17 s instead of about 1.3 s whenever it was. A scoped scan now recomputes only what its
  folders can have changed: their tracks and the rest of those tracks' releases, the releases,
  mediums, artists and genres involved, and the playlists in the folders. It also recomputes any
  genre whose count went stale, such as the one a retagged track left. A library-wide scan is
  unchanged, and catches the rare case a scoped one leaves behind (an entity elsewhere whose cover
  image was deleted, a playlist elsewhere that lists the new file).
- **The "recent" track list no longer sorts the whole library for every page.** A new index on the
  release-date expression the list sorts by takes the query from 0.65 s to 2 ms on a copy of the
  production database. It is created at startup, so there is no database version bump.

## [0.87.0] - 2026-09-30

### Added
- **Subsonic clients now see each song's tempo** (issue #150). LMS read the file's BPM tag but
  stored nothing, so third-party Subsonic clients showed no BPM even after 0.86.0 started writing
  the measured tempo into the files. LMS now keeps it per track (a new `track.bpm` column, database
  version 126) and returns OpenSubsonic's integer `bpm` on every song object -- `getSong`,
  `getAlbum`, `search3`, playlists and the rest share one serializer -- with `0` when the file has
  no tempo. The tag is read as `150`, `150.0` or `150,5` (rounded half up); anything else, or
  outside 40-500, counts as no tempo. The upgrade bumps the audio scan version, so the next scan
  re-reads every file once: that is what fills in the files whose tag was already right and which
  the writeback therefore never touched. An LMS image from before this change refuses the upgraded
  database. MuMa's own pages keep showing MuMa's measurement (docs/designs/lms-bpm/).

## [0.86.0] - 2026-09-30

### Added
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

## [0.85.6] - 2026-09-30

### Fixed
- **LMS no longer replaces the artist portrait music-manager chose on every scan with changes.**
  music-manager's hourly sync points each artist at its portrait, and LMS's artist-image step,
  which runs on every scan that found a change (every few minutes on production, for the folder
  scans the downloader and tagger announce), worked the artwork out again and overwrote it with a
  release cover or with nothing. Measured on production on 0.85.4: right after the hourly sync
  39,591 artists pointed at their portrait, 44 seconds later, after the next folder scan, 0. LMS
  now keeps an artist's artwork when it is an image under the managed portrait folder
  (`LMS_ARTIST_IMAGE_MANAGED_DIRECTORY`, `/music/artists` on the lms stack) and only chooses one
  itself for artists without one. The portrait-path repair's log line also names the server
  (`server-stable`) instead of `unknown` (bug report 139).

## [0.85.5] - 2026-09-30

### Changed
- **MuMa Mobile 7.15.0 checks the server at start-up** and offers Opnieuw proberen / Wachten op server / Offline verder when it is unreachable. See the muma-mobile changelog.

## [0.85.4] - 2026-09-30

### Fixed
- **Artist portraits are no longer removed from LMS and written back on every library scan.**
  music-manager wrote each portrait into LMS's database under its own mount (`/mnt/music/...`).
  Inside the LMS container that path does not exist, so every library scan removed about 20,000
  portrait rows at 0.2 s each, more than an hour per scan, and most artists had no portrait until
  the hourly sync wrote the rows back. The sync now uses the path LMS sees (`/music/...`), which
  is usually a row LMS's own scanner already made for the same file. A repair pass moves the rows
  written earlier. LMS also gets indexes on the seven columns that point at an artwork, so
  removing an image now takes microseconds instead of 0.2 s, whatever the reason for the removal
  (bug report 138).

- **A new download shows up in LMS within minutes again while a library scan runs.** Priority
  passes for announced folders came about 30 minutes apart on production. The walk was not the
  cause, it checks every 10 files. The check for removed files was: before a pass it finished every
  job in flight and first deleted everything they had found. On production that meant up to 10,000
  image rows at 0.2 s each (the artist portraits under `/mnt/music/artists`, outside LMS's
  library). The deletion now runs 50 rows at a time with a check in between, so a due pass waits
  about 10 s instead of half an hour. One pass also reads at most 50 folders; the rest go in the
  next one (bug report 136).

## [0.85.3] - 2026-09-30

### Changed
- Internal: Klassiek, Zachter, Middenin and Harder now share one pair of day-stable library
  samples per listener instead of each drawing the same two (issue #138). The nightly
  feeds-refresh spent ~24 s of SQL per listener sampling the library four times for one answer;
  it now spends ~6 s. The mixes themselves are unchanged -- the same ids in the same order, reused
  in-process for up to ten minutes. The label mix keeps its own samples, since it filters on its
  label.

### Fixed
- **New tracks get their scrobble-matching keys the moment they are scanned.** `normalized_title` and `normalized_base_title` were never written by the scanner; a background pass filled 500 rows an hour, and after the 67,331-row label-tree rescan of 2026-09-26 every track added since sat without them, so a listen spelled slightly differently from the tag (case, accents, a "(Radio Edit)") waited in the retry queue instead of linking. The scanner now writes both keys with the row, and the background pass drains whatever other writers leave behind in one go (up to five minutes, `SCROBBLE_BACKFILL_BUDGET`). The ~16,000 rows still missing them on production are filled by the first pass after the deploy. Bug report 137.

## [0.85.2] - 2026-09-30

### Fixed
- **A write-heavy LMS scan no longer locks every other writer out of lms.db.** The scanner commits
  in small batches, but it started the next transaction as soon as the previous one committed. The
  lock was free for microseconds at a time. music-manager's hourly sync, which sleeps up to 100 ms
  between attempts at the lock, never got in and gave up after 10 s. Measured locally against a
  bulk writer with music-manager's settings, the result was `database is locked` after the full
  10 s in every case. After 0.5 s of writing the scanner now waits 120 ms without the lock. The
  same measurement gets the lock in 3 to 231 ms. A scan that paused says so in the log after its
  summary. A scan-files transaction also commits once it has run for 250 ms, and the WAL file is
  truncated back to 64 MB after each reset instead of staying at its high-water mark (1.09 GB on
  production). The 20 s runs measured on production on 2026-09-29 came mostly from the
  per-cluster transactions fixed in 0.83.0. On 0.85.0 the lock was held in 2 of 38,528 samples
  across three scoped scans (bug report 134).
- **A locked database no longer takes LMS down from a podcast refresh or a ListenBrainz sync.**
  These background writes ran on a thread that logs FATAL and aborts the process on any exception.
  None of them caught a write the database refused after its 15 s wait. A refused write is now
  logged as a WARNING and retried on the next round. A podcast refresh ended this way no longer
  stops refreshes for good (bug report 135).

## [0.85.1] - 2026-09-30

### Changed
- **MuMa Mobile 7.14.0 adds a BPM folder to Android Auto** (Nummers → Bladeren → BPM). See the muma-mobile changelog (issue #140).

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

## [0.85.0] - 2026-09-29

### Added
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

## [0.84.1] - 2026-09-29

### Changed
- **Visual reference refreshed for the BPM tile** on the phone browse page.

### Fixed
- **A release that changes the web UI now always ships a new app build.** The app serves the web
  interface baked into its APK, but the release check only asked for an app version bump when
  `services/muma-mobile` changed, and compared against develop, where every change merged before the
  cut is invisible. So 0.84.0's BPM browsing and statistics filters reached the web player but no
  phone. The check now compares both the app and the frontend against the last release (bug report
  133).

## [0.84.0] - 2026-09-29

### Added
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

- **Listening statistics by genre and release year, with filters.** The statistics page now shows
  your most played genres and a release-year chart (per year or per decade, tracks without a usable
  date in their own "Onbekend jaar" bar), and every panel -- totals, timeline, clock, sources, top
  tracks/artists/labels and the two new ones -- can be narrowed to one or more genres and/or years:
  pick genres in the filter bar (your own genres, most played first), type a from-to year range, or
  tap a bar in either chart to toggle it. Several genres mean any of them; a genre and a year must
  both hold. The filter is in the URL, so a view can be bookmarked or shared. A track with several
  genres counts for each, and the genre panel says the bars overlap. Genre and year are only known
  for a linked track, so a filter excludes every listen that was never matched to the library; the
  page says how many right under the filter instead of silently shrinking the totals. API:
  `GET /api/listening/top-genres`, `GET /api/listening/years`, and the parameters `genre`, `year`
  (a year or `unknown`), `year_from`, `year_to` on every `/api/listening/*` endpoint, which also
  report `excluded_unmatched` (docs/designs/listening-stats/). No schema change.

## [0.83.0] - 2026-09-29

### Added
- **New feed "Oude hitjes": old favourites you play less.** The daily mixes lean on recent
  releases, so an old anthem rated five stars never came back without a search -- on production
  702 old tracks carry 4-5 stars and 584 old tracks played three or more times had not been played
  in six months. The new feed (100 tracks, stable for a day, "Meer laden" like the others) fills
  about 40% with your own old 4-5 star songs, 30% with old songs you played at least three times
  but not in six months, and 30% with known hits by artists you rate or play: an artist's top
  tracks on Deezer (and Last.fm when `lastfm_api_key` is set), or songs the library holds four or
  more versions of. "Old" is released more than three years ago by the earliest date of any version;
  anything rated 1-2 or played in the last 90 days is left out, one version per song, at most three
  per artist. It shows after the daily mixes on Home and the phone's "Daily mixes" page, at
  `/old-hits`, and via `GET /api/feeds/old-hits`. A new hourly `popular-tracks` loop fetches the
  top lists for the ~940 artists that matter (a 4-5 star track or five listens), weekly per artist,
  at most four requests a second, sending only artist names, into the new tables
  `artist_popular_tracks` and `artist_popularity_fetches` (migrate_v49). Every threshold is a
  setting in the "Feeds" group (`old_hits_*`, `popular_tracks_*`).

### Changed
- **The daily mixes are no longer only this year's releases.** Klassiek, Zachter, Middenin, Harder
  and the label mix drew only from the last 90 days, so on 2026-09-29 they were 96-100 % tracks from
  2026. Now half of each comes from the last 12 months and half from older songs that fit the
  listener's artists, labels and genres -- leaving out what they rated 1-2 stars and preferring what
  they have not played lately. A short half is filled from the other. Tunable in Beheer -> Config ->
  Feeds (`feeds_daily_recent_percent` 50, `feeds_daily_recent_window_days` 365,
  `feeds_daily_older_min_rating` 3). Release Radar and the artist mix are unchanged (bug report 131).

- **"Meer laden" on a daily mix no longer rebuilds the mix, and building one is 2-3x cheaper.**
  Klassiek, Zachter, Middenin, Harder and the label mix now rank 500 places in the same build and
  store everything past the first page, so the next page is read from the stored row instead of
  sampling the library twice again (about 11 s of queries on production). The samples themselves
  were slow because every feeds query grouped the whole audio-features table per scanned track to
  find a release date that `library_tracks` already had; they read it per track only when needed
  now -- recent half 4.8 s to 1.7 s, older half 6.1 s to 2.7 s, measured on production (issue #137).

- **Visual references refreshed for the Oude hitjes card** on the daily mixes page (desktop and phone).

### Fixed
- **LMS no longer crashes when music-manager's hourly lms.db sync runs during a scan.** The scan
  step that updates the genre, mood and festival track counts opened a separate write transaction
  for every cluster and rewrote each one, changed or not. That meant thousands of trips for the
  write lock on every folder scan. When one of those trips landed inside a music-manager sync
  batch, SQLite refused the UPDATE at once, even though LMS is configured to wait 15 s for the
  lock. The error `update "cluster" ...: database is locked` escaped the scanner thread and took
  the whole server down with `std::terminate`. It happened twice in 72 hours, both times inside
  the sync pass. The configured wait was ignored because Wt starts transactions as deferred, and
  SQLite does not wait when a transaction that has already read tries to write. Now every LMS
  write transaction starts with `BEGIN IMMEDIATE`, so it waits for the lock. The step writes only
  the clusters whose counts changed, in one transaction per 100 clusters. A write the database
  still refuses is logged as a WARNING and retried on the next scan; the process keeps running
  (bug report 132).

- **The LMS log no longer carries an ERROR every 30 seconds from its own healthcheck.** The probe
  called `/rest/ping.view` without credentials, which LMS logged as "Required parameter 'c' is
  missing" 2,880 times a day. It now asks `getOpenSubsonicExtensions`, the one Subsonic call that
  needs no login, and still only checks that an HTTP thread answers.

## [0.82.2] - 2026-09-29

### Changed
- **MuMa Mobile 7.12.2 only updates its test and lint tooling.** No change in the app itself.

### Fixed
- **The downloader filled the event log and the alerts topic with lines that describe nothing
  wrong.** In 36 hours on production: 320 `This video is DRM protected` ERRORs, 629 `http_mp3`/
  `hls_mp3 format not found` WARNINGs and 157 `webm doesn't support embedding a thumbnail`
  WARNINGs. DRM-protected SoundCloud tracks were never written off and were fetched again on
  every sweep; they are now recorded in `downloads_soundcloud_unavailable` (reason `drm`, retried
  after 30 days) and skipped before extraction, since yt-dlp fails them before the ordinary match
  filter runs. YouTube audio channels ask for `bestaudio/best` instead of yt-dlp's default video
  merge, which downloaded every video whole only to throw it away after extracting the same audio;
  the m4a files are unchanged. A short explicit allowlist of such yt-dlp lines is logged at INFO;
  every other yt-dlp warning keeps its level. And five ERRORs a day titled just `root: ERROR: `
  now carry the failure in the title: yt-dlp's leading `\r` split it off (bug report 130).

- **The hourly lms.db sync no longer raises a WARNING per batch while LMS scans.** LMS's scanner
  holds its database's write lock for runs of up to twenty seconds, for as long as a scan lasts --
  and folder scans after downloads arrive up to 180 times an hour. The song-version and track-form
  pushes waited two seconds, slept a minute, tried three times per batch and then dropped the batch
  with `gave up on a batch after 3 locked attempts`: 40 WARNINGs a day, one pass parked for eleven
  minutes, and the track-form push's refusals logged under the song-version logger. Nothing was
  actually lost (the next pass rewrote the same rows; a production sample of 516 files matched),
  only delayed. Now each batch takes the lock up front (`BEGIN IMMEDIATE`, 10 s wait, still 100
  UPDATEs per transaction), the first refusal defers the pass's remaining rows instead of sleeping,
  and those exact rows are written again five minutes later, up to five times. One WARNING per hour
  remains, and only when rows are still unwritten after half an hour (bug report 129).

- **One night of YouTube refusing yt-dlp made the nightly production report unusable.** The
  fingerprint normalisation in `scripts/nightly-prod-check/collect.py` folded a SoundCloud item id
  away but not a YouTube video id: that only ever happened through the catch-all `\S*_\S*` rule,
  and a video id is eleven characters of `[A-Za-z0-9_-]`, so roughly one in three. On 2026-09-25
  that turned 22,170 downloader errors with nineteen causes into 7,638 attention items -- one per
  video, against a budget of two fix MRs -- and wrote 7,634 dead rows into the ledger. `[youtube]`
  and `[youtube:tab]` now get the same explicit rule `[soundcloud]` has; the same night folds back
  to 19 fingerprints. The replacement is `<name>` rather than `<item>:` on purpose, so every
  fingerprint the catch-all already folded -- and the verdict the ledger holds against it -- keeps
  its key.

### Security
- **Release images pick up the day's OS security updates again.** The Dockerfiles' `apt-get
  upgrade` / `apk upgrade` steps came out of the CI runner's layer cache, so the LMS image shipped
  with 0.82.1 still carried an upgrade from 2026-09-17 and a libexpat with a fixed HIGH CVE
  (CVE-2026-93990). A build argument that changes daily now forces that layer to rebuild, and the
  public base images are pulled fresh (bug report 128).

## [0.82.1] - 2026-09-27

### Fixed
- **MuMa Mobile 7.12.1 resends its Android Auto buttons when repeat or shuffle changes, and logs a fuller diagnostics line for the missing car buttons.** See the muma-mobile changelog (issue #130, bug report 127).

## [0.82.0] - 2026-09-27

### Added
- **A label page lists the channels linked to it** (issue #122, `docs/designs/channel-links/`).
  Under the label's heading a **Kanalen** section shows every SoundCloud, YouTube or Telegram channel a
  curator linked to that label, busiest first, with its platform and number of tracks; tapping one
  opens the channel's tracks (the `Soundcloud (<channel>)` / `Youtube (<channel>)` album), or the
  account's page on the platform when the library has no such album. A curator also gets
  **Koppelingen beheren**, which opens Beheer -> Downloaders on the Koppelingen tab, and sees the
  section (with its placeholders) on every label; a listener only on a label that has channels, so the
  track list does not jump on the many that have none. On production (2026-09-27) no channel is
  linked yet -- 898 proposals await review -- so the section fills as they are confirmed. New:
  `GET /api/channel-links/by-label?name=` (read-only, index lookups only, no schema change).

- **The artist evidence run now runs by itself, once a day, inside music-manager** (issue #49,
  `docs/designs/artist-curation/technical.md`, "Scheduled evidence run"). `tools/artist_auto_approve.py`
  approved 5.903 names when it was run by hand on 2026-09-20; since then only 8 of ~3.300 new names
  left the queue. The new `artist-auto-approve` loop looks up every new (pending) name plus 300
  older ones a day, most tracks first, on Deezer, iTunes and MusicBrainz at their documented rates,
  with the tool's own rules (the judgement moved to `services/common/Helpers/ArtistEvidence.py`, so
  both share it). A round is bounded (1.000 names, 180 minutes), writes one INFO line to the event
  log and a row to the new `rules_artist_evidence_runs`; verdicts live in `rules_artist_evidence`
  (migrate_v47). **Dry run is on by default**: it approves nothing until "Artist curation -> dry run"
  is switched off in Beheer, after which the first round also applies what the dry runs judged
  approvable. Approvals are signed `auto-external`, never overwrite a curator's decision, and an
  undone approval is never made again; nothing is ever rejected automatically. Review them on the
  Goedgekeurd tab with the new "Automatisch (bewijsronde)" filter (`GET /api/rules/artists` gains
  `decided_by` and `sort=decided`), or per round via `GET /api/rules/artists/auto-approve/runs`.
  Measured on prod: 49.382 undecided names, 325 of them new; about 20-25 minutes of lookups a day.

- **A channel link now changes the tags, and a channel the search found nothing for can be linked by
  hand** (issue #58, `docs/designs/channel-links/`). Until now a confirmed link between a
  SoundCloud/YouTube channel and its label or artist was only shown in the Volledigheid table. The
  tagger reads it now: a download from a linked channel gets the linked label as its publisher --
  which the library stores as the track's label, where it used to store none because the publisher
  was always the platform -- and the linked artist replaces the channel name wherever that name
  was only standing in for an artist because the title named nobody. An artist the title did name
  is never touched, a real label is never overwritten, and the linked label's genre rules apply as
  they do to a label release. Linking, confirming or unlinking queues the channel's files for the
  tagger (reason `channel_link`, served after decisions and new files). Beheer -> Downloaders ->
  Koppelingen gains a **Handmatig koppelen** panel: type part of a channel's name, pick label or
  artist, type part of that name (only approved artists and real labels are offered) and link; the
  Volledigheid table has a **koppelen** button on every channel with no link and no proposal. On
  production (2026-09-27) the 149 open label proposals cover 52.128 tracks, 50.449 of which have no
  label today; 515 channels with 77.171 tracks got no proposal at all and can only be linked by hand.
  New: `PUT /api/channel-links/channels/{id}/{kind}`, `GET /api/channel-links/channels` and
  `GET /api/channel-links/targets`; `confirm` and `unlink` responses gain `queued` (additive);
  `channel_link_proposals.source` gains `manual` (`migrate_v48`).

### Fixed
- **A new download stayed invisible in LMS for as long as its library-wide scan ran -- well over
  an hour** (issue #125, `docs/bug-reports/126-scoped-scans-wait-for-full-scan.md`). On production
  the library-wide scan started at 15:38 on 2026-09-27; by 17:23 LMS had received 225 scan
  requests, 224 of them folder announcements from the downloader and tagger, and started not one
  scan. Before 15:38 each announcement was read within about a minute. The cause: the "pause the
  library scan for a scoped one" path ran on the scanner's io thread, which is the thread the
  library scan itself occupies, so it could only fire once there was nothing left to pause.
  Announced folders now go into a queue the running scan reads itself: at a safe point in the file
  walk, the removed-files check and between steps, it runs a priority pass over them -- the
  ordinary scoped scan -- and carries on where it was, without restarting or aborting anything
  (bug report 120's loop stays closed). Two minutes of library scan between passes keep a busy
  tagger from stalling it. The scan summary in the log gains `priority passes = N (M folders)`,
  each pass logs its own `Priority scan of N announced folder(s) complete` line, and
  `getScanStatus` gains `pendingFolders` and `priorityScan`.

### Security
- **Every production container now drops all Linux capabilities and has a PID ceiling; LMS, its
  nginx proxy and autoheal also run on a read-only root filesystem** (issue #32,
  `docs/deployment.md`, "Container hardening"). Until now `no-new-privileges` was the only
  hardening, and the LMS stack did not even have that. Each service gets back only a named set:
  the muma Python images and LMS keep root's four file capabilities (CHOWN, DAC_OVERRIDE, FOWNER,
  FSETID) so their access to the music share and `lms.db` is unchanged, and lose raw sockets,
  MKNOD, SETUID/SETGID and the rest; MariaDB, phpMyAdmin and nginx keep what their root parent
  needs to switch users and bind port 80; autoheal needs nothing. `pids_limit` sits far above the
  PID counts measured on production (29 for music-manager, 40 for LMS, 326 for Firefox). The test
  stack runs the same settings, so core-smoke, the e2e chain and the contract suite exercise
  them. Applies to a container when it is next recreated -- `db` on a `DEPLOY_DB=1` deploy. Not
  done yet, listed in the deployment doc: non-root users and read-only roots for music-manager
  and the workers, and Firefox.

- **No password, token or key goes on a command line any more, outside the deploy as well**
  (issue #40, bug report 125). The release jobs sent the GitLab tag/merge token as a curl header,
  Renovate and the mobile release build passed their tokens and the signing passwords as
  `docker run -e NAME=value`, the nightly check and crash triage put the production system API key
  in a curl header, and three prod scripts put the MariaDB root password on the argv of
  `docker exec` or the client -- all readable through `ps` by every account on the shared runner or
  the production host. They now use `MYSQL_PWD` via `-e NAME` without a value, curl headers through
  a process substitution, ssh's stdin, `sshpass -e` and `keytool -storepass:env`;
  `scripts/migrate_lms_history.py` reads its key from `MUMA_API_KEY`. The nine scripts that still
  read `.env` with the loop that cut `ab#cd` to `ab` use `scripts/lib/dotenv.sh`, as the deploy
  does. A new CI test (`tests/ci/test_no_secrets_on_command_lines.py`) fails on any new
  occurrence.

## [0.81.5] - 2026-09-27

### Changed
- **Settings loads only the tab you open, and Now Playing left the web player's first file
  without opening any slower** (issue #119, `docs/designs/perceived-performance/technical.md`
  section 7). The settings page was one 79 kB chunk with all five tabs in it; each tab is its own
  chunk now, so opening settings on General fetches 36 kB instead of 81 kB (9 kB instead of
  18 kB gzip) and a browser never fetches the device tab. A tab still loading shows its own shape
  in skeleton blocks, and the next tab in the list is fetched in the background. The full-screen
  Now Playing moved out of the entry chunk; the mini player stays in it, the view is fetched on
  idle after the first frame and the moment a finger touches the mini player, and if it is still
  on its way a seeded stand-in draws the same screen at once -- cover, title, artist and a working
  play/pause -- so opening it never waits. The entry went from 300 kB to 255 kB (89 to 76 kB
  gzip); everything loaded before the first screen from 420 kB to 405 kB (137 to 133 kB gzip).

## [0.81.4] - 2026-09-27

### Changed
- **The web player's first screen loads another 70 kB less, and its translation file no longer
  waits for the app's code** (issue #118, `docs/designs/perceived-performance/technical.md`
  section 7). The artist, album, feed, preset and playlist pages, the filter bar and the
  collection grid and bar were still in the entry chunk; they are chunks of their own now, fetched
  on idle after the first frame and, for artist, album and feed links, the moment a finger goes
  down together with the page's data. The artist and album heading still appears at once: until
  the page's code is in, a small seeded stand-in (`EntityPageShell`) draws the same header from
  what the tapped link knew. `index.html` now carries a `modulepreload` for the listener's locale
  file, so the browser fetches it together with the entry instead of one round trip later. The
  entry went from 370 kB to 300 kB (107 to 89 kB gzip); everything the first screen waits for,
  one locale included, from 580 kB to 511 kB (184 to 168 kB gzip).

### Fixed
- **A shuffled preset paged into a new shuffle every 100 tracks** (issue #103). The web's
  `getSongsContinuation` sent the preset's `seed` to `getSongs`, but the LMS fork only read `seed`
  on `getSongsByFilter` and `getSpotifyTracks`; every page of a Random preset was a fresh
  `RANDOM()` draw, so "Meer laden" and the queue top-up repeated tracks (hidden by the dedupe as a
  shorter page) and could skip others. `getSongs` now honours `seed`, which Android Auto's new list
  continuation relies on as well. Additive: a request without `seed` shuffles as before.

## [0.81.3] - 2026-09-27

### Changed
- **The web player's first screen loads less than half the JavaScript it used to** (issue #114,
  `docs/designs/perceived-performance/technical.md` "Code splitting"). The bundle was one 1.29 MB
  file (350 kB gzip), so every start parsed all of Beheer, the settings pages, the statistics
  pages and all four translation files before the home screen could paint. Pages off the first
  screen are now chunks of their own, fetched when opened (`lazyViews.js`, `LazyView.svelte`):
  settings and its sidebar, Beheer's shell and sidebar and each of its tabs (Scrobble excepted),
  history, listening statistics, starred, memories, song versions, the curation edit pages, the
  preset builder, voice, downloads, the car screen, the setup tour, the search "more" modal, the
  track details sheet and the equalizer. Each translation file is a chunk too, and only the active
  locale is waited for (Dutch is complete, so English follows in the background). The entry chunk
  went from 1,289 kB to 370 kB (107 kB gzip); everything that loads before the app mounts -- the
  entry, the chunks it imports and one locale -- is 580 kB (184 kB gzip).
  - **Opened by URL**, a lazily loaded page's chunk is fetched behind the boot screen, so the app
    appears with the page instead of a skeleton. **Opened by navigating**, the page shows skeleton
    rows while its chunk loads, and a chunk that fails shows the section error with a retry. The
    settings page, song versions, the search "more" modal and the details sheet are fetched on idle
    once the first screen is up, and Beheer's shell and first tab as soon as the account turns out
    to be an admin.
  - **Deploys.** LMS now sends `Cache-Control: public, max-age=31536000, immutable` for the hashed
    files under `/assets/` and `no-cache` for everything else it serves from the web UI's docroot,
    `index.html` and the SPA route fallback included. It sent no cache headers at all. A tab left
    open across a deploy that asks for a chunk the new build replaced reloads once
    (`vite:preloadError`) instead of showing a retry that cannot succeed.
  - **Measuring.** `BUNDLE_REPORT=<file> vite build` writes a per-chunk, per-module size report and
    `node scripts/bundle-report.mjs <file>` prints it, with the entry's static-import closure.

## [0.81.2] - 2026-09-27

### Security
- **The web player keeps no copy of the password after signing in** (issue #101). Since issue #72
  it signs nothing, but `lms_credentials` in localStorage still held it -- and, after a Google
  sign-in, the MuMa API key in its place -- for two jobs: re-logging in when MuMa refused the stored
  key (`Management.svelte`'s auto-login), and telling the Android shell's boot whether to sign in
  again.
  - **Sign-in.** `signIn` and the Google path store the name only; the login form clears its
    password field once the sign-in succeeds.
  - **Existing sessions.** A stored password is dropped the first time the page loads
    (`withoutPassword`, and the persisted value is rewritten without it) -- the session itself
    stays, it lives on as the MuMa key and the Subsonic token.
  - **A refused key.** MuMa answering 401/403 to the stored key at start-up or on the management
    screen now ends the session and shows the login page. It used to be traded silently for a new
    key with the stored password. The key is permanent, so a refusal means it was revoked or the
    account is gone.
  - **Signed in.** "Signed in" is one explicit state, `signedIn` (a name or a MuMa session), and
    no longer depends on a stored password.
  - **Also removed.** The unbuilt `spotify-ui` copy of the player in the LMS tree
    (`services/music-management-server/src/lms/ui/spotify-ui`, issue #102), which still signed
    with `p=<password>`. Nothing built, served or imported it: `Dockerfile-release` copies
    `services/frontend` into LMS's `docroot/spotify`, which `SpotifyResource` serves. Its accepted
    SAST finding is gone with it.

## [0.81.1] - 2026-09-27

### Changed
- **A genre, label, festival, podcast, year or lineup no longer shows the previous list under its
  name, and search no longer says "No results" before it has asked** (issues #109 and #112,
  `docs/designs/perceived-performance/`). Opening a second genre left the first genre's tracks on
  screen under the new heading until `getSpotifyTracks` answered, and one loading flag shared with
  the collection grids could mark the list done while it was still loading. The list now clears on
  every new place and shows skeleton rows; a filter change on the same list keeps the old rows
  dimmed until the new ones arrive; a failure is a section error with a retry instead of an empty
  "Geen nummers" state. The first page of every list is cached per query for five minutes
  (`trackListCache.js`, stale-while-revalidate, refreshed after one minute), so going back is
  instant, and pressing a genre/label/podcast/festival/year/lineup card starts that list's
  request on pointerdown, one request per press and shared with the page. The search results page
  gives tracks, artists and albums their own skeletons, errors and retries, shows "Zoeken…" while
  any is out, and says "No results" only once all three answered empty. The search dropdown
  says it is searching from the first keystroke (the 300 ms debounce included), keeps the previous
  results dimmed instead of flashing "No results", and offers a retry when `search3` fails. History,
  Starred, Memories and the search "more" modal swap their whole-page "Laden…"/spinner for
  skeleton sections, and Starred, History and the modal show an error with a retry where they
  used to claim there was nothing. The style guide's Loading States section gains the stale-results
  and search-as-you-type rules.

- **Feeds, the release radar, the daily mixes and a song's versions open at once and fill in**
  (issues #110 and #111, `docs/designs/perceived-performance/`). A daily mix showed its header and
  then a bare "Laden..." until MuMa had answered and every `getSongsByPath` chunk had been
  resolved, one after another. The song page (`song:`) showed nothing but "Laden..." until up to
  five pages of `getSpotifyTracks` had come back. A tapped daily-mix card now leaves its title and
  subtitle, and a tapped versions button the track's title, artist and cover: both pages draw that
  header at once, with skeleton rows where the tracks go. A feed's chunks are resolved in parallel
  (`/rest` does not pass the serial MuMa gate, and a feed is at most two chunks) and each chunk's
  rows appear as it lands, always in MuMa's order. A chunk LMS fails to answer, or the feed itself,
  gets its own "Opnieuw" instead of being counted as 100 files missing from the server; the
  "N niet gevonden op de server" note (bug report 122), "Meer laden" and the queue continuation
  from !1084/!1087 work as before, and play pressed during loading starts the feed when it is in.
  Each page of versions is drawn as it arrives. A revisit within five minutes comes from the
  entity cache. The daily mixes page shows card-shaped skeletons, and the track details sheet
  shows skeleton rows while it asks MuMa for the tags, with a retry after a failure.

### Fixed
- **The play button on a daily-mix card could not be seen on a phone or tablet** (issue #99).
  It only appeared on hover (`opacity-0 group-hover:opacity-100`), and a touchscreen has no hover.
  On a coarse pointer it is now always visible and 48px (the style guide's touch target); with a
  mouse it still appears on hover, and now also on keyboard focus.

## [0.81.0] - 2026-09-27

### Added
- **The app says what it is doing while it starts, and an artist or album opens at once** (issue
  #107, `docs/designs/perceived-performance/`). Until now a cold start showed a black page until the
  bundle had run. In the app it stayed black until the server, the session and up to 200 queued
  tracks had been restored. A tapped artist showed a bare "Laden..." until `getArtist` had
  answered, and only then asked for the tracks. `index.html` now paints a boot screen from the first
  frame: the MuMa mark, the stage ("Verbinden met de server…", "Inloggen…", "Wachtrij herstellen…"
  with a filling bar), a hint after 8 s and a retry button after 20 s. A link to an artist or album
  now leaves what it already knows (name, picture, cover, artist). The page draws its header from
  that at once, with skeleton rows and tiles where the data still has to come. The artist page
  starts `getArtist`, `getSpotifyTracks` and `getArtistInfo2` together instead of one after
  another. Each section loads, fails and retries on its own, and play pressed before the tracks
  arrive waits for them with a throbber. A revisit within five minutes renders from an in-memory
  cache and refreshes in the background. The page's main request starts on pointerdown and is
  shared with the page, one request per tap, never on hover or scroll. New building blocks:
  `entityCache.js`, `entitySeeds.js`, `entityLoaders.js`, `bootScreen.js` and
  `src/lib/loading/` (Skeleton, SkeletonRows, SkeletonTiles, Throbber, SectionState). The style
  guide's Loading States section now covers the boot screen, the optimistic page shell, section
  errors and the inline throbber.

### Security
- **The web player never signs a Subsonic request with the password any more** (issue #72, bug
  report 124). Since bug report 103 it signed with the per-user Subsonic token, but fell back to
  `p=<password>` in plain text whenever no token was stored. On production that was the normal
  case: the web shell sent 1,200 `/rest` requests with `p=` on 2026-09-27 while the native client
  signed all of its requests with the token.
  - **Cause.** The token was fetched once per page load and a failed fetch was never repeated. The
    phone's WebView page outlived the music-manager restart that made its fetch fail, and signed
    with the password until the app restarted at 05:17 -- in the same second its next fetch
    succeeded, it switched to `t=`.
  - **Fix.** `authParams` is now the token query or empty. A missing token is fetched before the
    first request and asked for again every 30 s, on returning to the page and on reconnecting. A
    sign-in retries a busy token endpoint and fails instead of pinging with the password.
    `subsonicJson` sends nothing unsigned.
  - **What you see.** While no token can be had a notice says "De server geeft geen toegang" (with
    a retry) or "Log opnieuw in" instead of showing an empty library.
  - **Also fixed.** The search thumbnails, which carried no credentials at all, are signed.
  - **Proof.** A Playwright test against the test stack asserts that no API, cover or stream
    request carries `p` across four starts: fresh sign-in, stored session, start without a token,
    and start whose token fetch fails.
  - **Password storage.** The stored password now only re-obtains a refused MuMa key and marks the
    session as signed in.

## [0.80.0] - 2026-09-27

### Added
- **Every long list keeps going in the queue, not only the daily mixes** (issue #100,
  `docs/designs/list-continuation/`). Playing "Nummers · Recent uitgebracht" from its first row
  queued the 50 tracks on screen and then stopped. The same happened with every other sort and
  filter of the songs and sets lists, with a genre, label, podcast, festival, year or lineup, with
  search results, an artist's tracks, a preset, the listen history, a memories year and the car-mode
  mix. Each of these lists now hands the queue it starts a continuation. The queue tops itself up
  near its end, as the daily mixes already did, and the queue sheet and side panel end in "Meer
  laden" while the list has more. Once a list that did continue has nothing more, both the page and
  the queue end in "Einde van de lijst". A track the queue already holds is never added twice, and
  a failed page is tried again on the next track or tap. Search results now also get "Meer laden" on
  the page. The feed-only top-up (`feedQueue.js` `extendFeedQueue`, `QueueFeedLoadMore`) became one
  source among several (`listContinuation.js`, `trackPages.js`, `QueueLoadMore`, `ListEnd`). Albums
  and playlists are loaded whole and are unchanged.

- **Logging out asks first** (issue #80). The profile menu's "Log out" logged out on a single tap,
  stopping playback and emptying the queue, although the style guide's Session controls rule says a
  logout always confirms first. It now opens a "Log out?" dialog that says playback stops and the
  queue is cleared -- and, in the app, that downloads stay on the device. Cancel, Escape or a tap
  beside the dialog changes nothing; confirming runs the existing sign-out unchanged (bug report
  106), once, however often the button is tapped. The dialog reuses `Modal.svelte`, which gains a
  `widthClass` prop and dialog semantics; the style guide now describes the Confirmation dialog.

### Fixed
- **A daily mix keeps going however it was started, and says when it is short** (issue #97, bug
  report 122). Tapping a track in a daily mix or the release radar, which is how the phone and the
  tablet start one, began a queue that forgot the feed. The queue stopped after the first 100 tracks
  instead of topping itself up; only the round play button carried the continuation. A tapped row
  now carries it too. The queue list (bottom sheet on the phone and the tablet, side panel on the
  desktop) now ends in "Meer laden" while the feed has more, so the next page can be loaded without
  waiting for the end. A feed page whose tracks the music server does not all have (for example
  files it has not scanned yet) says so in its header ("98 nummers • 2 niet gevonden op de server")
  instead of looking like a 98-track mix for no reason. Paging still follows MuMa's rows, so the
  gap never skips or repeats a track.

- The pre-deploy database backup can no longer be corrupted by a second writer. On 2026-09-27 a
  `DEPLOY_DB=1` deploy refused to continue because its dump did not decompress: Watchtower's hourly
  session had recreated the running `db-backup` container, which started a second dump in the same
  second as the deploy's fallback, into the same file. The backup run now opts out of Watchtower,
  a failed run's container is removed before the fallback starts (or the deploy is refused), a
  running nightly backup refuses the fallback, every writer's temporary file has a name of its own,
  and the nightly prune leaves a partial file alone until it is an hour old (bug report 123).

- **LMS keeps a listen until music-manager has it** (issue #67, bug report 075). LMS relayed each
  listen to music-manager with two back-to-back retries and nothing else. Any listen played while
  music-manager was down or starting up (every deploy) was lost, and so was whatever was still
  queued when LMS itself restarted. The relay now writes each listen to an outbox in `lms.db`
  (`muma_listen_outbox`, LMS database version 125) before sending it. It delivers from there in
  play order, one at a time, retrying after 5 s and backing off to once a minute, and removes a
  listen only once music-manager has taken it. A retry sends the same start time, so a listen
  that arrives twice is counted once. The outbox survives restarts. It is bounded at 10,000
  listens and 14 days, and it logs a WARNING for every listen it drops. Delivery runs on LMS's
  background threads with its own HTTP queue, never on a request thread or in the `/muma` proxy's
  queue. music-manager's `/health` now shows, per LMS, how many listens wait and since when
  (`lms_listen_outbox`); it never turns the check red. The 15-minute `lms-listen-backfill` loop
  stays as the safety net behind the outbox.

## [0.79.4] - 2026-09-27

### Fixed
- **LMS's scan summary says what its errors are, and folder scans stop re-reporting the same 967**
  (issue #95, bug report 121). Every scoped scan on production ended with `errors = 967`, even
  after reading two files. All 967 were playlists: scene releases' own `.m3u` files naming tracks
  the tagger has since renamed (439) or whose audio is gone (149), and releases already moved out of
  the import queue `EPs/__TODO` (49) -- 637 with every entry missing, plus 330 single
  missing entries that were counted but only logged at DEBUG. The playlist step walks the whole
  library, so each scoped scan re-reported all of them. A scoped scan now only reports playlist
  problems inside its own folders, playlists in `__TODO` never count, and the summary lists the
  count per kind (`errors = 967: 637 playlist-all-entries-missing, 330 playlist-entry-missing`).
  The library-wide scan still reports every broken playlist and every unreadable file, and its
  admin-page report still lists each one. Files that were simply removed are no longer logged as
  `[error] Error while checking file ...: No such file or directory` -- 92,000 lines in six hours
  that buried the real errors.

## [0.79.3] - 2026-09-27

### Fixed
- **LMS's library-wide scan can finish again, and MuMa's scan requests stop timing out** (issue
  #93, bug report 120). The tagger asked LMS for a library-wide scan after every round, every ~5
  minutes, and LMS answered each request by aborting the scan it was running -- on the request's
  own thread, so the request waited for the abort and often ran past its ten-second timeout
  (~50 "Failed to trigger LMS scan ... Read timed out" WARNINGs per 12 hours). A library-wide scan
  takes most of an hour, so none ever completed; on 2026-09-27 two in a row were aborted at 152k
  and 650k file checks. LMS now lets a plain library-wide request join a scan that is already
  running (or run right after a scoped one) and answers at once; only `fullScan`, `forceOptimize`
  and `compact` still start over. Authentication no longer waits behind a scanner write batch just
  to stamp a token's last use or a user's last login, which is what timed out the downloader's
  folder notifications (~43 per 12 hours). The tagger round no longer sends a library-wide
  request -- every folder it writes is already announced -- and "rerun parse" announces the track's
  folder instead. A request that fails is retried once, and then carried to the next one instead
  of dropped; an LMS outage is one WARNING, not one per request.

## [0.79.2] - 2026-09-27

### Fixed
- **The importer no longer tries to extract a video file in the import folder every cycle** (issue
  #90, bug report 119). The extract step handed every file at the root of the import folder to
  patool, whatever it was; two `.mp4` downloads left there produced two WARNINGs and an ERROR per
  file per cycle -- 218 and 109 per file in twelve hours on 2026-09-27. Only a file with an archive
  extension *and* the matching archive signature is extracted now. Anything else -- video, image,
  document, a loose track -- and any archive that cannot be extracted is left where it is, warned
  about once, recorded in `importer_conflicts` with a reason (`migrate_v46` adds the `reason` column
  and the `extractor` step), and skipped until the file changes or disappears. The fallback retries
  log at INFO. Nothing is moved or deleted. `GET /api/import-conflicts` returns the reason, and
  Beheer lists these files next to the folder conflicts as "Openstaande importproblemen".

- **28 m4a files no longer fail every hourly scan with "Data too long for column 'title'"** (issue
  #91, bug report 117). Their title, original title or display artist held one value repeated up to
  241 times (3,800+ characters) -- left behind by the m4a `ORIG` atom defect fixed in 0.72.2, where
  every retag added one more copy. The scanner now cuts a value longer than its column to the
  column's character length, stores the file, and queues it for the tagger; the new
  `CollapseRepeatedValuesRule` collapses a repeated title, original title or display artist back to
  one value (the longest for the original title, the most frequent for the others). About 1,900
  more titles carry the same repetition at a length that still fitted; the tagger's deep run
  (every file within 30 days) repairs them. A file whose scan keeps failing is now parked after three failures in a row until it
  changes or the service restarts, instead of logging one error per file per hour for good.

- **A WAV file's date is read as text again** (issue #92, bug report 118). The ID3 date frames hold
  mutagen `ID3TimeStamp` objects, which the WAV reader passed on as they were: every WAV with a date
  logged "Could not split date value ['2023']" (270 warnings in two hours on production) and kept
  the date as an object.

## [0.79.1] - 2026-09-27

### Fixed
- **A setting changed on one device no longer disappears when another device saves at the same
  moment** (issue #39, bug report 116). The account's settings blob could only be written whole, so
  the web player and the app each read it, changed their key and posted everything back -- and the
  second of two near-simultaneous saves wiped the first one's change. New
  `PATCH /api/users/{id}/settings/{app_id}` with `{"set": {...}, "remove": [...]}` changes only the
  named top-level keys, as a `SELECT ... FOR UPDATE` read-merge-write in one transaction, and
  answers the merged blob. The web player now sends only the keys it changed, without reading
  first. Additive: `POST` still replaces the whole blob for older app versions, and a new client
  falls back to it when a server answers the PATCH with 405. The music server's MuMa proxy now
  forwards PATCH too; before, it sent nothing and held the call for 30 s, and it now answers any
  verb it does not forward with an immediate 405.

## [0.79.0] - 2026-09-27

### Added
- **Presets keep the Soort** (issue #47). The preset builder has a Soort select in sets mode (All /
  Sets & mixes / Live sets / Podcasts), and "save as preset" from the sets view keeps the filter
  bar's Soort. The preset sends it to `getSongs` as `form`, and with one year that year becomes the
  filing year (a live set's performance year). Android Auto plays the same preset the same way.
  MuMa Voice's explanation names the Soort it heard.

### Fixed
- **Confirming a label proposal, renaming a podcast show, changing an artist's portrait, revoking a
  user's sessions and grouping song versions could stop half-way.** The music-manager database pool
  commits every statement on its own, and each of these wrote two or more statements in a row. A
  failure in between could leave a CAT-ID rule in force behind a proposal that still read as open, a
  renamed show whose old spelling was lost for good, a portrait flagged in the manager that the
  artist did not actually show, an api_key cleared while its refresh tokens stayed valid, or grouped
  song versions without a canonical that no later pass would ever repair. Each now runs in one
  transaction: all of it lands, or none of it does (bug report 115).

## [0.78.1] - 2026-09-26

### Fixed
- **Deleting a news source or a radio channel, or merging a podcast show, could stop half-way.**
  The music-manager database pool commits every statement on its own, and these three writes ran
  two or three statements in a row with nothing tying them together. A failure in between left a
  news source whose bulletin rows were gone while its recordings stayed on disk, a radio channel
  on air without its history, or a merged-away show still in the queue without any of its
  spellings. Each now runs in one transaction: all of it lands, or none of it does (bug report 113).

### Security
- **An artist image URL could still reach the internal network through DNS rebinding.** "Set
  image from URL" checked the host's addresses and then let `requests` resolve the name again, so
  a DNS server answering public for the check and `192.0.2.27` or `169.254.169.254` for the
  fetch got the download past it. The host is now resolved once, every address is checked
  (including CGNAT, Docker/LAN ranges and IPv6 forms that embed a private IPv4 address), and the
  connection goes to that checked address with the original name as `Host`, TLS server name and
  certificate name. Every redirect hop is checked the same way, at most three. The bulk portrait
  fetcher downloads provider image URLs through the same path, where it had no address check or
  size cap before. Bug report 114.

## [0.78.0] - 2026-09-26

### Added
- **Release Radar and the daily mixes held 30 tracks, often under an hour of music.** They now hold
  100 by default, and the length is a setting ("Feed length", Beheer -> Config -> Feeds, 10-200), so it
  can change without a release. Measured on production: five of the seven feeds reach 100 on their
  own, and a build of 100 costs the same as one of 30 (Release Radar 4.1 s both); only Middenin and
  Harder take about 22 s at 100, because they top up a few places from tracks of unknown hardness.
- **"Meer laden" at the end of a feed.** `GET /api/feeds/{slug}` takes `offset` and answers
  `next_offset`: the next page is the same day's feed built with more places, without any song
  already served, and it is stored so the same page asked twice holds the same tracks (at most 500
  per feed per day). The feed page shows a "Meer laden" button, and a queue started from a feed
  (the feed page or a Home card, web and app) tops itself up before it runs out. Both clients now
  resolve feed paths to songs in chunks of 100, the most LMS accepts per call.

## [0.77.2] - 2026-09-26

### Fixed
- **The daily artist mix picked artists it could not fill: 0 tracks for "unproven", 2 for
  "valhalla".** The draw never asked whether the artist had anything to play, and the 90-day window
  plus the unheard-or-loved pool left none of Teun's top ten artists with even 15 songs. On top of
  that the artist mix was capped at 3 tracks per artist, when every track in it has the same artist.
  Now one grouped query counts the playable songs of the whole top ten, and only an artist (or label)
  with at least 15 is drawn. The window widens to a year, then to all time, before the next name in
  the top ten gets a turn. If no name qualifies, the mix is empty for the day instead of holding a
  few tracks. The artist mix is no longer capped per artist (bug report 110).

- A long track or a label's festival mix album under `EPs/` is no longer filed under "Live sets"
  just because its title names a festival ("Radium - Decibel Dictature" matched Decibel Outdoor;
  "Defqon.1 2015 Mix 1" is the label's mix album, not a recording). In the label tree a festival
  now makes a live set only together with "live" or "DVD" in the title or folder, so the "Live at
  Reverze" DVD rips and live-registration releases stay live sets. The hourly form pass moves about
  310 files from live set to set after deploy (issue #76, bug report 109).

## [0.77.1] - 2026-09-26

### Fixed
- **Web: logging out marks the device as signed out.** The web UI's logout now waits at most five
  seconds for the Android shell's own sign-out and records a device-level `muma_signed_out` mark,
  so the shell's next boot shows the login page instead of signing back in from credentials the
  phone still holds; any successful sign-in lifts it. Inside the shell the login page offers a
  native "Sign in with Google" button (the Google Identity Services button stays browser-only), and
  a Google sign-in there hands the session to the phone like a password sign-in does. Browser
  behaviour is unchanged. Bug report 106.

- **The orphan relink runs in minutes, not hours.** The title-and-artist key queried the whole track table once per orphan, so a dry run over production's 81,879 fileless tracks took hours while holding the scanner lock. A bulk run now reads the candidates once. Bug report 107.

### Security
- **The password is no longer in every Subsonic URL.** The web player signed each stream, cover
  and API request as `u=<name>&p=<password>` -- the password in plain text, so in every access log,
  proxy log and browser history entry it passed. LMS accepts the salted `t=md5(token + salt)&s=salt`
  form, but only against the user's own *Subsonic token*, which a client had no way to get:
  `/muma/api/admin/subsonic-token` needs an administrator. New `GET /api/auth/subsonic-token`
  returns the caller's own token (the account the key resolves to, nothing in the request can name
  another), issuing one into LMS's `lms.db` when there is none and leaving an administrator-issued
  token as it is; the key check counts towards the login rate limit and the token is never logged.
  The web player now signs in through MuMa first (password in the POST body), fetches its token and
  signs every URL with it; the password is only the fallback while no token is known. LMS's `/muma`
  bridge accepts `u`/`t`/`s` too, checked like `/rest`, for the artist-image URLs. Bug report 103,
  closes GitLab issue #21.
## [0.77.0] - 2026-09-26

### Added
- `POST /api/scanner/purge-orphans` (admin only, `?dry_run=1` supported) deletes fileless track
  rows that nothing a user made points at: no listen, no rating, no work pin and no reviewed ml
  label. It works in batches of 1000 and takes the rows' link rows with them. Orphans that do have
  references are kept and listed on `GET /purge-orphans` for a person to decide. The operator
  script `scripts/prod/person/relink-orphans-by-filename.sh` backs everything up first, then runs
  the relink and then the purge (bug report 104).

### Fixed
- **LMS now refuses a second user whose login name differs only in case at the schema level.**
  Bug 074's fix stopped the code from creating one, but the `user` table had no index on
  `login_name` at all. Schema version 124 adds a unique index on `login_name COLLATE NOCASE`,
  the collation the login lookup uses, so it also serves that lookup. A database that still holds
  a case variant keeps starting: the index is skipped with an error naming the names, and retried
  on every start until they are merged. Production had no case variants on 2026-09-26 (12 users).

- **The hourly song-version sync, track-form push, release-date sync and feed rebuild summaries now reach the event log.** They log under `services.music_manager.*`, a namespace the event stream only accepted from WARNING, so their INFO lines existed only in `docker logs` and were lost at every deploy. The artist image fetcher, which logs per artist, stays at WARNING. Bug report 105.

- The orphan relink (`POST /api/scanner/relink-orphans`) now also matches on the file name. About
  50,000 fileless track rows from the first scan in May 2026 have the raw file name as their title
  and no artist or duration, so the metadata match could never find their successor. An orphan
  whose title is the file name (without extension) of exactly one track's file is now relinked to
  that track, and its listens and ratings move with it. A name that several tracks share is left
  alone. The totals, the event and `GET /relink-orphans` report how many rows each key relinked,
  and `?dry_run=1` counts without writing (bug report 104, issue #71).
## [0.76.2] - 2026-09-26

### Fixed
- **New and moved tracks reach their song within the hour, not days later.** The song-versions worker grouped at most 500 tracks per hourly pass, and on 2026-09-26 42,915 were waiting after a label-tree rescan and the regroup, so they were missing from everything that shows one version per song. A pass now keeps grouping in batches of 500 until nothing is left, for up to five minutes (`SONG_VERSION_TICK_BUDGET`). Bug report 101.
## [0.76.1] - 2026-09-26

### Fixed
- **The Versies page no longer lists 77,000 songs without a file as changed.** The first rescore under the new ranking (0.76.0) set the best version to "none" for every song none of whose tracks has a file any more, which is right, but flagged each of them for review and counted it: "79267 canonicals changed" where about 2,300 real changes exist. A song that loses its only playable version is now not a change to review, and migrate_v45 clears the flag on the songs it was set on. Bug report 100.
## [0.76.0] - 2026-09-26

### Added
- **Setting `prefer_lossless` (Beheer → Configuratie, "Song versions").** On by default: FLAC plays
  before MP3. Off: MP3 320 first, for when storage or bandwidth matters more. Changing it re-ranks
  every song within the hour, and the file LMS shows follows the same order.
- **Beheer → Curatie → Versies.** Every song with more than one version, searchable and sortable by
  number of versions or by recent change, with each version's source, format, bitrate, kind, path,
  rating and plays and which one plays. Pick another version as best, reset to automatic, or accept
  a choice the re-ranking changed; songs whose choice changed are flagged.

### Changed
- **Which version of a song plays is now decided by format first, then by the kind of edit.**
  The old order put "official release" first, and a release still waiting in `EPs/__TODO` has no
  label yet, so it counted as unofficial and lost to a SoundCloud or YouTube rip (549 songs on
  production, e.g. Hysta & RDØ – TOGETHER; 1,428 picked a worse format than a sibling). The new
  order: lossless over MP3 (or MP3 320 first when `prefer_lossless` is off), then pro edit > radio
  edit > edit > original > no marker > extended > instrumental > music video, then bitrate, then
  official release (anything under the label tree, including the import queue, counts), then the
  oldest. A pin still wins. Every song is re-ranked once after the deploy; the log says how many
  choices changed before it changes them (about 2,700 of 32,000 multi-version songs by a SQL
  estimate). Pinning a version now needs the `rules.manage` permission.

### Fixed
- **Three backend loop tests no longer fail at random and block releases.** The tests ended a
  loop by patching `time.sleep` with a finite `side_effect` list. The event writer thread paused
  between database retries with that same process-wide function, so a retry that landed inside
  the test used up its items and it died on `StopIteration`. The writer now pauses on an event of
  its own. `run_forever` and the tagger, scanner, events-retention, lms-db-sync and artist-image
  loops take a `stop` event, and the tests end them through it after an exact number of rounds.
  In unit tests the process-wide event service writes to memory, never to a database. Bug report
  099.

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
## [0.75.2] - 2026-09-26

### Fixed
- **A deploy no longer fills the production disk, and `DEPLOY_DB=1` backs the database up before
  it replaces it.** After a verified deploy, `scripts/ci/prune-prod-images.sh` removes images that
  no container uses. It keeps the three previous images of each repository for an `IMAGE_TAG`
  rollback, plus `:latest`/`:stable`/`:rc`. It never uses `docker rmi -f` and logs the free space
  before and after. On 2026-09-26 old images had filled the root disk to 95%. `deploy.sh` now
  refuses to start with less than 8 GB free (`DEPLOY_MIN_FREE_GB`). `DEPLOY_DB=1` recreates `db`
  after the verified pre-deploy dump rather than before it. `db` now runs
  `mariadb:13.0.2@sha256:...` with `MARIADB_AUTO_UPGRADE=1`, so the coming 12.3 -> 13.0 move runs
  `mariadb-upgrade`. The deploy waits for the real server over TCP, logs the upgrade and checks
  it before any migration. Renovate now keeps the MariaDB digest current. `docs/deployment.md` no
  longer offers an ssh tunnel for the read-only MCP, because the `muma-readonly@'192.0.2.1.%'`
  account cannot log in through one. Bug report 094.

- **Two quick taps on "next" in the app no longer leave the player flickering between two tracks.**
  On the phone the web player worked out the next track itself and pushed it to the native
  service as a new queue position. A second tap before the service had reported the first move
  queued a second push; the report of the first move then pointed the UI back at the first
  target, and that mirror went across as a request too -- so each settled move re-queued the other
  one, indefinitely. "Next" and "previous" are now intents the service carries out (N taps move N
  tracks, shuffle and repeat are the service's own), a UI write that follows a service report is
  never sent back, and a report from before the newest requested move is dropped. The same race
  also hit two tracks picked from the list in quick succession. Bug report 095.

- **The Release Radar and the daily mixes list a song once, and play its best version.** A feed
  treated every file as its own candidate, so two files of one song took two places (Deadly Guns -
  KOPPEN ROLLEN twice on the radar of 2026-09-26, one YouTube and one SoundCloud file of the same
  song), and "heard" was per file: a song heard in its official version made its 140 kbps rip rank
  as unheard, above it (ERABREAK - Elevate and four more). Every feed now collapses to one entry per
  song before ranking, plays the song's canonical even when only a rip fell inside the window,
  dates the song by its newest version, and counts a listen or a rating of any version as the
  song's. Bug report 096.
- **Search, favourites, shuffle, genre lists, radio channels and the phone home shelves show each
  song once.** The server's `search3` (with a query), `getStarred2`, `getRandomSongs`,
  `getSongsByGenre` and `getSongsByFilter` return only the canonical of a song (a song not grouped
  yet stays), a favourite version is listed as its song, and "Recent uitgebracht" / "Recent
  toegevoegd" ask for one row per song. Albums, playlists and the song page are unchanged. The row
  of a song shows the song's rating: the canonical's own, else the highest given to any version;
  clearing it clears every version, so unstarring from favourites works. Bug report 096.

- **A folder conflict in the import queue is warned about once, not every five minutes.** When the
  importer's renamer or mover cannot use a name because a folder holding a different release already
  has it, both folders stay in place as before, but the pair is now remembered in a new
  `importer_conflicts` table (`migrate_v43`): one WARNING the first time, an unchanged pair is not
  compared again, and each cycle ends with one `Standing folder conflicts` INFO line. A pair whose
  folder was removed or renamed is forgotten. On production 49 pairs produced ~490 WARNING events an
  hour. `GET /api/import-conflicts` and a read-only section under Beheer → Label proposals list what
  stands. Bug report 091.

- **Every song now has exactly one canonical row in LMS.** The song-version push marked canonical
  per file, so a canonical track with several files (the FLAC and the MP3 of one release) put every
  file in canonical-only lists -- 5,226 works were shown more than once -- and a work whose
  canonical file LMS does not have got no canonical row at all, so 1,081 songs vanished from
  canonical-only lists in the app and Android Auto. The push now decides per work: the canonical
  track's best file (the scanner's own media row, then format and bitrate, then the newest) is the
  only canonical row, and when LMS lacks that track the best version LMS does have stands in
  (counted in the hourly log). It reuses bug report 093's one-row-per-path rule and compares before
  writing, so an unchanged run writes nothing. Bug report 097.

- **The hourly track-form push into LMS converges.** 1,481 files had two `library_media_files` rows
  (the scanner's own and a stale one from July 2026 on a length-less stub track), and both were
  pushed, so LMS flipped ~1,700 files between `track` and empty every hour and took its write lock
  each time. The push now sends one row per path, the scanner's own first, and its UPDATE compares
  before writing, so an unchanged run issues no UPDATE at all. The scanner also re-reads a file
  whose row has no length even when mtime and size are unchanged, so ~38,000 files scanned in May
  2026 with only their file name as title get a length, a title and a form. Tracks without a file
  stay unclassified on purpose; the form pass now logs both counts. Bug report 093.
## [0.75.1] - 2026-09-25

### Fixed
- **The `__TODO` label repair answered 500 on production.** The music-manager image did not
  contain `services/importer`, whose label resolver the repair reuses. It is copied now, and a CI
  test fails whenever code in the container imports a package the image does not carry. See bug
  report 092.
## [0.75.0] - 2026-09-25

### Added
- **A name a tagger rule guessed no longer confirms itself on the next file.** The tagger matched
  titles against every name in `library_artists`, and the scanner records every artist it reads, so a
  guess was a trusted artist one scan later -- the loop that once put 9.188 tracks under `Premiere`.
  The artist rules now trust only approved names (by hand or by the external-evidence run) and the
  names that were already in the library before this release (`rules_artist_legacy_trust`, seeded
  once by `migrate_v40`). A new name is recorded, stays on the file it came from, and is listed in
  Artiestcuratie with a **Nieuw** badge (`state=pending`, `pending` in the summary) until it is
  decided. Measured on production: ~3.500 new names in 30 days, 20-35 on a quiet day, over a thousand
  after a mass retag.
- **A rejected artist is now also removed or corrected by CheckArtistRule.** It asked the artist list
  before the ignore list, and every rejected name that was ever on a file was in that list, so the
  rejection was skipped: 996 rejected names are still on 29.772 tracks. They change the next time
  each file is tagged.

- **Channels get a proposed label or artist.** Since 0.70.0 every SoundCloud and YouTube channel is
  its own row in the database, but none pointed at a label or an artist. Beheer -> Downloaders ->
  **Koppelingen** now compares every channel name with the known labels and the approved artists
  (case, accents and punctuation ignored; an alias or a redirect from artist curation counts too) and
  proposes only exact equality. Confirming records the link, rejecting does so for good. Measured on
  production: roughly 860 of the 1.376 channels get a proposal, 18 are skipped as ambiguous. The
  Volledigheid table shows the linked label or artist in a new "Gekoppeld aan" column, with a
  "voorstel" marker where one is still open. New table `channel_link_proposals` (`migrate_v41`), new
  endpoints under `/api/channel-links`; the coverage response gained an additive `channel` per account.
- **The Volledigheid table showed no last download for any SoundCloud channel.** The archive files a
  SoundCloud download under the numeric `soundcloud_id` (157.887 of 157.888 rows); the page looked it
  up by account name and never found it, so all 1.113 accounts read "onbekend". Now by id (bug
  report 089).

- **A repair for the SoundCloud files that lost their full date.**
  `python -m services.tagger.soundcloud_date_repair` (dry run by default, `--apply` to queue) finds
  the SoundCloud downloads since 0.72.0 whose file still carries only the year. It queues them for
  the tagger with reason `soundcloud_full_date`, and the tagger restores the date from the stored
  download info.
- **A new SoundCloud download that arrives with only the year now logs a WARNING.** The tagger
  repairs the date silently, so without this warning the defect from bug report 088 could come
  back unnoticed. The warning reaches the alerts topic and the nightly prod check.

- **Every track now has a form -- track, set, live set or podcast -- and a live set files under
  the year it was played.** Until now "what is this file" was only guessed from its folder or its
  length, so no filter could ask for live sets and leave the weekly radio shows out, and a Defqon.1
  2012 recording uploaded in 2016 filed under 2016. `library_tracks` gets `form` and
  `performance_date` (`migrate_v42_track_form.sql`, columns only), LMS gets the same two columns
  (migration step 122, database version 123). The form is derived from length (under ten minutes
  is always a track -- the short files under `Podcasts/` and `Top 100/` are countdown tracks), top
  folder (`Livesets`, `Telegram`, `Podcasts`) and the festival and podcast rules the tagger already
  uses (`services/common/track_form.py`); a live set whose festival and year have an edition date
  gets that date. The scanner writes both for every file it reads, and the hourly LMS sync
  recomputes the whole library first (writing only what changed -- this is the backfill, no
  deploy-time data migration) and then pushes both into each server. `getSpotifyTracks` and
  `getSongs` take `form` (unknown values are refused) and `year` now uses the performance date for
  live sets, in both LMS query builders (`find_advanced` and `find`); `/api/library/advanced` and
  the analytics take `form` and compare `year_min`/`year_max` against the same filing year. The
  sets view has a new **Soort** filter (Sets & mixes / Livesets / Podcasts), on the phone and in
  the browser. Design: `docs/designs/track-form/`.

### Changed
- The `services/music_manager/tests` router modules no longer stub `pymysql`, `dbutils`, `mutagen` or `markdown`: they run against the real libraries. The one test that leaned on the stubbed pool (`test_radio`'s permission check) now overrides the dependency the route actually uses. Test-only; no behaviour change.

### Fixed
- **MariaDB, LMS, Firefox and the rest of production now have a memory ceiling.** Only music-manager
  and the workers had one; on an 8 GB host a runaway LMS scan or a Firefox with full shared memory
  could drag MariaDB into the OOM killer. The limits come from `docker stats` on production
  (2026-09-25): `db` 2g (661 MiB used, 128 MiB buffer pool), `lms` 1536m (549 MiB), `firefox` 2g
  (626 MiB, above its 1 GB `shm_size`), phpMyAdmin 256m, the LMS proxy and autoheal 128m, the
  one-shots 1g and the backup jobs 512m, each overridable in the stack's `.env`. They apply when a
  container is recreated; for `db` that takes a `DEPLOY_DB=1` deploy. Bug report 086.
- **`scripts/dev.sh` starts its stack again.** The dev overlay named an LMS container that is not in
  that stack, and the overlays repeated `security_opt`, which compose 2.26 rejects as a duplicate --
  so neither the dev stack nor README's base + tools combination rendered.
  `tests/ci/test_compose_render.py` now renders every documented compose combination.

- **Files stamped `__TODO` as their record label can now be repaired, and the fixed tagger stops
  creating new ones.** GenericSong fell back to the publisher for a copyright, so a release waiting
  in the import queue still got `copyright = __TODO`; LabelSong kept an old `__TODO (2021)` copyright
  after filing. Both now empty the placeholder first. `GET|POST /api/tagger/todo-label-repair` pages
  the label tree (primary-key ranges, no join), counts poisoned files per label derived from their
  folder -- the importer's resolver for files still in the queue -- lists the undecidable ones, and
  queues the rest for the tagger under reason `todo_label_repair`. Bug report 087.
- **The import queue's location is one setting.** Every walker of the label tree asks one predicate
  (`ImportQueue`) instead of checking for `__TODO` or a leading underscore itself, and a CI test
  refuses a new hard-coded `__TODO`. Moving the queue out of `EPs/` is now `import_folder_path` plus
  a folder move; the tagger keeps tagging it as generic songs wherever it lives.
- **Crooked ` - ` import folder names get a rename tool.** `python -m
  services.importer.catid_prefix_repair` plans a catalogue-number prefix only where the number routes
  to a label in `rules_catid_label`, with a rename log and rollback. On production that is at most ~27
  of 2.613; the rest need a label decision.
## [0.74.3] - 2026-09-25

### Fixed
- **A tablet in landscape shows the search box and the profile button again.** The top bar chose
  between its phone and desktop version on `isMobile`, which is true on every touch screen, while
  the page layout switches at Tailwind's `md` breakpoint (768 px). From 768 px up a touch screen got
  the phone bar, which its own `md:hidden` then hid, and no desktop bar at all -- as did a desktop
  window between 768 and 1023 px. Present since 0.63.0, not caused by the colour-token rewrite in
  0.74.1; every token class was compiled and checked, and a test now keeps it that way. Bug report 090.
## [0.74.2] - 2026-09-25

### Fixed
- **SoundCloud downloads keep their full release date again.** Since 0.72.0 the cover-art step
  rewrote each mp3 as ID3v2.3, and ffmpeg cut yt-dlp's undelimited `upload_date` (`20260831`) down
  to the year on the way. The downloaders now hand FFmpegMetadata the date as `2026-08-31`, which
  survives that rewrite, and the tagger completes a year-only SoundCloud date from the stored download info
  when the years agree -- so a retag repairs the files already downloaded. Bug report 088.
## [0.74.1] - 2026-09-25

### Changed
- **The ml-analyzer is deprecated and disabled; its code is kept.** It never ran in production (its
  compose service was commented out), nobody has time to work on it, and it would not have worked
  if it ran: the already-analysed check compares a track id against a path hash, the ML label rows
  are keyed by path hash while every reader joins them by track uid (bug report 028's shape), and
  `predict.py` feeds the model 11 unscaled audio features where the trainer fitted 41 scaled ones, into a
  table no deployed database has. It is now out of `backend:unit` and the coverage figure (the
  total goes up, the floor is untouched), out of `./build.sh`'s build-all run, the dependency audit
  and Renovate, and commented out of `docker/docker-compose.full.yml` too. Its tests run only in
  the manual job `backend:ml-analyzer-unit`, and `tests/ci/test_ml_analyzer_deprecated.py` fails if
  any other job picks it up again. `library_track_audio_features` and `library_track_ml_labels`
  keep their data, so BPM, analytics and feeds keep showing what is there; new tracks get no
  analysis. `services/ml-analyzer/DEPRECATED.md` has the defects with file and line and the
  checklist for reviving it.

- **A disabled or deleted MuMa account no longer keeps streaming through LMS.** The user sync only
  ever created and updated LMS users, so an account disabled in MuMa kept its Subsonic key and every
  client holding it went on playing. The next sync now disables the LMS user (new `user.disabled`
  column, LMS migration step 121, database version 122) and revokes every auth token it holds, in
  every domain. The same happens to an LMS user whose MuMa account has gone from the list. The user
  is disabled, never deleted: listens, ratings, stars and playlists refer to it by id and stay where
  they are, ready for a re-enabled account. No credential lets a disabled user in -- token, salted
  token, password or proxy header -- including a token issued after the sync. An empty user list,
  or one with an unreadable id, disables nobody as deleted. `DELETE /api/users/{id}` now pokes the
  LMS sync after its commit, as enable and disable already did, so a deleted account is locked out
  at once instead of at the next sync.
- **One bad row no longer ends the LMS user sync.** A row without a username, or one whose write
  failed (two LMS users claiming the same MuMa id), ended the loop, and every account after it went
  unsynced until the next sync. Each account is now written in its own transaction: an unusable row
  is logged and skipped and the rest are applied.
- **The LMS fork is documented.** `services/music-management-server/FORK.md` records the upstream
  base (LMS v3.76.0, `d3eb168d7`; the `3.83.1` project version is the fork's own), the MuMa-specific
  subsystems, how upstream fixes are ported, and the database version policy: steps from 103 up are
  the fork's own sequence, and an upstream migration is ported under the next free step, never merged
  under its own number (upstream's 103-115 already mean something else here).
- **New C++ tests** for the MuMa listen and rating relays (payload, key header, how the send queue
  retries and drops them), the user sync, disabled-user authentication and the `/muma` routing
  helpers (allow-list, settings path, proxied URL and headers), now in `Routing.cpp`. A settings
  path whose user id is not a plain number (`12abc`) is a 400; it used to be read as user 12.

- **Test stubs no longer leak into every other test.** `services/tests/mock_base.py` used to replace
  mutagen, pymysql, yt-dlp, `config_store`, `Cache`, `DatabaseConnector` and more in `sys.modules`
  for the whole pytest session, so a test that needed the real module got a MagicMock, and MagicMock
  values reached real output (bug report 082's ntfy pushes). A test module now asks for exactly the
  stubs it relies on with `pytestmark = pytest.mark.mock_base(...)`; they exist only while that
  module is imported and its tests run, and everything imported under them leaves `sys.modules`
  again afterwards. 104 of 270 unit test modules declare stubs, the rest run against the real
  libraries. `tests/ci/test_mock_base_isolation.py` fails if a stub survives collection. The unit
  run is faster (about 160 s instead of 240 s) and coverage is unchanged. Bug report 085; the marker
  is documented in `CONTRIBUTING.md` and `AGENTS.md`.

- **Nine API routes that nothing in the repository calls are deprecated, and three redundant aliases are removed.**
  The deprecated routes are `GET /api/about`, the three `/api/rules/artist-redirects` routes,
  `POST /api/tagger/rescan/file`, `POST /api/songs/tracks/{id}/split`,
  `GET /api/downloaders/schedule/{source}`, `GET /api/users/permissions` and
  `POST /api/users/sync/lms-db`. They still work and are flagged `deprecated` in the OpenAPI
  schema. The first call to each one per process now logs an INFO event naming the caller, so any
  real use shows up in `/api/events`. Routes that stay unused are deleted on 2026-11-01. The
  removed aliases are `GET|PUT /api/users/{id}/lb-account` (use `/listenbrainz`),
  `POST /api/users/sync/lms` (use `/sync/muma-server`) and `POST /api/rating/server-event` (use
  `/lms-event`, which LMS calls). **Breaking** only for a client outside this repository that
  still calls one of those three aliases. `/api/listening/clock`, `/api/listening/sources`,
  `/api/curation/retag` and `/api/rating/ratings/{username}` were on the audit list but have a
  consumer and stay. See bug report 084.
- **Five identical genre-style name keys now share one implementation in
  `services/common/text_normalize.py`.** They are in `GenreRulesHelper`, `GenreNameAnalyzer`,
  `PodcastHelper`, `curation_rules`, plus the padded variant in `FestivalHelper`. The artist key
  in `ArtistNameAnalyzer` also moved there. A characterisation table pins every normalizer's
  output on the same tricky inputs, and none of it changed. The scrobble matcher, the artist image
  fetcher and `Tag.set` normalize differently on purpose and now say why.
  `scripts/restore_lms_ratings.py` imports `candidate_paths` instead of carrying a copy.

### Fixed
- **Every container's log is capped, not only the main stack's.** Docker keeps container logs
  without a size limit by default, and a full disk on the production host has already looked like
  a 502. Bug report 050 capped the services in `docker/docker-compose.yml`. The `lms` stack, the
  backup jobs, the CI test stack and the other compose files now get the same json-file rotation
  (10 MB x 3). LMS and its nginx front get 20 MB x 5, because they log every request. A CI test
  fails when a service in any compose file has no cap. The cap applies once a container is
  recreated, so `db` needs a `DEPLOY_DB=1` deploy to pick it up. Bug report 081.
- **Deploys check production's SSH host key.** Every deploy and verify script connected with
  `StrictHostKeyChecking=no`, after adding whatever `ssh-keyscan` returned to the runner's
  `known_hosts`. Together that accepted any key. The host's keys are now pinned in
  `scripts/ssh/known_hosts`, and a changed key fails the job with ssh's own message.
  `docs/deployment.md` explains how to update the pin after a reinstall.
- **The secondary compose files no longer publish MariaDB and phpMyAdmin on every interface or
  default the noVNC password to `admin`.** This is the same as `docker/docker-compose.yml` since
  bug report 050.

- **Rejecting or undoing an artist no longer leaves redirects pointing at it.** Rejecting a name
  with a correction now re-points every redirect that led to it; rejecting it outright or undoing
  it sends those redirects back to the curation queue. Both are listed in the reply. The tagger
  follows a redirect chain to its end (with a loop guard) instead of writing the middle name, the
  Tagger tab refuses a redirect to a rejected artist or one that closes a loop, and
  `GET /api/rules/artists/redirects/issues` reports dangling and looping redirects stored before
  this fix (bug report 080).
- **A cleared artist portrait now disappears everywhere.** The server sync takes back the artwork
  it gave the server for a cleared artist, and the fixed-URL copies (`primary.jpg`, `thumb_*.jpg`)
  are removed on clear and rewritten on selecting another stored image (bug report 080).

- **The web interface no longer mixes Dutch into English.** Error messages, confirmation dialogs,
  titles and the lock-screen fallback "Onbekend nummer" were typed into the components in Dutch and
  ignored the language setting; they now come from the locale files. Numbers and dates follow the
  chosen language instead of always being formatted Dutch (`1,234` in English, `1.234` in Dutch).
  A unit test fails if one of the moved phrases or a fixed `'nl-NL'` comes back (bug report 083).
- **Colour tokens instead of hex values in the web frontend.** Five greys the interface already
  used got a token (`muma-spotify-muted`, `-subtle`, `-raised`, `-hover`, `-highlight`) and about
  820 arbitrary colour classes were rewritten to tokens with the same value, so nothing changes on
  screen. The Save button on a genre page has a hover state again (`bg-opacity-*` compiles to
  nothing in Tailwind v4), and the search box no longer fetches the full genre and label lists
  again every time the layout switches between phone and desktop.

- **A rating set in one place of the web player now shows everywhere at once.** Bug report 078:
  the track list, the player bar, Now Playing, the details sheet and car mode each kept their own
  copy of "the rating I last set", so rating a track in one left the others on the old stars until
  a reload. All of them now read and write one shared store (`services/frontend/src/lib/ratings.js`):
  the new value shows at once, is rolled back with the usual "could not save your rating" message
  when LMS refuses it, and a late failure can no longer undo a newer tap. 1-5 stars as before, and
  clearing is its own call (`rating=0`, which LMS relays as `rating_removed`).
- **Tapping a radio channel twice, or a second channel while the first was still tuning in, no
  longer starts two streams.** Every start takes a ticket and only the newest one may touch the
  player once its await returns; a superseded radio controller can no longer load its stream over
  the newer one, or tear down the newer channel when its own start fails late.
- **Saving a long queue as a playlist, and pushing a long jam queue, no longer fail with 414 URI Too
  Long.** `createPlaylist` and `savePlayQueue` now carry their track ids in a form-encoded POST body
  (OpenSubsonic `formPost`, which LMS already accepts) instead of the query string; saving a
  playlist also reports a refusal inside a Subsonic 200 instead of calling it saved.
- **The player no longer writes its state to localStorage four times a second.** `playerState` is
  written at most every five seconds while playing, plus straight away on pause, when the page is
  hidden and on `pagehide`, so the last position still survives a reload.

- **Google sign-in accepts only a verified e-mail address, and a taken username is a 409.** Bug
  report 079. A Google ID token whose `email_verified` claim is not true is refused with 401: the
  address is what an admin reads when approving a request and becomes the new account's username.
  A rejected token's 401 no longer repeats the Google library's reason. Approving a request whose
  e-mail address is already a username (in any case) answers 409 with a hint to link the request to
  that account, instead of a 500.
- **Logins through LMS are rate limited per client again, and a forged `X-Forwarded-For` no longer
  picks a bucket.** LMS now passes the client address it resolved to MuMa, both on its password check
  for every Subsonic request and on a proxied `/muma/api/auth/login`; it sent none, so every login
  on `lms.<domain>` counted as the LMS container. MuMa believes that header only from a trusted
  network (`AUTH_TRUSTED_PROXIES`, default loopback and the private ranges) or a caller with the
  system key, and reads it from the right instead of taking the client-written left-most entry. A
  login now counts per client and account (10 a minute) and per account from anywhere
  (`AUTH_RATE_LIMIT_ACCOUNT_ATTEMPTS`, 50 a minute), so one device with a stale password no longer
  locks the account for everyone.

- **The unattended Claude runs on the runner host no longer run with permissions off.** The
  crash triage (which reads crash reports that app users write), the nightly prod check (which
  reads production logs) and the release that the approved-MR watcher starts all used the
  skip-permissions flag. A prompt injected into a crash report or a logged track title could
  therefore do anything the `triage` user can: use the production system key for writes, push
  to any branch, merge. All three now run with `--restricted --permission-mode dontAsk` and a
  per-job allowlist from `scripts/crash-triage/claude-permissions.sh`:
  - production only through one-purpose wrappers (GET, one status PATCH, one ntfy topic);
  - GitLab reads through a wrapper, and pushes only to the job's own branch prefix;
  - only the release run may merge, and then only a green release MR into master;
  - no curl, no `glab api`, and no local test runs (a test run is a shell).
  The units now run a root-owned copy in `/opt/crash-triage/bin`, so a run cannot edit the
  file that sets its own permissions. That copy has to be installed on the runner by hand. See
  bug report 077 and `scripts/crash-triage/README.md`. A CI test now fails when the flag
  appears anywhere outside the docs.
## [0.74.0] - 2026-09-25

### Added
- **MuMa now inserts, by itself, the listens LMS recorded but never passed on.** LMS forwards each
  listen once, retries twice in a row and then drops it, so every MuMa restart (every deploy)
  lost the listens made during it. On 2026-09-25 three of four morning listens went missing this
  way, and the reconcile counts 1,453 such listens overall. A new `lms-listen-backfill` loop reads
  the last 48 hours of LMS's own listen history every 15 minutes. It inserts each lost listen with
  source `lms-backfill` and LMS's start time. It uses the reconcile's rules: nothing within ten
  minutes of another listen by the same user, nothing from the last half hour, and it never moves
  an existing listen. Switch, interval and window are on Beheer > Config under "Scrobbling". The
  thread appears in `/health`. Older history remains a one-off `POST /api/scrobble/reconcile/lms`
  with `insert_lms_only` (bug report 075).

### Fixed
- **The release pipeline's secret scan no longer times out and skips the deploy.** Without an
  explicit range gitleaks scanned every ref in the runner's clone and ran past 30 minutes; branch
  pipelines now scan the history reachable from `HEAD` (about 20 s). `SECRET_SCAN_ALL_REFS=1`
  still scans every ref.
- **Listens from the app went missing, and LMS and MuMa disagreed about when they happened.** Bug
  report 071: of four listens LMS recorded on 2026-09-25, MuMa had one. The app's side is fixed in
  MuMa Mobile (a queue on the phone that keeps every listen until LMS confirms it); it now sends the
  play's start time as the Subsonic `time`, which LMS records and relays to MuMa unchanged, so a
  resend lands on the same `scrobble_listens` row and the reconcile pairs the two exactly. The three
  missing listens that morning had reached LMS and were dropped by its relay to MuMa, which gives up
  after two immediate retries; that part is not fixed here and is tracked in `docs/open-work.md`.

- **The event log no longer grows to tens of millions of rows.** On production the `events` table
  held 17.5 million rows (6.9 GB). Retention did run, but a 60-day WARNING window kept everything
  the importer wrote: about 380,000 WARNINGs a day since August, peaking at 821,000 on 2026-09-24.
  They were one warning per unplaceable folder per cycle, fixed separately in 0.73.1. Retention now
  keeps DEBUG 3 days, INFO 14, WARNING 30, ERROR 90 and CRITICAL 365, each configurable on the
  Beheer config page (group *Events*). It deletes at most 10k rows per statement by primary key
  and stops after 5 minutes, coming back after an hour instead of a day until the backlog is gone.
  A new size cap, `events_max_rows` (default 10 million), removes the oldest non-CRITICAL rows if
  the table is still too big. Each pass writes one summary line to the event log. The disk space
  InnoDB keeps after the clean-up is reclaimed by hand, see bug report 072 and
  `docs/deployment.md`, "Reclaiming space in the events table".

- **A login typed in another case no longer splits one person into two accounts.** After the
  0.73.1 key rotation the phone was signed in as "Teun" for the account "user". MuMa accepted
  it, because MariaDB compares names case-insensitively. LMS then looked the typed name up byte
  for byte, found nobody, and created a second user, id 13 `Teun`. Every play from the phone
  since 05:05 UTC went to that user (31 listens) and was relayed to MuMa as `Teun`, so the
  history was split for LMS and for everything that groups by name in Python. Account names are
  now case-insensitive everywhere. The login answers with the account's own spelling and every
  client signs in under it. LMS matches login names case-insensitively and never creates a user
  that differs only in case. Creating an account with a case variant of an existing name is a
  409. Scrobbles, ratings, feeds and the reconcile store and compare the canonical spelling. The
  existing fork is repaired by `scripts/prod/repair-username-case.sh`, which is run by hand. See
  bug report 074 and `docs/authentication.md`.

- **The LMS listen reconcile could insert one play twice.** LMS records a listen when playback
  starts; the app scrobbles to MuMa about a minute later (55 s on production). The check "is
  this the same play under another track, or unmatched?" used the 5-second pairing window, so it
  missed that listen. It now has its own 600-second window. Exact and shifted pairing are
  unchanged. The production dry run had called 254 LMS listens insertable under the old rule.
- **The reconcile treated `user` and `Teun` as two people.** Usernames are now compared without
  case. Every name is shown and inserted in MuMa's own spelling.
- **A stale `lms.db` without LMS tables is ignored everywhere, with a single warning.**
  Production's leftover `alpha/lms.db` (schema 114, no `user` table) made the song-version sync
  log "no version columns yet" every one to two minutes and retry as if a server were still
  migrating. `lms_db_targets()` now drops such a file for every consumer.

- **Running the tests no longer sends real phone notifications.** `config_store` loads the
  developer's `.env` at import time, so a local test run picked up the real `NOTIFY_URL`, and the
  artist-image router test pushed "Downloads failed: <MagicMock ...>" to the milestones topic. The
  root `conftest.py` now blanks `NOTIFY_URL` before anything imports the config store, and a CI
  test pins it. See bug report 082.

- **A full build cache on the workstation runner skipped a release deploy.** On 2026-09-25,
  124GB of BuildKit cache filled `/var/lib/docker` to 98%. The emulator in `mobile:smoke` then
  failed on "Not enough space to create userdata partition", so `muma:deploy` never ran. The disk
  janitor used to leave the build cache alone completely. It now prunes cache that has not been
  used for 72 hours, and cache unused for 24 hours if the disk is still at 85% or more. It never
  prunes without an age filter, so the `server:unit` ccache stays. `mobile:smoke` also checks free
  space before it starts the emulator (12GB by default). When there is not enough, it fails at once
  and says how to fix it (bug report 073).

- **YouTube's "Sign in to confirm you're not a bot" is now one warning, not an error per video.**
  Bug report 076: since 2026-09-24 the event log took about 20,000 ERROR events a day (26,721 in
  under two days), plus the same number of "No title found in player responses" warnings. 0.72.2
  did not cause the refusals. It made them visible, because it was the first release that passed
  yt-dlp's output to the event log. YouTube downloads had already stopped at about 2026-09-20
  02:40 UTC. The YouTube worker now counts these refusals across the sweep. After
  `bot_check_threshold` in a row (default 5) it stops, pauses YouTube for `bot_check_pause`
  (default 6 hours, both adjustable in Beheer > Downloaders) and logs one WARNING that says to log
  in again in the Firefox container. Beheer shows the pause together with that instruction. A
  missing or unreadable Firefox cookie database is now one clear ERROR at the start of a round,
  not a failure for every video. The worker also reads its cookies from a checkpointed copy of the
  profile, as SoundCloud already did, so it no longer misses the newest cookies Firefox has only
  written to its write-ahead log. The downloads themselves only return once someone logs in to
  YouTube again in the `muma-firefox` container (see `docs/open-work.md`).
## [0.73.2] - 2026-09-25

### Fixed
- **A deploy no longer hangs for an hour on a migration waiting for a table lock.** The 0.73.1
  deploy re-ran `migrate_v29`, a no-op `ALTER TABLE tagger_processed_files MODIFY COLUMN mtime DOUBLE`.
  It queued behind a five-hour diagnostic query and waited until the job timed out. While it
  waited, every tagger write to that table froze for three hours, and the retry's pre-deploy dump
  queued behind it too. Each migration now runs with a 120 s `lock_wait_timeout` through the new
  `tools/apply_migrations.py`. A blocked one errors, naming the file, prints the server's sessions
  so the lock holder is visible, and stops the deploy before any container is recreated. A new
  `schema_migrations` ledger records every applied file with its sha256, so an unchanged file is not
  run again (a changed one is). Migrations run in explicit byte-wise name order (`v10` before `v2`).
  The pre-deploy dump now stops after five minutes without output instead of hanging, and in that
  case the deploy does not start a second dump that would queue behind the same lock. See bug
  report 068 and `docs/deployment.md`, "When a deploy stops on a lock wait".

- **The LMS listen reconcile no longer fails on a stale LMS database.** On production every dry run
  answered 500 with `no such table: user`: besides the live `stable/lms.db`, music-manager also sees
  `alpha/lms.db`, a leftover at LMS schema 114 without a `user` table. A database that lacks one of
  the tables the listen query joins is now skipped with a warning naming the file, and the
  reconcile runs against the rest. See bug report 069.
## [0.73.1] - 2026-09-25

### Changed
- **Web UI: the label chip looked exactly like a genre chip.** `MetaChips` now colours a chip by
  its `kind`: a label is amber (`#ffcc80` on `#3a2c16`), genres, festivals and moods keep the
  neutral grey. Applies to the phone now-playing screen and the track details sheet, the two places
  that render label chips through `MetaChips`.

- **Image builds no longer pull whatever is newest on the day.** yt-dlp is pinned (2026.8.19) in
  `requirements.txt` and both images that install it, and Renovate bumps the three together in one
  MR, automerged when green: a new yt-dlp is now a merge request instead of an implicit rebuild.
  `muma:refresh-downloader` still ships it between releases, by installing the version pinned on
  develop. deno (v2.9.7) and the ffmpeg, Wt, stb and TagLib tarballs in the LMS image are pinned and
  checked against a sha256 after download; phpmyadmin, jlesage/firefox, autoheal, nginx and the
  Android SDK image are pinned to a version and a digest instead of `latest`. A new test fails on any
  unchecked download or floating image. How to bump: `docs/deployment.md`, "Pinned build inputs".
  See bug report 067.

- **Tagger: one database connection per worker and one rule stack per round, instead of per file.**
  Every helper the tagger calls per file used to open its own MariaDB connection (three to six per
  file at ~14 ms each), and every song rebuilt its whole rule stack, including two 37k-name artist
  sets and two uncached list queries for SoundCloud, Telegram and YouTube files. A round now lends
  each thread one connection for its duration and builds each song type's rules once; the artist
  names still follow the helper's snapshot, so tagging results are unchanged. Each round that tagged
  something logs one `Tagging round: ...` line with files, wall time, ms/file and connections opened.
  A single-file scan no longer reloads the genre rules before it knows it can get the scanner lock.
  See bug report 063.

### Fixed
- **MusicBrainz timeouts and failed portrait downloads still pushed an alert per artist during the
  artist-image run.** Bug report 058 fixed the Spotify path only: the MusicBrainz provider logged every
  timed-out attempt as a `WARNING`, image-download retries were `WARNING`s and a failed save an `ERROR`
  (logged twice), each one a push on the alerts topic. These are now `INFO` and counted into the run's
  single summary, which reports failed downloads and non-answers per provider. A MusicBrainz `429`, or
  a `503` with `Retry-After`, pauses the run the way a Spotify `429` does. The only `ERROR` left is an
  image directory that cannot be written, once per run. Bug report 060.

- **A write that replaced a set of rows could leave the set empty.** The database pool runs
  autocommit, so every "delete the old rows, insert the new ones" was two separate commits and the
  `conn.commit()` after it did nothing: a failure in between -- a festival alias longer than the
  column was enough -- left a genre without parents, a festival without aliases (but already
  renamed), a track without artist or genre links, or a rematched listen in both tables. Those
  writes, and the multi-statement account writes (approve/unapprove an access request, delete and
  merge a user), the song pin and split, now run in one explicit transaction via
  `database.transaction()`: all of it lands, or none of it. The scanner now always writes a file's
  links in one transaction, not only when the file moved to another track. Bug report 062.

- **Every router checks the API key through the one shared dependency.** Eleven routers carried a
  `verify_api_key` of their own -- once copies that answered a database outage with
  `401 Invalid API key`, lately thin wrappers where such a copy could return. They now all import
  `routers.users.verify_api_key`, and a test fails if a router defines one again. Answers are
  unchanged: unknown key `401`, disabled account `403`, outage `503`. The routers' own "no database
  connection" checks now answer `503` with `Retry-After` instead of `500`. Bug report 065.
- **A missing image-provider credential is reported once per process.** Every single-artist portrait
  fetch built a new fetcher, which logged the missing Spotify credentials and Last.fm key as
  `WARNING`s and "no configured image provider" as an `ERROR` again -- each one an alert push. They
  are now logged at full level once, then at `DEBUG`. Bug report 065.

- **A genre could be filed under its own subgenre, and the daily mixes then lost both.**
  `PUT /api/curation/genres/{name}/parents` only refused a genre as its own parent, so Hardcore
  under Uptempo under Hardcore was stored, and `deepest()` in the feeds dropped every genre in the
  loop. The write now answers `409` ("Hardcore is already an ancestor of Uptempo"), the edit page
  refuses a subgenre as a parent up front, the feed walkers keep one genre of a stored cycle (the
  alphabetically first) and log the cycle once per load, and
  `GET /api/curation/genre-hierarchy/cycles` lists any cycle already in the table so it can be
  fixed in Beheer (bug report 064).

- **The importer re-read the tags of every unplaceable `__TODO` folder after every restart, and
  logged a warning per folder every five minutes.** Since 0.73.0 the mover remembered a resolved
  folder only in process memory, so each deploy started the ~2,266-folder backlog over, reading
  every track over CIFS; and the `CAT ID ... not found` / `No valid CAT ID` warning was still
  logged for every one of those folders on every cycle, each one an event row. The proposal row
  now stores a fingerprint of the folder (entries, size, newest mtime), the catalogue-number rules
  and the row's own decision; while it matches, the folder is skipped without reading a tag or
  logging a warning. A changed folder, a new or edited `rules_catid_label` rule, or a decision on
  the proposal makes it resolve once more, exactly as before. Each cycle logs one line:
  `Unplaceable folders: N checked, N skipped as unchanged, N re-read`. New column
  `rules_label_proposals.resolved_fingerprint` (migrate_v38). Bug report 061.

- **LMS could read freed memory when a client hung up on a slow artist picture.** The `getCoverArt`
  proxy to MuMa kept a raw pointer to Wt's response continuation, and Wt frees that continuation
  when the client disconnects. If MuMa's answer or the 504 deadline landed after that, it went
  through the dangling pointer. The proxy now holds the continuation weakly and does nothing once it
  is gone. Normal completion still cancels the deadline. Bug report 066.

- **Web UI on a phone: the now-playing rating stars hung off the left edge.** The same full-screen
  player the app bundles (`NowPlaying.svelte`) now centres the rating row and shows an unrated
  track as grey outlined stars instead of a faded glyph that read as disabled. The desktop player
  bar is unchanged.
- **Web UI on a phone: the now-playing screen had no news button.** Only the desktop player bar
  rendered it; `NowPlaying.svelte` now has it next to the radio button, wired to the same
  `toggleNews` (bug report 059).
## [0.73.0] - 2026-09-24

### Added
- **Listen times destroyed by bug 039 can be restored from LMS.** Until migrate_v33 every update
  of a listen -- a rematch, a played-seconds top-up, an account merge -- moved its `listened_at` to
  the moment of that update. LMS's own `listen` table still has the real time of every play it
  relayed. `GET /api/scrobble/reconcile/lms` (admin) compares the two per user and track, joined by
  file path across the `/music` vs `/mnt/music` spellings, and reports `exact` / `shifted` /
  `muma_only` / `lms_only` with a sample; `POST` restores the shifted times (and, on request,
  inserts plays muma lost, as source `lms-reconcile`) in one transaction per user. Idempotent;
  ListenBrainz imports are never touched.

### Fixed
- **A Spotify rate limit during the artist-image run pushed an alert every five minutes for the whole
  run.** Spotify answered `429` on about 40% of the lookups, and the fetcher logged each one as a
  `WARNING` and went straight on to the next artist, which kept the limit tripped: 3,278 warnings on
  2026-09-24, 1,650 in one hour. The Spotify provider now reads `Retry-After` (default 30 s, capped at
  10 minutes) on the lookup and the token endpoint, and the fetcher pauses the whole run for that long
  and asks about the same artist once more before deferring it. Per-artist non-answers are `INFO`; a
  run logs at most two `WARNING`s, the first rate limit and a closing summary (artists deferred,
  pauses, total pause time). Bug report 058.

- **Een tik op een genre of label in de speler kwam nergens uit.** De speler sloot met
  `history.back()`, maar die komt pas later aan; de navigatie ging eerst, en de late `popstate`
  zette daarna de pagina onder de speler terug. `closeNowPlaying()` geeft nu een promise die pas
  na die `popstate` afloopt, en de speler navigeert daarna. Geldt ook voor album, artiest en de
  rijen onder "Hierna".
- **Bij veel informatie verdween de bediening van de speler onder de navigatiebalk.** Het
  schermvullende scherm is nu één schermhoogte: alleen de hoes krimpt mee, titel, artiesten,
  albumregel, genres, sterren, voortgang en knoppen staan altijd in beeld. Genres en labels staan
  op één rij die zijwaarts scrollt, de datum staat rechts naast het album, meerdere artiesten
  blijven op één regel. Liggend (tablet, gedraaide telefoon) staan hoes en bediening naast elkaar;
  voorheen was de hoes op een liggende tablet hoger dan het scherm en zag je geen enkele knop.
- **Artiesten stonden zonder spatie achter de komma ("Catscan,Starving Insect").** Svelte haalde
  de spatie weg uit `, ` binnen een `{#if}`. Overal waar `ArtistList` artiesten toont.
- **De nummerlijst op een tablet schoof titel, artiest en album over elkaar.** De kolommen gingen
  aan op de breedte van het scherm, terwijl de zijbalk daar een kwart van inneemt: bij ~500px
  tabel bleef er ~65px over voor de titel. Kolommen verschijnen nu op de breedte van de tabel
  zelf, cellen kappen af in plaats van over elkaar heen te lopen, de datum breekt niet meer af en
  aanraakschermen hebben geen lege beoordelingskolom meer. De status- en navigatiebalk van een
  tablet liggen niet meer over het logo en de spelerbalk.

### Security
- **The web login hands each user their own MuMa key instead of LMS's shared `api-key`.** LMS
  answered `/muma/api/auth/login` itself and returned its own configured `api-key` to every user --
  on production possibly MuMa's system key, which MuMa treats as an always-allowed superuser and the
  web app showed as an administrator for whoever held it. The route is now MuMa's own login: nginx
  sends it to `music-manager` directly (and LMS, when reached without nginx, passes it through), so
  the answer is `{api_key, refresh_token, user: {permissions, role_name, is_admin, ...}}` for that
  user. **Contract change:** a client that read LMS's flat `{id, username, display_name, is_admin,
  api_key}` gets MuMa's shape instead; the web player is updated in the same change and MuMa Mobile
  already used MuMa's login. **Every web user signs in once more:** a browser still holding the
  shared key finds it verified as a system key at startup, and the session ends instead of counting
  as an administrator. On the direct route nginx forwards the client as one `X-Forwarded-For`
  address (the right-most one not written by a private-network proxy), so the login rate limit
  cannot be reset by a forged address in front of the chain.
## [0.72.3] - 2026-09-24

### Removed
- **`trigger_fetch` in the artist-images router is gone.** Since the image endpoint stopped
  scheduling a lookup on a miss, nothing but its own tests called it; the per-artist fetch that
  remains is `trigger_fetch_by_id` behind `/fetch-image`. `coverage-muma-server.xml` is no longer
  tracked either: `scripts/test/muma-server-unit.sh` writes it on every run and `server:unit`
  uploads it from there.

### Fixed
- **A file the tagger could not read was retried every five minutes, forever, with an alert each
  time.** A failed file kept its place on the retag queue, was handed out again on the next round and
  logged another `ERROR` — and every `ERROR` is an event and an alert push. Failures now back off
  (10, 20, 40, 80 minutes) and the fifth in a row parks the file with reason `failed` until it changes
  on disk or a retag is requested: one `WARNING` for the first failure, one for the park, `INFO` in
  between, no `ERROR`. `GET /api/tagger/retag/pending` reports the parked files as `failed`, outside
  `total`, and the tagger page shows the count. New columns `attempts`/`last_attempt` (migrate_v37).
  Bug report 051.
- **Two files whose paths differed only in case, an accent or an emoji shared one row in the
  tagger's table** (`tagger_processed_files.filepath` was `utf8mb4_general_ci`), so one of the pair
  was retagged on every walk and each overwrote the other's mtime. The column is `utf8mb4_bin` now;
  migrate_v37 queues the rows that stood for two files (reason `binary_path`) before it changes the
  collation, and the tagger picks up the twin as a new file. The tagger's folder walk now skips hidden
  folders, as the scanner already did.
- **One 403 during a multi-threaded sweep climbed the backoff ladder once per worker thread and sent
  a push per thread.** `park()` now counts the first refusal of a sweep only and hands the others the
  same answer. A backoff reset from the management page during a sweep is no longer undone when the
  sweep finishes.
- **Redownload could fetch the wrong track, and on YouTube did nothing.** The source was looked up
  with `LIKE '%<name>%' LIMIT 1` (so `Intro.mp3` matched `DJ Intro.mp3`, and `_` matched anything);
  it is now the exact stored path, then the exact file name in the same folder, and a name that
  matches several downloads is a `409` instead of a guess. YouTube ran with `nooverwrites`, so yt-dlp
  reported the file as already downloaded and kept it. Both downloaders now overwrite on a
  redownload, into a staging folder beside the file that is moved over the old one only once it is
  complete: a failed redownload leaves the old file where it was.

### Security
- **The last admin could demote or disable itself.** Only `DELETE /api/users/{id}` refused to remove
  the last admin, and it counted disabled admins as spares. `PUT /api/users/{id}/role` and
  `POST /api/users/{id}/disable` now share its check, which counts only *other enabled* admins, and
  all three answer `409` (delete answered `400`). Bug report 052.
- **Two simultaneous first-time setups could create two admins.** `POST /api/auth/setup` counted the
  users and then inserted without a lock. The check and the insert now run under a lock and the
  `INSERT` itself refuses a non-empty table; the loser gets `409 Setup already completed` (was `400`).
- **Login timing told whether a username existed.** An unknown username was answered before bcrypt
  ran -- milliseconds against a quarter second. It now pays for one bcrypt check against a dummy
  hash and gets the same text as a wrong password; "Account disabled" only follows a correct password.
- **A database outage read as "Invalid API key".** The `library` and `scrobbler` routers kept their
  own key check, which swallowed every exception into a `401`. They now delegate to
  `users.verify_api_key`, and `verify_token` answers `503` when the users table cannot be read
  (before: `403 Invalid API Key` without a pool, `500` on a connection error). A key no account
  holds is `401` on every router (it was `403` on all but `library` and `scrobbler` since 0.72.2;
  the access-control feature requires `401`); a disabled account is `403` everywhere.
- **Any account could scrobble into another account's history.** `POST /api/scrobble/event` took
  the body's `username` at its word for every key. A user key may now only name itself (`403`
  otherwise); admins and the system key, which LMS uses, still name anyone.
- **`user_refresh_tokens` grew without bound.** Every successful login -- including every LMS
  Subsonic password check it has not cached -- inserted a row that was never removed. Each account
  now keeps its 10 newest, pruned on issue, and the daily `events-retention` pass applies the same
  cap everywhere and drops revoked rows older than 30 days.

- **The nightly production check no longer runs Claude with every permission switched off.** It
  judged a report built from production logs and crash reports -- text anyone who can make prod log
  a line can partly write -- under `--dangerously-skip-permissions`, so the skill's "only GET against
  prod, never merge" was a request, not a limit. `scripts/nightly-prod-check/run.sh` now starts it
  with `--permission-mode dontAsk` (not allowed means denied, never asked) and an explicit
  allowlist: edits only in the fix worktrees and the result file, production only through the new
  `prod-get.sh` (a GET of `/api/...` or `/health`, curl itself denied), `git push` only to
  `nightly-fix/*`, and `glab mr create/view/list` only -- merge, approve, `glab api`, force pushes,
  pushes to `master`/`develop`/`release/*`, ntfy and MCP servers are denied. Pinned by
  `tests/ci/test_nightly_prod_check_permissions.py`.

## [0.72.2] - 2026-09-24

### Changed
- **Every user route existed twice.** The users router was mounted at `/api/users` and again at
  `/api` (to reach `/api/auth/*`), so `DELETE /api/{user_id}` and every other user route answered under the
  bare prefix too. The session endpoints (`/api/auth/*`) and `GET /api/roles`, which the web
  player's Beheer page calls there, are now a router of their own at `/api`; everything else is under
  `/api/users` only. No client used the duplicates. `/api/users/auth/*`, which
  `docs/api-specification.md` documented and no client called, no longer exists.
- **The analytics, config, feeds, stats and listening routers check a key through the one
  `users.verify_api_key`**, as scanner already does (management and rating follow in !916). A user key no account
  holds, or a disabled account, now gets that function's 403 there instead of a local copy's 401;
  a missing key is still a 401. The web player treats both the same.
- **`docker/docker-compose.workers.yml` is marked local-only** (`scripts/dev.sh` layers it on top;
  production never reads it), and `run_telegram_auth.sh` points at `docker/docker-compose.yml`
  instead of a `work-context/` file that no longer exists.

- **The test gates now measure what they claim.** Python coverage is measured on source only — the
  ~220 test files under `services/` used to count as covered code, and `tools/` was not measured —
  which moves the figure from 95% to 84.9% and the floor from 93 to 84; the only time that floor
  has gone down. `backend:integration` fails instead of skipping when CI cannot reach its database,
  and runs MariaDB 13.0 like production (`MARIADB_VERSION=10.6` still reproduces bug report 039).
  The loose mypy floor runs in a new `backend:typecheck-all` job (allowed to fail while its 299
  errors are worked down), and `scripts/lint.sh` now fails an undocumented public function or class
  in a strictly type-checked module. Bug report 047.

- **The importer sends one phone notification per release instead of one per file.** A 44-release
  weekly pack used to be well over a hundred pushes. Each release now gets one `Import Complete`
  push with its label, catalogue number and track count. Every imported track is still in the event
  log as an `INFO` event (`Track Imported`), just without a push.

### Removed
- **Dead code removed.** `services/other/` (an artist fixer, converter, EPs flattener that
  duplicated `services/importer/flattener.py`, file repair, sanitizer and an unimportable
  `yt-fixer.py`, 461 lines that only their own tests imported) and its tests;
  `services/tagger/run_tagger.py`; `VerifyArtistRule`, reachable only through `services/other`;
  seven one-off tools (`check_media`, `finalize_genres`, `init_remote_db`, `list_imports`,
  `replace_table_names`, `repro_mutagen`, `migrate_db_renames`); the frontend's Vite template
  leftovers (`Counter.svelte`, `hero.png`, `svelte.svg`, `vite.svg`); the unused
  `subsonic/VideoPlayer.kt`; and an empty `ultrasonic-database.db` committed into the Android tree.
- **The `/api/jobs` registry and its WebSocket are gone.** Nothing read them: the downloader and
  importer side only pushed when `HUB_API_URL` was set, which no deployment did, and the WebSocket
  took no key. The curation pages' own job progress (artist and genre analysis, a rule's retag) now
  lives in `services/music_manager/job_store.py`, which keeps the last 50 finished jobs instead of
  every job for the life of the process.

### Fixed
- **A bulk artist-image run went blind after an hour.** The Spotify token was fetched once and
  kept forever; client-credentials tokens expire after 3600 s, so every lookup after the first
  hour answered 401 and the rest of a ~45.000-artist run was deferred. The token is now renewed
  before it expires, and a 401 renews it and retries once. (Bug report 043.)
- **Clearing a portrait in the manager was undone at the next restart.** The clear set
  `image_status = 'none'`, which the start-up run treats as "never asked". It now sets `cleared`,
  which the bulk run and a plain `/fetch-image` skip; "search automatically" in the manager sends
  `force=true` and still reaches it.
- **One failed download marked an artist `failed` for 30 days.** A provider had found the artist;
  the CDN or the disk had not cooperated. A failed download or save now records nothing and the
  artist is asked again next run, and the downloader pauses 1 s, then 2 s, between attempts.
- **Last.fm's placeholder was taken for a portrait.** `artist.getinfo` returns the same grey star
  for every artist, and with an MBID it scored as a known match. It is skipped now.
- **`manifest.json` in the artist-image folder is no longer maintained.** It was rewritten in full
  after every artist and nothing read it. Existing files are left on disk.
- **The config store's file beat every deploy.** `data/config.json` held a snapshot of every value,
  secrets from the environment included, and was loaded after the environment. Now only values
  changed through the config page are written (mode 0600), a value set back to its environment value
  is removed from the file, and an existing file is cleaned up at start-up -- a secret the
  environment also sets is left to the environment. The `db_*` fields, which nothing read through
  the store, are shown read-only. The radio scheduler now resolves the LMS Subsonic key the way the
  scan trigger does.
- **LMS errors no longer leak the Subsonic key or flood the alerts.** The key travels in the query
  string, and requests' error text carries the full URL; the radio logged it at WARNING -- an event
  and an ntfy alert -- per channel every five seconds while LMS was down. Query strings are now
  redacted, and the radio warns once per channel per outage.

- **One MariaDB restart or CIFS hiccup stopped the tagger or the scanner until the next deploy.**
  Their loops had nothing around the loop body, and the radio, news and feeds loops took their
  connection outside their `try`. Every background loop now runs through one helper that logs the
  failure as an `ERROR` event, backs off (10 s, doubling up to the loop's interval) and carries on.
  Each loop also records a heartbeat, and `/health` answers 503 when a loop is alive but has not
  completed a round within its window (24 h tagger, 12 h scanner, 3 h news, otherwise three
  intervals and at least an hour); the new `heartbeats` field shows the detail.
- **`/health` said `database: ok` while MariaDB was down, and hung when the pool was exhausted.**
  It now runs `SELECT 1` on its own connection with short timeouts and answers within about two
  seconds. The connection pool no longer waits forever: after 5 s (`DB_POOL_WAIT_SECONDS`) a request
  gets a 503 instead of hanging.
- **During a database outage an alert push waited ~21 s per queued event before reaching the
  phone.** The event log's database write now runs on its own thread, so pushes go out immediately
  and only the rows are late. The 5-minute repeat brake still applies.

- **A deploy started the new code before its migrations, with no backup and no way back.**
  `scripts/deploy.sh` recreated every container first — MariaDB included, with `--force-recreate`
  — and migrated afterwards, and `release:build-images` had already pushed `:latest`, which
  Watchtower on the host pulls for the downloader images, so a release's workers could start before
  `muma:deploy` had migrated anything, or without any deploy at all when it was skipped. The order
  is now: database up and answering, a verified pre-deploy dump (`tools/db_backup.py` with
  `BACKUP_LABEL=pre-deploy`, else `mariadb-dump` through `docker exec`; no dump, no deploy),
  migrations while the previous release still runs, `:latest` moved from `:${VERSION}` inside
  `muma:deploy`, then `pull` + `up` of only what changed. `db` is no longer recreated on a routine
  deploy (`DEPLOY_DB=1` does), the one-shot `soundcloud-fetcher`/`genre-processor` no longer run on
  every deploy (`DEPLOY_ONESHOTS=1`), and every image this repo builds is
  `${IMAGE_TAG:-latest}`, so `IMAGE_TAG=<previous> ./scripts/deploy.sh` is a rollback. New
  migrations must be expand-only (`tests/ci/test_migration_ordering.py`). See bug report 050.
- **The post-deploy check could pass while a container was crash-looping.** It sampled once, right
  after `up`. music-manager now has a healthcheck on `/health`, every worker a light one (Python
  runs, MariaDB reachable), and `post-deploy-verify.sh` probes LMS's Subsonic ping and re-samples
  after 60 s, failing on any restart-count increase or unhealthy container.
- **CI tested on Python 3.11 against whatever the runner had installed; production runs 3.14.**
  `backend:unit` and `backend:integration` now run inside `docker/Dockerfile.python-ci`
  (python:3.14-slim) with `requirements.txt` installed, and the lint jobs always use their 3.14
  container. That run found `httpx2` missing from `requirements.txt` and a numpy stub that broke
  every property-based test; both are fixed.
- **Changed production defaults (need a human on the first deploy).** MariaDB `3306` and phpMyAdmin
  `8002` bind to `127.0.0.1` unless `DB_BIND_ADDRESS`/`PHPMYADMIN_BIND_ADDRESS` are set (the database
  binding only changes on a `DEPLOY_DB=1` deploy; phpMyAdmin's on the next one). The Firefox noVNC
  password lost its `admin` default and `FIREFOX_PASSWORD` is now required in `PROD_ENV_FILE` by
  `release:check-secrets`. Every service's log is capped at 3 × 10 MB, and music-manager (4g) and
  the workers (2g, telegram 1g) have memory limits, overridable per `MUMA_MEM_LIMIT_*`.

- **YouTube never backed off when YouTube refused it, and its download errors never reached the
  event log.** yt-dlp ran with `ignoreerrors` and no logger, so it wrote a 403 or 429 to stderr and
  returned normally. The code that parks the source only ran on an exception, so it never ran.
  YouTube now uses the same yt-dlp logger as SoundCloud. It parks on a 429 and on a 403 that yt-dlp
  gave up on, and every error goes through the event log. (bug report 040)
- **A deep sweep that was refused counted as finished.** The listing came back empty, so the account
  was marked deep-swept for another month. A refused listing now feeds the backoff and leaves the
  account due. Any other listing failure falls back to the ordinary check.
- **A deploy now stops the downloader and importer cleanly.** A download in progress is abandoned
  instead of continuing to the next video until SIGKILL. The pause between rounds wakes up on
  SIGTERM, and the importer handles SIGTERM between its steps.
- **Telegram no longer trusts the sender's filename.** Only the base name is used, with the message
  id added, so two posts with the same name no longer overwrite each other and nothing can be
  written outside the channel folder. Files are downloaded to `.part` and renamed when complete.
- **Downloading a single YouTube video no longer follows its whole channel.** Every archived video
  used to add its uploader to the followed channels, which created duplicates when the same channel
  was spelled differently.
- Removed two yt-dlp options that did nothing because of a typo (`no_part` and `playlist_random`).

- **A daily mix that came out empty stayed empty for the rest of the day.** A listener who opened
  Home before their first listen got `not_enough_data`, and that answer was cached as the day's
  mix. A mix that is not `ok` now lives 15 minutes (`FEEDS_NON_OK_TTL_SECONDS`) and is rebuilt
  after that, on the next read or by the background refresh. A curator's hardness edit and a
  listener's exclusion change now also reach the mixes on the next read, including when a build
  was already running, and the mixes roll over at local midnight (`MUMA_TIMEZONE`, default
  `Europe/Amsterdam`) instead of at 01:00 or 02:00. See
  `docs/bug-reports/049-empty-daily-mix-stays-empty-all-day.md`.

- **Logging out of the web player left the previous user's session behind.** The queue, current
  track, player state, equalizer, page size and every account setting survived a logout, so the
  next person to sign in on that browser started in the previous person's session. Logout now
  resets everything the web player persists (bug report 041).
- **Changing two settings at once could lose one, and a failed read could wipe them all.** Each
  setting did its own read-modify-write of the shared account blob, and a failed read wrote back a
  blob holding only the one changed key. Changes are now batched into one read and one write, and
  nothing is written after a failed read.
- **An expired password looked like an empty library.** Failed Subsonic answers and MuMa error
  responses were treated as data (and the feed list cached an error as "no feeds" for the whole
  session). They now surface as errors; a rejected password returns to the login page.
- **Sets mode stayed green** once the management pages had loaded: two components overrode the
  brand colour app-wide. Removed, and a test guards against it.
- **Going from one artist or album straight to another could show the previous one's details**,
  and the scrobble-import poll kept running after leaving its tab.

- **Genres went through the artist splitter, so 'Drum & Bass' became 'Drum' and 'Bass'.**
  `CleanTagsRule` and `ResolveGenreRule` both ran `ARTIST_REGEX` over the genre tag, which splits on
  ` & `, ` and `, ` x `, ` with `, `: `, ` vs ` and ` et `. A curated genre with any of those in its
  name could never match its own row, 'Hardcore: Uptempo' became two genres, and a YouTube category
  such as 'Film & Animation' dodged its blacklist entry. Genres are now split on ';' and '/' only.
  The unused `MergeDrumAndBassGenresRule` (meant to repair exactly this, wired to nothing and calling
  a method that does not exist) and `InferGenreFromTitleRule` (no callers) are gone. Files tagged
  before this keep the halves on disk. Bug report 045.

- **A fresh database and production's disagreed about the schema, and no test compared them.** A
  new integration test builds the schema twice from nothing — once the way a fresh stack does
  (`db_init.py` plus every `init_db`), once the way a deploy does (the migrations) — and compares
  every column and index. On develop it found `library_artist_aliases`, which the artist edit page
  reads, missing from every fresh stack, three portrait columns no migration declared, and seven
  indexes that were missing or named differently on one of the two paths. `migrate_v36_schema_drift.sql` also gives
  `rules_ignored_artists.name` the unique key production already has (removing duplicates first),
  drops five audio-feature columns only fresh stacks ever had and nothing reads or writes, and
  declares three indexes that existed only in `db_init.py`. Bug report 047.

- **A half-extracted archive could land in the library.** Every backend extracted straight into the
  import folder, so when `unrar-free` gave up after 13 of 44 releases, those 13 stayed there and the
  fallback extracted the rest on top of them (7z renamed each collision to `name_1.mp3`). The same
  cycle then moved whatever was there. Each attempt now extracts into its own staging folder, and
  only a complete extraction reaches the import folder. (bug report 046)
- **A release still being copied into `__TODO` could be renamed or moved half-done.** The
  flattener, renamer and mover now leave a folder alone until nothing in it has changed for
  `import_settle_minutes` (new setting, default 5).
- **A second download of a release already in the library stayed in `__TODO` for ever.** The
  duplicate check compared byte sizes, and the library copy gets new tags right after the move, so
  the two never matched. The mover logged "contents differ ... manual intervention" about it on
  every cycle. Releases are now compared by track list and track length.
- **Every import cycle read the tags of every folder it could not place again**, over CIFS: about
  2.266 folders every five minutes. A folder is now read again only when something in it changed.
- **Split RAR sets failed on every cycle.** Only the first volume is extracted now, and the other
  volumes are quarantined together with it.
- **A full backup disk never recovered.** Old dumps were only pruned after a successful dump, and a
  dump that ran out of space left its half-written file behind. The job now prunes first (never the
  newest daily), refuses to start when the last dump would not fit, and removes a partial file
  whatever went wrong. The monthly copy is streamed and verified instead of being read into memory,
  and `latest.json` can no longer be left half-written.
- `scripts/restore_db.sh` and `tools/backup_db.sh` no longer put the database password on a
  command line.

- **Every scrobble-rematch miss moved the listen to "now".** Both scrobble tables were created on
  MariaDB 10.6 with `listened_at TIMESTAMP NOT NULL` and no DEFAULT, which that server turns into
  `ON UPDATE CURRENT_TIMESTAMP`. Each miss stamp, played_secs top-up, re-match and account merge
  therefore rewrote when the listen happened; two misses of the same track in one second collided on
  the unique key, which is the `1062 Duplicate entry ... for key 'username'` seen after 0.23.0 — not
  the key truncation `docs/open-work.md` suspected. `listened_at` now declares its DEFAULT, and
  `migrate_v33_listened_at_no_on_update.sql` removes the attribute from the existing tables. Values
  already rewritten are not repaired; bug report 039 says how to count them.
- **Two join columns were never indexed.** `library_tracks.primary_artist_id` (every rematch tier,
  the artist statistics and the feeds join on it) and `scrobble_listens.track_id` — which
  `migrate_v20` claimed already had an index. `migrate_v34` adds `idx_tracks_primary_artist` and
  `idx_listens_track_user (track_id, username)`.

- **Clearing a rating now clears it in MuMa too.** The server deleted its rating row and then
  reported the change by the id of the row it had just deleted, so nothing was ever sent and MuMa
  kept the old star forever. It now sends a `rating_removed` event (rating 0), captured before the
  row goes, and `POST /api/rating/lms-event` deletes the mirrored row on it -- and on a
  `rating_changed` of 0, which no star count means. A cross-app contract change: an older MuMa
  ignores `rating_removed`, so both sides ship together.
- **Deduplicated track pages no longer skip tracks.** `nextOffset` advanced past every row the last
  scan fetched, including the rows after the page had filled, so those tracks never appeared on
  any page. It now counts only the rows actually used. History also loads its listens and tracks
  in one query instead of one per listen.

- **News recorder.** A capture that failed part way left its `.part` file behind; deleting a source
  left its recordings on disk; a retention of 0 deleted the bulletin just recorded and a negative
  one captured the same hour twice; two record-now presses in the same minute shared one file and
  got two rows; and a second source due at the same hour waited for the first, while each capture
  held a database connection for its full ten minutes. Recordings are now named to the second, one
  source records one capture at a time (record-now answers 409 while it does), sources due together
  are captured side by side, no connection is held during a capture, and out-of-range source
  settings are a 422. A `Range` such as `bytes=10-5` is a 416 instead of a negative
  `Content-Length`.
- **ListenBrainz import stopped at 10.000 listens and said `completed`.** It now ends as
  `truncated` at its page cap and the next import for the same account continues below the oldest
  listen reached (`scrobble_imports.oldest_listened_ts`, `migrate_v35`). Paging no longer skips the
  listens that share the boundary second (`max_ts` is exclusive already), and a listen without a
  timestamp no longer fails the whole import with a `TypeError`.
- **`GET /api/library/tracks` and `/advanced`: page 0 was a 500 and `limit` had no ceiling.** Both
  now answer 422 for `page < 1` or `limit > 500`. `/tracks` also dropped `sc_url`/`yt_url`, two
  correlated `LIKE '%…%'` scans of the download archives per row that no client read.
- **Logging in with a non-ASCII password, or one over bcrypt's 72-byte limit, was a 500** that the
  login rate limiter never counted. Both are now an ordinary 401.

- **A retag that changed a title or the primary artist left the track's ratings and listens behind.**
  `track_uid` hashes title, duration and primary artist, so the scanner gave the retagged file a new
  track row and never touched the old one: ratings (`rating_tracks`) and listens (`scrobble_listens`)
  stayed on a row without a file, and the song-version worker could even pick that row as canonical
  and hide the real file in LMS. The scanner now moves ratings (newest wins), listens, analysis rows
  and work pins to the new row and deletes the old one, in one transaction; a fileless track can no
  longer be canonical. Rows orphaned before this are repaired by the new admin-only
  `POST /api/scanner/relink-orphans` (bug report 042).
- **A corrected publisher kept its old label link.** Label and channel links were only ever added;
  they are now recomputed from every file of the track on each scan.

- **Een promo- of follower-only track kwam binnen zonder genre, tags en omschrijving, en zonder
  regel in het archief.** De download zelf loopt door `YoutubeDL` mét de ingelogde
  Firefox-cookies en de bijpassende user agent -- daar is deze downloader voor -- maar de
  verrijking erna (`SoundcloudSongProcessor._fetch_enriched_info`) startte een kale
  `yt-dlp --dump-single-json` zonder cookies en zonder user agent. SoundCloud beantwoordt zo'n
  anonieme aanvraag voor een niet-openbare track met 401, en juist alleen voor die tracks,
  waardoor het jarenlang op een incidentele storing bij SoundCloud leek. Op 23 september ging het
  vier keer mis op 53 downloads: `thesplitter/dreaming` en drie promo's van `merciless_music`,
  elk 0,8 seconde na de eigen regel "Postprocessing downloaded file" -- de gecredentialiseerde
  aanvraag voor exact dezelfde track was dus net gelukt. De verrijking stuurt nu dezelfde sessie
  mee als de download. Wat verloren ging was de rij in `downloads_soundcloud_archive` en de
  tags uit `--dump-single-json`; het bestand zelf stond er gewoon.

- **The tagger rewrote files on every retag, and each rewrite could give a track a new identity.**
  `CheckArtistRule` edited the artist list while walking it, so a corrected first artist moved to
  the end (`ANGERFIST;outsiders;Dj Mad Dog` became `outsiders;Dj Mad Dog;Angerfist`) and the order
  changed again next pass; the scanner derives `track_uid` from the first artist, so ratings and
  listens ended up on a stale row. Every tag value was also split on '/', so AC/DC became two
  artists and `Live 24/7` three title parts; only genres are split on '/' now. On m4a, `REMIXER`
  and `ORIGINAL_TITLE` were written to atoms mutagen truncates to `REMI`/`ORIG` and never read back
  (title inference re-ran on the already-cleaned title each retag), and album / album artist went
  to atoms LMS does not read. They now go to `----:com.apple.iTunes:REMIXER`,
  `----:com.apple.iTunes:ORIGINAL_TITLE`, `©alb` and `aART`, and a file with the old atoms is
  migrated on its next retag. Bug report 053.

- **Een m4a zonder metadatablok liet de tagger bij elke ronde opnieuw stuklopen.** mutagen geeft
  `tags` als `None` terug wanneer het bestand helemaal geen atom heeft — een yt-dlp-fragment dat
  nooit samengevoegd werd (`... Identity Episode 108.f140.m4a`) is zo'n bestand — en
  `BaseSong._set_m4a_tag` schreef daar rechtstreeks in: `TypeError: 'NoneType' object does not
  support item assignment`. De wav-tak maakte dat blok al aan als het ontbrak; m4a doet dat nu ook.
  Omdat een bestand dat de parse niet haalt nooit als verwerkt wordt weggeschreven, kwam het via
  `new_in_library` elke ronde terug: 274 keer in het venster van één nacht, op één bestand.

### Security
- **`POST /api/config` echoed secrets in the clear.** The response carried the real value of every
  posted key; it now carries the masked value the GET shows. API consumers that read the response
  body receive the sentinel for secrets (the web config page reloads the fields and is unaffected).

- **The seven accepted starlette advisories are gone from `security/accepted-vulnerabilities.txt`.**
  They were accepted for fastapi 0.111; the requirements pin 0.141, and
  `scripts/ci/dependency-audit.sh` reports no Python, npm or Android finding with the list empty.

- **A deploy showed the whole production `.env` to anyone who ran `ps`.** `deploy.sh` and
  `deploy-stack.sh` put the env file, base64-encoded, on the ssh command line, and migrations put
  the MariaDB root password in `mariadb -p...` — visible on the runner and on the production host
  for as long as the deploy ran. The env file now travels on ssh's stdin and the password reaches
  the client as `MYSQL_PWD` through `docker exec -e`. On the host the env file is written under
  `umask 077` to `/root/.muma-deploy/<stack>/` and deleted when the deploy ends, instead of staying
  world-readable in `/tmp/.env.<stack>` until the next reboot; the compose file moved there too,
  and a `/tmp/docker-compose-v2` is no longer run as root. In CI the Docker Hub login uses a
  throwaway `DOCKER_CONFIG`, the ssh-agent holding the prod key is killed when its job ends, and
  the prod env files are written outside the checkout (and `.dockerignore` excludes `.env`), so
  none of them outlives the job on the shared runner or lands in a build context. A password
  containing `#` no longer breaks the migration step. See bug report 038.

- **Any `X-API-Key` made the caller whoever `u` named on LMS's `/muma` routes.** The bridge accepted
  every non-empty key without checking it and then took the caller from the bare `u` parameter, so
  `GET /muma/api/admin/subsonic-token?u=<an admin>&username=<anyone>` with `X-API-Key: x` read -- and
  `PUT` replaced -- any user's Subsonic token; media libraries and per-user settings opened the same
  way. The generic proxy also added MuMa's system key whenever the caller sent no header, so
  `?apiKey=x` reached MuMa as the system identity. A key now counts only if it is LMS's own
  `api-key` or MuMa confirms it through `/api/auth/verify` (cached 60 s, cleared on
  `/muma/users/sync`); the caller is whoever that verified credential names; admin routes need a
  verified admin user rather than a system key; and the proxy forwards the caller's own key and
  nothing else. Bug report 056. The same admin route also refuses a Subsonic token shorter than
  16 characters (400, existing tokens untouched), the floor `updateUser` already applied.

- **Any logged-in user could crash the music server with one settings request.** `updateUser`
  stored any integer as the feedback or scrobbling backend, and the next rating or listen looked
  up a backend that did not exist and dereferenced a null pointer -- a segfault for everyone.
  Every enum setting is now range-checked (an unknown value is a bad-parameter error and nothing is
  written), and both services look a backend up without inserting into the map the request
  threads share. Subsonic tokens are unique per domain (migration V121 removes values two users
  shared, so both re-issue) and must be at least 16 characters. Bug report 044.
- **`getSpotifyTracks`, `getSpotifyPlaylist` and `getSpotifyHistory` no longer walk the whole
  library.** A negative `offset`/`count` is refused and `count` is capped at 1000, so `count=-1`
  no longer means "everything".
- **A 429 from MuMa no longer freezes the queue to MuMa.** A proxied call gets the 429 as its
  answer, other requests are retried three times and then failed, and the queue is capped at 1000
  waiting requests.

- **Any account could start a ListenBrainz import into any other account's history.**
  `POST /api/scrobble/import/listenbrainz` took `username` from the body without checking it against
  the caller. An ordinary account may now only import into its own history (403 otherwise); admins
  and the system key may still name anyone.

- **Most of the management API was open to every account, whatever its role.** Three routers
  still carried a pre-RBAC `verify_api_key` that accepted any enabled account, so a plain `user`
  could read the log of any container on the Docker host, add and remove downloader sources,
  decide genres and rules, confirm label proposals (which moves folders on disk), clear the event
  log, write ratings under another account's name, and make the server fetch an arbitrary URL.
  `GET /api/users` also returned every account's `api_key`, which login accepts as a password.
  **Contract change** for the routes below; the web management UI (admins) and LMS (system key)
  pass unchanged, and the Android app uses none of them as a normal user:
  - `rules.manage`: genre/podcast decisions, artist/label genre rules, artist redirects,
    label-proposal confirm/reject, `POST /api/tagger/rescan[/file]`, and the mutating artist-image
    routes (`/image/url`, `/image/upload`, `/image/select`, `/image/clear`, `/fetch-missing`,
    `/{id}/fetch-image`);
  - admin: `GET /api/system/containers`, `GET /api/system/logs/{name}` (only containers the list
    shows, else 404), SoundCloud/YouTube account add/delete, `DELETE /api/events[/{id}]`,
    `POST /api/users/sync/*` (409 while a sync runs, shared lock with the hourly loop);
  - system key only: `POST /api/rating/lms-event` and `/server-event`;
  - own account or admin: `GET /api/rating/ratings/{username}`;
  - `POST|PUT /api/users/{id}/password`: another account's or any admin's password needs admin; a
    non-admin changing their own must send `current_password`;
  - `GET /api/users` and the `POST /api/users/{id}/merge` response no longer carry `api_key`;
  - image URLs resolving to a non-public address are refused (400), and downloads and uploads are
    capped at 10 MB (413).
  An unknown or disabled key on the management routes now answers 403 instead of 401, like every
  other router. See docs/bug-reports/037-management-routes-open-to-every-user.md.
## [0.72.1] - 2026-09-23

### Fixed
- **Elke luisterbeurt in de app werd twee keer geteld.** Sinds de app de web-UI draait (12
  september) scrobbelden twee spelers dezelfde track: de native speler (`mobile`/`auto`) en de
  web-player in de WebView (`frontend`). De server herkent een dubbele alleen aan exact dezelfde
  tijd, en die verschilden, dus ~345 luisterbeurten op productie hebben een tweeling. De
  web-kopie was bovendien fout: bij een trackwissel door de service werd de starttijd niet
  vernieuwd (zes verschillende tracks kregen dezelfde `listened_at`), en vanuit een WebView op
  de achtergrond kwam hij een half uur te laat of mislukte hij — de "Scrobble mislukt"-melding.
  Op de native shell laat de web-player het scrobbelen nu aan de service over.

## [0.72.0] - 2026-09-22

### Added
- **Een backfill die de hoes inbedt in bestanden die er zonder binnenkwamen.**
  `scripts/backfill_artwork.py` vult aan wat de downloaders hadden moeten meeschrijven:
  387 van 149.626 SoundCloud-nummers hadden een hoes, en 4.132 van 53.702 YouTube-nummers.
  Opnieuw per bestand via yt-dlp zou 200.000 extracties zijn tegen een host die een burst met
  403 beantwoordt; dat hoeft niet. SoundCloud beantwoordt `tracks?ids=<50>` met een
  `artwork_url` per track en de id's staan al in het archief, dus de hele bibliotheek is
  ~3.000 verzoeken. Een YouTube-thumbnail is adresseerbaar vanaf het video-id, dus die kant
  vraagt geen enkele API. Alleen bestanden zonder afbeelding worden aangeraakt, een track
  waarvoor het platform geen hoes heeft blijft leeg (níét de avatar van de uploader), en een
  URL die geen http(s) is wordt geweigerd — `urllib` spreekt ook `file://`, en die URL komt
  uit andermans JSON. Draai hem met `--dry-run`, dan `--account <kanaal>`, dan de rest.

### Fixed
- **45.066 artiesten hielden een oordeel dat een blinde fetcher had geveld.** `migrate_v30` was
  precies daarvoor geschreven en draaide ook, maar deed niets: zijn voorwaarde was er één voor de
  hele tabel — "reset alles, tenzij er sinds de blackout een provider-foto binnen is" — en tegen
  de tijd dat die migratie voor het eerst op productie kwam, stonden er al 22 met de hand
  opgehaalde Spotify-portretten in. Daarmee was de voorwaarde voor alle overige 45.044 artiesten
  permanent onwaar. `migrate_v32` stelt de vraag per artiest: is *dit* oordeel geveld in het
  venster tussen de blackout en de eerste foto die een provider daarna leverde? Zo ja, terug naar
  "nooit gevraagd"; zo nee, het blijft staan. Zelfbeperkend en herhaalbaar, want deploy draait
  hem elke keer. De fetcher pakt deze artiesten daarna vanzelf op.
- **Gedownloade nummers krijgen weer een hoes.** Beide downloaders voegden yt-dlp's
  `EmbedThumbnail`-postprocessor toe, maar zetten `writethumbnail` niet. Die postprocessor bedt
  een thumbnail-*bestand* in: hij zoekt `info['thumbnails'][i]['filepath']`, vindt niets, meldt
  "There are no thumbnails on disk" en geeft het bestand onveranderd terug. Op de
  commandoregel impliceert `--embed-thumbnail` dat `--write-thumbnail`; via de Python-API niet.
  Niets ging stuk: downloads landden, de postprocessor draaide, en de bestanden hadden geen
  hoes. Op productie had 387 van de 149.626 SoundCloud-nummers er een. Geldt vanaf nu voor
  nieuwe downloads; bestaande bestanden hebben een aparte backfill nodig.
- **De nummerlijst in de webinterface valt terug op de artiestfoto.** De tabel tekende een kale
  `<img>` die bij een ontbrekende hoes direct naar het MuMa-merk sprong, dus de keten
  hoes → artiestfoto → getint vlak die de kaarten en de speler al gebruikten, bereikte nooit de
  lijst waaruit de meeste nummers gespeeld worden. Offline wordt de artiestfoto overgeslagen --
  dat is ook een serververzoek -- en het vlak blijft hier zonder titel: naast de titel van de
  rij is een tweede exemplaar op 48 pixels ruis, geen herkenning.

## [0.71.1] - 2026-09-21

### Changed
- **De speler laat album, releasedatum en de radioknop altijd zien, en zegt waar je écht uit
  afspeelt.** Onder de artiest staat nu een vaste regel met het album (tikbaar) en de
  releasedatum; die datum stond sinds de polish-ronde alleen nog in de nummerdetails. De
  radioknop van de desktopbalk zit nu ook in de iconenrij van het telefoonscherm, met de
  kanaalkeuze als bottom sheet. En "Afspelen vanuit" las "Nummers" voor elke wachtrij uit de
  nummerlijst, wat niets zei over de lijst waaruit je koos: het is nu "Nummers · Recent
  uitgebracht" (of welke sortering er ook aanstond). Een genre-, label- of jaarpagina hield al
  zijn eigen naam.

### Fixed
- **De Volledigheid-tab gaf "No module named 'yt_dlp'" zodra hij live stond.** De opgeslagen
  telling werd gelezen via een dataclass in `deep_sweep.py`, en die module importeert yt-dlp
  bovenaan; de manager-container heeft yt-dlp niet en gaf dus geen enkele rij terug. De
  dataclass staat nu in `account_snapshot.py` zonder die import. Een test leest een rij in een
  subprocess waarin `yt_dlp` onimporteerbaar is, zodat dit niet stil terug kan komen.

## [0.71.0] - 2026-09-21

### Added
- **Nummerdetails tonen nu het bestand en alle tags.** De sheet achter `⋮` (en nu ook achter een
  tik op de titel in de speler) verborg bestandsnaam en formaat achter een inklapbare "Technische
  details" die alleen bitrate en pad liet zien. Er staat nu een vaste sectie *Bestand* met
  bestandsnaam, `MP3 · 320 kbps · 44,1 kHz · stereo · 9,8 MB`, map en de dag van toevoegen -- alles
  wat LMS al meestuurde en de UI weggooide -- plus een sectie *Tags* die MuMa bij het openen vraagt
  via het nieuwe `GET /api/library/tracks/by-path`: kanaal met platform, bron-URL, herkomst, BPM,
  catalogusnummer, copyright, originele artiest/titel, remixer, en daaronder elke overige tag uit
  het ingestion-record. Een bestand dat MuMa niet kent geeft geen tags-sectie; een MuMa die niet
  bereikbaar is zegt dat, zodat het niet leest als "dit bestand heeft geen tags".

### Fixed
- **Festivals worden nu echt geïndexeerd.** `FESTIVAL` stond nooit in de extra tags van de
  LMS-scanner op productie -- een runtime-instelling die alleen in een ontwerpdocument
  genoemd werd -- dus de festivalpagina's, de festivalchip in de nummerdetails en het nieuwe
  `festivals`-veld op het song-node bleven leeg terwijl de tagger al maanden `TXXX:FESTIVAL`
  schreef. Migratie V119 voegt de tag toe aan `scan_settings.extra_tags_to_scan` (achter wat er
  al stond, één keer) en verhoogt de audio-scanversie, zodat de eerstvolgende scan de hele
  bibliotheek één keer herleest en de clusters vult.
- **De kanaalregel in de nummerdetails is een plek om heen te gaan.** Een kanaal dat als label
  gecureerd is opent die labelpagina; een kanaal dat als artiest gecureerd is opent een zoekactie
  op die naam. Een ongecureerd kanaal blijft tekst.
- **De labelchip in de speler rendert weer, en de festivalrij in de nummerdetails bestaat nu
  echt.** De speler las `track.label || track.publisher`; LMS zet op een song-node `labels: [...]`
  (de PUBLISHER-cluster) en nooit een van die twee, dus geen enkel nummer kreeg zijn label onder de
  genres terwijl de sheet -- die wél `labels` leest -- het gewoon toonde. De sheet las op zijn beurt
  `track.festival`, een veld dat LMS nooit stuurde: de song-node krijgt nu `festivals` naast
  `labels` en `moods`; migratie V119 (hierboven) zorgt dat de scanner die tag ook leest.

## [0.70.0] - 2026-09-21

### Added
- **Per kanaal is nu te zien hoe compleet het is.** De diepe ronde van de downloader telde al
  per account hoeveel tracks het platform vermeldt, hoeveel het archief heeft en hoeveel er nog
  open staan, maar schreef dat alleen naar het log. Die telling wordt nu als momentopname
  bewaard in `downloads_account_checks` (`snapshot_*`, per SoundCloud-account en per
  YouTube-kanaal-en-type) en getoond onder Beheer → Downloaders → Volledigheid: tegels met
  geteld/compleet/achterstand, de afschrijvingen per reden, en per kanaal een balk
  gearchiveerd/uitgesloten/open met laatste download en leeftijd van de telling. De telling is
  een partitie -- gearchiveerd + uitgesloten + open = vermeld -- en niet de lopende getallen uit
  het rapport, die verlopen afschrijvingen meetellen en niet optellen. Er staat bewust geen
  einddatum bij: de rondes lopen per kanaal op eigen tempo en een 429 remt alles tegelijk af.
  `GET /api/downloaders/coverage/{source}`. Het YouTube-archief krijgt met `migrate_v31` een
  `added_at`; bestaande rijen blijven NULL ("onbekend") in plaats van allemaal op de deploydag
  te landen.

- **Hoe compleet de catalogus van een label is, staat nu op de labelpagina.** Dirty Workz nummert
  zijn releases `DWX0001` tot `DWX2212`; wie 001–303 en 305–309 heeft, moest tot nu toe een
  mapoverzicht sorteren om te zien dat 304 er niet is. Beheer > Labels > label krijgt een sectie
  Catalogus die de nummers uit de mapnamen van de releases leest (er is nergens een kolom voor;
  `LabelPath.split` van de tagger levert de releasemap, ook bij een geneste map) en ze per reeks
  groepeert: `DWX`, `DWXCD`, `DWXCVR`. Per reeks het waargenomen bereik, hoeveel daarvan aanwezig
  is, een balkje, en de niet-aanwezige nummers als reeksen (`DWX0177, DWX0287–DWX0289`), met een
  knop die ze voluit, één per regel, naar het klembord kopieert -- dat is waar je mee zoekt. Een
  variant (`DWX1105D`, `DWX0544-`) vult zijn positie en wordt apart genoemd; wat geen nummer heeft
  (`DWXFREE`) staat onder Overig en telt nooit als gat. Het nummer is de laatste cijferreeks, drie
  cijfers of meer tenzij een streepje hem van de prefix scheidt, zodat `247HC001`, `AFT3R001`,
  `R909-29` en `DWXCD-050` goed vallen. De pagina zegt bewust "niet aanwezig" en nooit
  "ontbreekt": vóór het laagste en na het hoogste nummer wordt niets geclaimd, en een label kan
  nummers overslaan. Eén verkeerd getypte map die een reeks tot boven de 20.000 nummers oprekt,
  geeft alleen nog een telling. `GET /api/curation/labels/{naam}/catalog`, op aanvraag berekend
  uit twee queries: de labelkoppeling van de scanner én de labelmap op schijf, want die koppeling
  loopt achter (2.706 gekoppelde bestanden tegenover 5.531 onder `EPs/Dirty Workz/`, de
  overgeslagen rescan). Alleen de EPs-map telt: de Soundcloud-, Podcasts- en Top 100-bestanden van
  een label (74 + 44 + 20 + 33 bij Dirty Workz) zouden anders hun kanaal- of showmap als release
  opvoeren. Geen kolom in het labeloverzicht, geen afschrijftabel -- dat zijn latere stappen
  (docs/designs/label-catalog-coverage).
## [0.69.1] - 2026-09-21

### Changed
- **Een nummer zonder hoes toont in een rij of kaart de foto van zijn eerste artiest, niet een
  tegel met alleen de titel.** De speler deed dat al (hoes, dan portret, dan het getinte
  paneel); `TrackCard` en `TrackRowCompact` sloegen het portret bewust over, en een plank
  "Recent uitgebracht" zonder hoezen werd zo een kolom grijze titelblokjes. De keten is nu in
  `coverArt.artistImageFallback()` gedeeld, met `primaryArtistOf()` als de ene plek die de eerste
  artiest kiest (de `artists`-lijst met ids gaat voor de samengevoegde string). MuMa zegt "geen
  portret" met een 404 die de browser niet cachet, dus een mislukte URL wordt per sessie
  onthouden en de volgende rij van dezelfde artiest begint meteen bij het paneel. Van de 56.800
  artiesten hebben er 11.759 een portret; de 44.972 met status `failed` komen pas bij de
  volgende opstart na de 30-daagse wachttijd opnieuw aan de beurt, dus de planken vullen zich
  niet in één keer.

### Fixed
- **De artiestfoto-fetcher draaide een maand zonder sleutels en zette 45.000 artiesten op
  "niet gevonden".** De Spotify client id en secret kwamen alleen ooit mee in de `.env` die het
  image kopieerde; toen die COPY op 2026-07-24 terecht verdween, kreeg de container ze van niets
  meer -- `docker-compose.yml` noemde ze niet. Een provider zonder sleutel antwoordde met een lege
  lijst, precies wat een zoekopdracht zonder treffers ook geeft, en de fetcher schreef
  `image_status = 'failed'`: Sefa, Partyraiser, Dr. Peacock, Warface, alles vanaf 22 augustus
  (11.759 actief, allemaal van juli; 44.972 failed, geen enkele foto sinds). De velden op
  Beheer > Config bestonden al en werden door niemand gelezen, en `data/config.json` stond niet op
  een volume, dus wat je daar invulde overleefde geen deploy. Nu: `credential()` in
  `config_store` (configpagina eerst, omgeving daarna) voor fetcher én tagger-lookup;
  `ProviderUnavailable` voor een ontbrekende of afgewezen sleutel, 429, 5xx of netwerkfout, zodat
  alleen een 200 zonder treffers "niet gevonden" is; een run zonder geconfigureerde provider
  kijkt niets op en schrijft niets; `migrate_v30` zet de blinde verdicten terug naar "nooit
  gevraagd" totdat de eerste providerfoto na 22 augustus binnen is; compose geeft
  `SPOTIFY_*`/`LASTFM_API_KEY`/`DISCOGS_TOKEN` door en mount `/app/data`. De 404 op
  `/api/artists/{naam}/image` doet niet meer alsof hij een lookup start -- Starlette liet die
  background task altijd al vallen. Zie docs/bug-reports/034.
## [0.69.0] - 2026-09-20

### Added
- **Filteren op geluidskwaliteit: alleen flac, of alles vanaf 320 kbps.** De bibliotheek houdt
  16.500 flac- en 1.100 wav-bestanden naast 61.000 mp3's op 320 en ruim twee keer zoveel
  daaronder, en niets kon ze uit elkaar houden. De scanner zet elk nummer nu in een `QUALITY`-cluster --
  `lossless`, `320`, `aac`, `192`, `low`, dezelfde vijf lagen waarmee muma de canonieke versie
  van een nummer kiest -- uit codec en bitrate, niet uit de extensie: een ALAC in een `.m4a` is
  lossless. De bestaande bibliotheek is in de migratie (V118) uit de al opgeslagen bitrate en
  het pad gevuld, zonder rescan; de scanner corrigeert dat per bestand zodra hij het toch leest.
  In Bladeren staat een chip Kwaliteit naast Rating (`getSpotifyTracks` neemt `minQuality`, een
  ondergrens: `320` is 320 én lossless), een preset onthoudt hem als `minQuality`, en de auto
  speelt zo'n preset ook echt met dat filter. Een lossless-vraag op een bibliotheek die de
  cluster nog niet heeft, geeft niets terug in plaats van alles; de scan-naar-luisteren-keten
  pint dat vast met de 33 kbps-fixture.

### Fixed
- Elke deploy zette de hele Youtube-boom (32.000 bestanden) opnieuw in de retag-wachtrij.
  `scripts/deploy.sh` draait elke `migrate_*.sql` bij elke deploy, en stap 3 van
  `migrate_v7_youtube_category_genres.sql` markeerde onvoorwaardelijk `%/Youtube/%` voor een
  rescan -- zonder reden, dus in de wachtrij zichtbaar als "(walk)". Sinds het wachtrijmodel van
  0.67.0 werkt de tagger dat direct na de start op volle snelheid af, en dat is wat op 2026-09-19
  de API ruim een uur onbereikbaar maakte. De markering gebeurt nu alleen op de run die
  daadwerkelijk een categorie-rij toevoegde of besliste; op elke volgende deploy raakt de migratie
  geen bestand meer aan.

- Een losse bestandsscan wachtte onbeperkt op een lopende volledige scan, en dat legde de API alsnog
  plat nadat de retag-wachtrij leeg was. `scan_single` nam dezelfde lock die `run_full` urenlang
  vasthoudt; elke `announce()` van de tagger vroeg via `/api/scanner/scan/file` zo'n scan aan,
  gaf het na 10 s op, maar de serverthread bleef wachten tot de volledige scan klaar was. Na
  veertig van die aanvragen had geen enkel sync-endpoint -- `/health` incluis -- nog een thread,
  terwijl de CPU vrijwel niets deed en de async endpoints in milliseconden antwoordden (prod,
  2026-09-19: `/api/scanner/health` zei `busy: true`, `/health` bleef 60 s stil). Een losse scan
  wacht nu hooguit 5 s (`SCANNER_SINGLE_LOCK_TIMEOUT`) en geeft anders op; het bestand is niet
  kwijt, want zijn mtime is veranderd en de volgende volledige scan leest het sowieso. Het
  antwoord van `/api/scanner/scan/file` meldt met `scanned` of de scan is uitgevoerd.

- De tagger legde de API plat zodra een grote retag-wachtrij leegliep. Hij draait in hetzelfde
  proces als music-manager en gaf 16 threads een pagina van 500 bestanden zonder adempauze; na de
  0.67.0-deploy stonden 32.000 Youtube-bestanden in de wachtrij en gaven `/health` en
  `/api/auth/login` ruim een uur geen antwoord, terwijl LMS in milliseconden reageerde -- inloggen
  op de webpagina leek daardoor "stuk". De pool krijgt nu 12 threads (`TAGGER_WORKERS`) en werkt
  per plak van twee bestanden per thread, met daarna een pauze van 0,5 s (`TAGGER_BATCH_PAUSE`)
  waarin alleen de event loop het proces heeft. Een plak waarin niets geparsed hoefde te worden
  kost geen pauze, dus een ongewijzigde dagwandeling wordt er niet langzamer van.
## [0.68.0] - 2026-09-19

### Added
- **Artiesten goedkeuren op extern bewijs.** `tools/artist_auto_approve.py` slaat de
  artiestcuratie-wachtrij op, zoekt elke naam op bij Deezer, iTunes en MusicBrainz en keurt
  hem goed als een opname *op naam van die artiest* daar een titel draagt die de bibliotheek
  ook onder die naam heeft — twee titels bij één act, twee titels over bronnen heen, of één
  onderscheidende titel bij MusicBrainz én een winkel. Dat de naam bestaat telt niet (`Otis`,
  `Nero`, `Holly` bestaan overal als iemand). Nooit automatisch afkeuren: geen dekking is geen
  bewijs van rommel. Elke response wordt gecachet, dus stoppen en hervatten kost niets;
  `apply` tekent de rijen als `auto-external` en `undo` draait precies die terug.
  `POST /api/rules/artists/decide` accepteert daarvoor een `decided_by` bij de systeemsleutel.

### Fixed
- **Elke tagger-ronde zette dezelfde 768 verdwenen bestanden opnieuw in de wachtrij.** De
  scanner houdt rijen voor bestanden die hij sindsdien niet meer zag (`__TODO`-releases die
  de importer heeft verplaatst); de anti-join van 0.67.0 zette die elke ronde in de wachtrij,
  de wachtrij-pass zag dat ze niet op schijf staan en gooide de rij weg, en de volgende ronde
  begon opnieuw. Een verdwenen bestand houdt nu zijn rij als grafsteen (reden `missing`,
  geen mtime): komt het terug, dan tagt de eerstvolgende walk het alsnog.
## [0.67.0] - 2026-09-19

### Added
- **De tagger is vanaf Beheer › Tagger te stoppen en opnieuw van voren te starten.** Een ronde
  doet sinds 0.66.1 eerst de retag-wachtrij en loopt daarna uren door de mappen; wie in de
  tussentijd genres of artiesten besliste, zag de teller staan en `NU RETAGGEN` een 409 geven.
  De pagina pollt nu elke vijf seconden `GET /api/tagger/retag/pending`, dat naast de teller
  `busy` en `stopping` meegeeft. Zolang de tagger loopt staan er `STOP` (`POST /tag/stop`) en
  `OPNIEUW VAN VOREN` (`POST /api/tagger/retag/restart`, nieuw): die laatste breekt de lopende
  ronde af, wacht tot het slot vrij is en start een verse ronde die de wachtrij als eerste
  wegwerkt. De teller blijft staan en zakt terwijl dat gebeurt; hij verdween eerder bij het
  indrukken van de knop, wat een tagger die niets deed onzichtbaar maakte.

- **Een download of import is meteen zichtbaar: de worker die het bestand tagt meldt het
  ook.** De SoundCloud-, YouTube- en importer-workers tagden hun bestanden al zelf, maar
  schreven niets in de administratie van de tagger, dus de eerstvolgende mapwalk in
  music-manager tagde elk nieuw bestand nog een keer; LMS hoorde ervan bij zijn eigen
  geplande scan en de muma-scanner op zijn uurronde. Telegram-downloads werden helemaal
  niet getagd tot de walk `Telegram/` bereikte, ná EPs, Soundcloud en Youtube. Na de
  tag-pass doet elke worker nu `announce`: de rij in `tagger_processed_files` met de mtime
  van ná het schrijven, een LMS-scan van de map, en `POST /api/scanner/scan/file` voor de
  bibliotheektabellen. Daarvoor krijgen de workers via het nieuwe `environment-lms`-anker
  in `docker/docker-compose.yml` de LMS-host en -sleutel mee die music-manager al had.
  Elke stap is best effort: een gelukte download faalt nooit op een trage server.
  `POST /api/scanner/scan/file` en `POST /api/tagger/tag/file` draaien nu in de threadpool
  in plaats van op de event loop, want ze blokkeren.

### Changed
- **Elk Soundcloud-bestand kostte de tagger 2,2 s, waarvan 1,6 s het drie keer inlezen van
  `library_artists`.** De artiestregels bouwen per bestand een index van alle 57k namen, en
  `TableHelper.get_all_values()` ging daarvoor drie keer per bestand naar de database, terwijl
  de helper diezelfde namen al in het geheugen had. De helper levert nu zijn eigen snapshot
  (nooit gemuteerd, vervangen bij een wijziging, per minuut ververst zodat de download- en
  importcontainers een nieuwe artiest ook zien), `exists()` is een dict-lookup in plaats van
  een scan over 57k namen, en de vier plekken die alleen wilden weten óf er een lijkende
  artiest bestaat stoppen bij de eerste treffer in plaats van alle namen te scoren.

- **Een tagger-ronde zonder werk kostte ruim een uur aan databaseverbindingen.** De mapwalk
  vroeg per bestand op een verse verbinding of het al getagd was: gemeten op prod 14 ms per
  bestand, waarvan 0,1 ms de query zelf, over 327k bestanden. Dezelfde 327k rijen komen in
  één SELECT in 1,4 s terug en passen in ~100 MB. Een ronde laadt de tabel nu één keer, na
  de wachtrij-pass en alleen voor de duur van de walk; `mark_processed` houdt het snapshot
  bij, en als de tabel niet te lezen is valt de ronde terug op de oude query per bestand.
  Een bestand dat ná het laden gemarkeerd wordt, mist deze walk en pakt de volgende ronde
  in de wachtrij-pass op.

- **De tagger is een wachtrij-consument; de mapwalk is een dagelijks vangnet.** Elke
  vijf-minutenronde deed tot nu toe de wachtrij én daarna een walk over alle 327k
  bestanden, en die walk begon na elke deploy opnieuw bij EPs. De ronde doet nu alleen de
  wachtrij; de walk draait als de vorige ouder is dan `tagger_walk_interval_hours`
  (standaard 24, `0` is het oude gedrag), en het moment van de laatste walk staat op schijf
  zodat een deploy hem niet opnieuw start. `NU RETAGGEN` en `OPNIEUW VAN VOREN` doen alleen
  de wachtrij; `FORCEER VOLLEDIGE RESCAN` en `POST /api/tagger/tag/all` ook de mappen.
- **De wachtrij bedient beslissingen vóór bulk.** Genre- en artiestbeslissingen, regels en
  handmatige retags gaan eerst, dan bestanden die de scanner kent maar de tagger nooit zag,
  dan `rescan_all` en `deep_run`, dan rijen zonder reden. De deep run, de knop "rescan all",
  rerun-parse en de handmatige file-retag schrijven nu allemaal hun reden mee. De reden
  is een filter op de bestaande `(needs_rescan, filepath)`-index: `filepath` is 3068 van
  de 3072 bytes die een sleutel mag zijn, dus er past niets naast, en omdat de cursor
  alleen vooruit loopt leest één reden zijn rijen samen toch maar één keer.
- **Een bestand dat iemand met de hand neerzet wordt gevonden zonder walk.** Elke ronde
  zet de anti-join `library_media_files` minus `tagger_processed_files` in de wachtrij
  (reden `new_in_library`), beperkt tot de mappen en extensies die de walk zelf doet.
  Bijvangst: de 1.402 EPs-bestanden met `.MP3` in hoofdletters, die de hoofdlettergevoelige
  glob van de walk nooit zag, worden zo alsnog getagd.

### Fixed
- **De tagger meldt een map alleen nog aan LMS als er echt een bestand in geschreven is.** Een
  volledige ronde loopt elke map af en laat vrijwel alles zoals het was, maar meldde elke map
  toch: LMS logde op 2026-09-18 13.798 scanverzoeken in drie uur tegenover 7 opgeslagen
  bestanden, en las per verzoek ~1.000 bestanden van de NAS opnieuw, urenlang achter elkaar.
  `BaseSong.save_file()` zegt nu of het geschreven heeft, `_parse_worker` geeft `SAVED` naast
  `OK` en `SKIPPED` terug, en zowel de mapwalk als de retag-wachtrij melden alleen mappen met
  een geschreven bestand. Wat wel geschreven is komt net zo snel in de app als eerst.

- **70 % van de bieb gold élke tagger-ronde als "gewijzigd".** `tagger_processed_files.mtime`
  was een `FLOAT`: bij de huidige epoch ligt er 128 s tussen twee opeenvolgende waarden, dus
  de tagger schreef een afgeronde mtime terug en las bij de volgende walk `mtime > opgeslagen`
  voor elk bestand dat naar beneden was afgerond. Gemeten op 1.200 prod-bestanden: 841 elke
  ronde opnieuw getagd, 359 met een verborgen wijziging, 0 exact. De kolom is nu `DOUBLE`
  (`migrate_v29`), de tagger slaat de mtime van ná zijn eigen schrijfactie op in plaats van
  die van ervoor, en een opgeslagen waarde die nog float32-afgerond is en binnen één stap
  van het bestand ligt telt niet als wijziging -- die rijen genezen zodra het bestand om een
  andere reden wordt getagd.

- **Een bestand waarvan de tags netto niet veranderden werd toch elke ronde herschreven.**
  `Tag.has_changes()` was een plakkende vlag: elke mutatie zette hem aan en alleen een save
  zette hem uit. De artiestregels doen op elk "MOTZ Premiere"-bestand `[A, B] → [A] → [A, B]`,
  dus het bestand werd elke pass opnieuw geschreven en LMS las het elke pass opnieuw in, voor
  een tag die eindigde waar hij begon. De vlag is nu een vergelijking met de waarde bij het
  inlezen; de basislijn schuift pas op nadat de save is gelukt, en een geleegde tag houdt
  zijn basislijn als er weer een waarde in komt.
## [0.66.1] - 2026-09-18

### Changed
- **De Python-tooling in CI installeert niet meer bij elke job opnieuw.** `backend:format`,
  `backend:lint` en `backend:typecheck` draaien in een `python:3.14-slim`-container en deden elk
  een verse `pip install -r requirements-dev.txt` naar een weggooi-`/tmp`; drie keer dezelfde
  wheels per pipeline, en op 2026-09-18 — PyPI leverde een uur lang 80–260 KB/s — liep elk van de
  drie tegen de 10-minutengrens van de job, op beide runners, twee pipelines achter elkaar. De
  installatie landt nu in `~/.cache/muma-python-tooling/<sleutel>` op de runner (sleutel = hash van
  `requirements-dev.txt` plus het image), als bind mount in de container; alleen de eerste job na
  een requirements-bump praat nog met PyPI, de rest vindt de tools klaarstaan. Drie jobs die
  tegelijk starten delen de map onder een `flock`; een afgebroken installatie laat geen
  `.complete`-marker achter en wordt gewoon opnieuw gedaan. Sleutels die een maand niet zijn
  aangeraakt worden opgeruimd. `PYTHON_TOOLING_CACHE=none` zet het uit. Gemeten: eerste run 14 s
  voor drie gelijktijdige jobs, warme run 1 s.

- **De startpagina haalt van geen enkele feed meer tracks op.** Na 0.65.3 vroeg Home nog steeds
  tien tracks per band-mix op voor een genretint, en een rij van tien voor de Release Radar —
  vier feed-builds voor een scherm waar niemand die tracks leest. Een kaart is een deur; wat
  erachter zit laadt pas als je hem opent. De Release Radar is nu de eerste kaart in dezelfde rij
  als de vijf daily mixes, onder de kop "Voor jou"; de band-kaarten houden hun vaste kleuren, de
  artiestkaart haalt alleen nog zijn foto. Op de telefoon rendert "Overzicht" voor radar en/of
  mixen die ene kaartenrij, en de radar-tegel beschrijft zichzelf met zijn eigen tekst in plaats
  van zijn eerste track. De enige `/api/feeds`-aanroep die Home nog doet is de lijst zelf.

- **De tagger doet de retag-wachtrij nu eerst, rechtstreeks uit de tabel.** Een ronde liep de
  mappen af in de volgorde EPs, Soundcloud, Youtube, Telegram, overig en begon bij elke herstart
  bovenaan; met vijf deploys in één nacht en 213.789 gemarkeerde bestanden was Youtube (50.384
  in de wachtrij, 0 klaar) in zestien dagen niet bereikt en stonden de genrebeslissingen van die
  ochtend achter alles. `Tagger._process_pending` leest de rijen met `needs_rescan` per 500 op
  primaire sleutel, tagt ze met het brontype dat hun pad geeft, en gooit de rij weg van een
  bestand dat niet meer bestaat. Wat klaar is blijft klaar over een herstart heen. Nieuwe index
  `(needs_rescan, filepath)` via `migrate_v28`; de mapwalk daarna vindt alleen nog nieuwe en
  gewijzigde bestanden.

### Fixed
- **Een afgekeurde "artiest" als `001` zette bijna de hele bibliotheek in de retag-wachtrij.**
  Een regelwijziging vertaalt naar bestanden via een brede match: artiestnaam, titel *of pad*
  bevat de term. Voor een catalogusnummer of jaartal is dat elk pad. Het afkeuren van ~480
  cijfer-artiesten op 17 september markeerde 149.213 bestanden, waarvan er 6.168 die naam
  daadwerkelijk als artiest droegen; de tagger liep een dag door bestanden waar niets aan te
  veranderen viel en de genrebeslissingen die erachter stonden kwamen niet aan bod. Een
  afkeuring markeert nu alleen de bestanden die de naam vandaag als artiest hebben, en een
  term zonder één letter doet nergens meer een substring-match. Het herstelscript voor de
  bestaande wachtrij staat in `scripts/prod/clear-spurious-artist-retag-marks.sh`.
## [0.66.0] - 2026-09-18

### Added
- **Advies bij Genre Curatie.** De wachtrij stond op 821 genres, en het meeste daarvan is
  mechanisch te herkennen: twee genres met een schuine streep ertussen (`Frenchcore/Terror`,
  ook `\` en `,`), aan elkaar geplakt (`Jungleterror`), samengetrokken (`Upterror` is het begin
  van `Uptempo Hardcore` plus heel `Terror`; `Frenchtempo`), verkeerd gespeld (`Harddcore`,
  `Oldksool Rave`), met ruis erbij (`Hardstyle 2018`, `Happy Hardcore Classics`, `Add "uptempo"`),
  of helemaal geen genre — een artiest, een label, een woord (`Tafelpoot`). Naast elke naam in de
  wachtrij staat nu een **advies** met de redenering en een zekerheid: "vervangen door Uptempo
  Hardcore + Terror", "verwijderen", of niets, want `Energycore` leest als een genre en matcht
  nergens op, en dat blijft mensenwerk. Het woordenboek is je eigen eerdere werk: de goedgekeurde
  genres, elke correctie die al gemaakt is (`Vocal Trance → Trance` leert dat `vocal` een
  bijvoeglijk woord is dat je weglaat), de afgekeurde namen, en de artiest- en labelkoppelingen
  van de taggerpagina — `Dr Peacock` in het genreveld is een artiest die aan Frenchcore hangt,
  dus dat is het advies; een artiest zonder koppeling wordt "verwijderen, koppel hem op de
  taggerpagina". "Overnemen" per rij, "Advies opvolgen" per pagina voor alles met minstens 60%
  zekerheid; een advies doet nooit iets uit zichzelf, en een analyse raakt geen enkele beslissing.
  Droog gedraaid op de echte wachtrij: 126 vervangingen, 172 splitsingen, 372 verwijderingen,
  151 zonder advies. `POST /api/rules/genres/analyze`, `GET /api/rules/genres/summary`,
  `rules_genre_proposals` (`migrate_v27`), drempels onder `genre_curation_analyzer` in de config.
- **De genrelijst op de taggerpagina toont alleen goedgekeurde genres.** `GET /api/rules` gaf
  de hele `rules_genres`-tabel terug, dus het Genre Overzicht telde 1.767 rijen en de keuzelijst
  bij "artiest/label koppelen aan genre" bood ook afgekeurde en nog te beoordelen genres aan.
  Nu alleen `white`; de playlist-genrefilter gebruikt dezelfde lijst en gaat mee.

### Changed
- **Genre Curatie is nu de plek voor alles rond genres; het Genre Overzicht van de taggerpagina is
  weg.** De pagina onder Curatie › Genres heeft vier onderdelen: de **wachtrij** (met het advies
  van hierboven), **Genres** (elk goedgekeurd genre met aantal nummers, hardheid, waar het onder
  valt en hoeveel artiest- en labelregels erop wijzen; Bewerken opent de genrepagina), en twee
  regelpanelen **Artiest → genre** en **Label → genre**: zoeken op naam óf genre, sorteren op
  bereik, toevoegen met een naam uit de bibliotheek en een goedgekeurd genre (een dubbele regel
  wordt geweigerd vóór de knop), verwijderen, en per rij wie de regel maakte en hoeveel nummers
  hij raakt; een regel voor een naam die niet meer in de bibliotheek staat krijgt een label. De
  taggerpagina houdt alleen nog wat van de tagger is — rescan en retag — en wijst naar Genres.
  Het oude "Genre Overzicht" toonde de hele `rules_genres`-tabel, afgekeurde en nog te beoordelen
  genres incluis, en de koppelkeuzelijst bood die ook aan. `GET /api/rules/artist-genres` en
  `label-genres` geven per regel nu ook `artist_id`/`label_id`, `track_count`, `created_at` en
  `created_by`; `GET /api/curation/genres` is nieuw en levert het overzicht.
## [0.65.3] - 2026-09-18

### Changed
- CI runs what a push actually touched. A feature branch no longer gets a branch pipeline: its
  first push — the one before the MR exists — ran the entire file (66 job minutes for an 11-file
  frontend change) because a new branch has no commit to diff against, and the MR pipeline that
  followed seconds later ran the 13 jobs that mattered. A push to master, whose tree is identical
  to the release tip that just passed, now runs only the `release:*` sequence instead of re-testing
  backend and server first; the tag and the back-merge no longer wait twenty minutes for that.
- A mobile job that times out no longer leaves its Gradle container running. The runner killed the
  job's shell but not its `docker run`, and the orphan's daemon held the shared Gradle lock, so
  every mobile job on that runner died in sixty seconds with "Timeout waiting to lock journal
  cache" for the next hour. Containers carry a `ci.job` label and `after_script` removes them,
  with `RUNNER_SCRIPT_TIMEOUT` set so that step also runs on a timeout.

- **De startpagina laadde seconden en de onderdelen hielden elkaar op.** Release radar, de
  vijf daily mixes en de presets kwamen pas tegelijk in beeld, en elk van de feeds kostte de
  server seconden. Twee oorzaken (`docs/designs/feeds/home-load.md`). Aan de serverkant rekende
  elke feed-aanroep alles opnieuw uit: `GET /api/feeds` loste het luisterprofiel zeven keer op
  (één keer per policy, telkens dezelfde 90 dagen `scrobble_listens`), en de drie
  band-mixes bouwden voor een kaartkleur een volledige feed, tot en met de hele bibliotheek als
  kandidaat wanneer het venster verruimd werd. Eén startpagina was elf profiel-berekeningen.
  Aan de clientkant wachtten songs en sets op de radar (`Promise.all`), de mix-kaarten op alle
  drie de band-feeds én de artiestfoto, en zaten sessiecheck, instellingen en presets in
  dezelfde wachtrij van drie achter een feed-build — de wachtrij was gemaakt voor de LMS-proxy,
  waar deze aanroepen sinds 0.65.1 niet meer langs komen. Nu: het profiel wordt per aanroep één
  keer opgelost; elke feed en de feedlijst worden per luisteraar per dag opgeslagen in
  `feeds_snapshot` (de daily mixes zijn per ontwerp dag-stabiel, de radar wordt elk uur ververst,
  een gewijzigde instelling maakt alles direct oud) en een achtergrondlus `feeds-refresh` houdt
  ze voor iedereen met een luisterbeurt in de laatste dertig dagen alvast warm; een uitsluiting
  wist de snapshots van die luisteraar. `?limit=10` is voortaan de kop van dezelfde ranking als
  de pagina waar de rij naartoe linkt, niet een tweede verdeling over tien plaatsen. De client
  toont elke rij zodra die er is, tekent de mix-kaarten meteen uit de feedlijst met de vaste
  kleuren en vult genretint en artiestfoto later los in, en houdt twee wachtrijen: drie plekken
  voor wat nog via de LMS-proxy loopt, acht voor wat rechtstreeks naar MuMa gaat.
  `X-MuMa-Feed-Source` op een feed-antwoord zegt of het uit de snapshot kwam of live gebouwd is.
- **`verify_api_key` in `routers/users.py` blokkeerde de event loop.** De dependency was
  `async def` en riep de synchrone `verify_token` (een databaseronde) rechtstreeks aan, dus elke
  presets- of instellingen-aanroep hield alle andere verzoeken op tot de sleutelcheck klaar was.
  Nu een gewone `def`, zoals `feeds.verify_api_key` al was; de rbac-, scanner- en
  tagger-wrappers gaan mee.

- A release is cut in two pushes: the empty branch first with `-o ci.skip`, the stabilize commit
  second. GitLab evaluates every `changes:` rule as true on the first push of a new branch, so
  cutting and stabilizing in one push ran `muma:images`, `server:lint`, the integration and e2e
  jobs on a commit that touched only VERSION and the changelogs — the very jobs the CI comment
  claimed a release skipped. Nothing in the pipeline changed; the runbook and the comment now
  describe what actually happens.
## [0.65.2] - 2026-09-18

### Fixed
- **Het openen van de startpagina gaf 503's op vrijwel elke MuMa-aanroep.** Elke `/muma/api`-call
  loopt via de LMS-proxy, die niet meer dan de helft van zijn HTTP-threads aan MuMa laat wachten
  en de rest weigert met `Too many requests to MuMa in flight`. Op productie (8 cores) is die
  grens vier; de startpagina vuurde er een stuk of twaalf tegelijk af — sessiecheck,
  accountinstellingen, genretinten, feedlijst, release radar, drie daily mixes,
  artiestafbeeldingen — elk vanuit een eigen module met een eigen limiet, samen ruim erover. De
  weigeringen werden bovendien in de maat opnieuw geprobeerd, zodat ze elkaar opnieuw troffen.
  De web-UI houdt nu één wachtrij voor alle MuMa-aanroepen bij elkaar (drie tegelijk, zodat de
  speler zijn eigen plek houdt), probeert een weigering met jitter tot ruim vijf seconden opnieuw
  en vraagt de artiestafbeelding via diezelfde wachtrij op. Van de proxy hoort een gebruiker niets
  te merken, of het nu één of honderd aanroepen zijn. LMS krijgt daarnaast een vaste pool van
  zestien HTTP-threads in plaats van "aantal cores", wat de proxygrens op productie van vier naar
  acht brengt.

- **Gewone MuMa-aanroepen gaan niet meer door LMS heen.** De reverse proxy stuurt `/muma/api/…`
  nu rechtstreeks naar MuMa; alleen wat LMS zelf implementeert (login, bibliotheekbeheer,
  artiestafbeelding en artiest-id voor de speler, track-refresh, `/muma/users/`) blijft bij LMS.
  De LMS-proxy hield per aanroep een Wt-thread vast, stuurde ze één voor één door en weigerde
  boven de helft van zijn pool — de oorzaak van de 503's bij het openen van de startpagina, en
  een grens die bij elke nieuwe aanroep op een scherm opnieuw in beeld kwam. MuMa controleert de
  `X-API-Key` zelf; LMS voegde daar niets aan toe behalve de flessenhals. Een nieuwe CI-job
  (`muma:proxy-routing`) draait de echte nginx-config tegen stubs en bewijst per route waar die
  heen gaat. Wat wél via LMS blijft lopen krijgt bij een weigering nu een `Retry-After`, en de
  web-UI wacht precies zo lang. De job-endpoints van MuMa (`/api/jobs/register`, `/active`,
  `/history`) vragen voortaan zelf een sleutel; ze leunden op de check die LMS ervoor deed.

## [0.65.1] - 2026-09-17

### Fixed
- **Een radiokanaal bewerken of verwijderen in Beheer gaf een 405.** De webkant praat via de
  LMS-proxy (`/muma/api/...`) met MuMa, en die proxy stuurde elke PUT en DELETE door als een
  POST — met een opmerking in de code erbij dat dat waarschijnlijk niet klopte. MuMa antwoordde
  dan netjes `405 Method Not Allowed` voor `PUT /api/radio/channels/main`, en de browser toonde
  een method-fout voor een verzoek dat hij nooit zo verstuurd had. Het zag eruit als een kapotte
  route in MuMa; de route was goed. De http-client van de server kent PUT en DELETE nu als eigen
  verzoeken (`sendPUTRequest`/`sendDELETERequest`, boven `Wt::Http::Client::put` en
  `deleteRequest`) en de proxy geeft het echte werkwoord door. Een unittest tegen een lokale
  server controleert per werkwoord wat er op de lijn staat, en de ketentest maakt, hernoemt en
  verwijdert een kanaal via de proxy. De artiestafbeeldingen-routes blijven POST-only: die zijn zo
  gebouwd toen dit nog niet kon.
## [0.65.0] - 2026-09-17

### Added
- **De speler op de telefoon vertelt nu waar het geluid heen gaat.** Onder de bedieningsknoppen
  staat de huidige uitvoer — "Bose QC35 II", "Bedrade koptelefoon", "Telefoonluidspreker" — in
  de accentkleur; een tik opent de uitvoerkiezer van Android (of de Bluetooth-instellingen op een
  toestel zonder kiezer). Het label volgt een koptelefoon die verbindt of een stekker die eruit
  gaat zonder de speler te heropenen. Alleen in de app: de browser weet niet waar zijn geluid
  naartoe gaat en toont niets. Het `platform.system`-contract kreeg `outputRoute()`,
  `onOutputRouteChanged()` en `openOutputPicker()`; de browser antwoordt `null` en doet niets.

- **De web-UI wordt nu per merge request op desktop én telefoon gerenderd en vergeleken.**
  `frontend:e2e` draait de browsersuite voortaan in twee Playwright-projecten (`desktop`
  1280×800, `phone` 412×915) en maakt van negentien routes een screenshot die tegen de referenties
  in `services/frontend/tests/browser/__screenshots__/` wordt gelegd. Een afwijking kleurt de job
  oranje (exit 42, `allow_failure`) en laat het verschil als artifact achter; een functionele
  fout blijft rood. De referenties zijn tegelijk de schermafbeeldingen van de app —
  zie `docs/frontend-screenshots.md` voor verversen na een bedoelde wijziging
  (`MUMA_UPDATE_SNAPSHOTS=1` en `scripts/test/frontend-screenshots-pull.sh`).

- **Home op de telefoon liet je luistergeschiedenis links liggen.** Onder de bestaande
  rijen staan nu "Jouw artiesten deze maand" en "Jouw labels", opgebouwd uit dezelfde
  `/api/listening`-rankings als de statistiekenpagina, met een "Alles tonen" naar die
  pagina. Beide rijen blijven verborgen zonder MuMa-sleutel of zonder luisterbeurten,
  en vragen dan ook niets aan MuMa. Tikken op een artiest zoekt eerst het echte
  LMS-artiestrecord op (MuMa's eigen artiest-id is daar niet voor bruikbaar) en valt
  terug op een zoekopdracht als niets matcht; een label opent direct op naam.

- **Onder de tegels op het startscherm van de telefoon hield het op.** Er staat nu een
  "Memories"-rij met één tegel per jaar (dezelfde kaart als de volledige Memories-pagina); tikken
  opent dat jaar, afspelen haalt eerst het hele jaar op in plaats van alleen de paar nummers die op
  de tegel pasten. Staan "onlangs toegevoegd" en "onlangs uitgebracht" allebei als knop of uit, dan
  toont het scherm nu toch één "onlangs"-rij die bij de huidige weergave hoort (nummers → onlangs
  toegevoegd, sets → onlangs uitgebracht), zonder extra verzoek aan de server. Een Memories-jaar
  zonder omslagfoto krijgt nu hetzelfde getinte paneel als de speler in plaats van het generieke
  Spotify-plaatje.

- **De speler op de telefoon toonde bij een track zonder cover altijd hetzelfde platte MuMa-merk,
  en de mini-speler had een aparte ronde artiestenfoto naast de naam die nergens anders in de app
  voorkwam.** Een bibliotheek die grotendeels zonder covers zit oogde daardoor stuk in plaats van
  gewoon ongedecoreerd. `Artwork.svelte` kent nu een expliciete val-door-keten cover → artiestfoto
  → getint paneel met de titel, gedeeld door de mini-speler (44px) en het volledige scherm; een
  nieuw nummer reset altijd terug naar de cover, zodat een oude 404 nooit de cover van het
  volgende nummer overslaat. De achtergrond van het volledige scherm is een verticaal verloop van
  de genre-tint van het spelende nummer (`trackTint()` in `genreTints.js`, dezelfde
  server-geleverde kleur als de genregrid) naar het neutrale `#121212`, in plaats van vlak zwart.

- **Het volledige-scherm-speler eindigde bij de sterren en de knoppenrij; wat erna kwam, wie er
  nog meer van dezelfde artiest was of welke andere versie van hetzelfde nummer bestond, was
  alleen via de wachtrij-sheet of de songpagina te zien.** Onder de bestaande knoppen staan nu
  drie secties, elk verborgen zodra er niets te tonen is: "Hierna" (de eerstvolgende drie
  nummers in de wachtrij, of één regel zodra shuffle aanstaat), "Meer van {artiest}" (zes
  nummers, lui opgehaald en één keer per artiest) en "Versies" (de andere bestanden van hetzelfde
  werk, via dezelfde `getSpotifyTracks`-paginering als de songpagina, nu gedeeld in `versions.js`).
  Tikken op een "Hierna"-rij springt binnen de lopende wachtrij; de andere twee starten een
  nieuwe. "Hierna afspelen" uit het detail-menu voegt nu in op de echte wachtrijpositie in plaats
  van op het eerste nummer met hetzelfde id, wat een dubbel gebooked nummer op de verkeerde plek
  zette. Het scherm scrolt nu ook echt, dus de swipe-omlaag-om-te-sluiten reageert alleen nog
  boven aan de sectie.

- **Bladeren onthield niets: elke keer terug naar de vaste categorietegels.** Een artiest, album,
  genre, label, festival, afspeellijst, snelkoppeling of Memories-jaar dat je opent staat nu, per
  toestel en account, in een "Recent"-rij boven het rooster, nieuwste eerst en maximaal twaalf. De
  speler wist ook niet altijd waar de wachtrij vandaan kwam en viel dan terug op het album van het
  huidige nummer, ook bij een genre of afspeellijst; "Afspelen vanuit" noemt nu de plek waar de
  wachtrij is gestart, en tikken erop opent die plek in plaats van altijd het album.

### Changed
- **Een lege startschermtegel zei altijd "geen tracks gevonden in deze categorie", een mislukte
  laadbeurt zag er identiek uit, en een oneven aantal tegels liet de laatste half leeg staan.**
  Elke tegel heeft nu eigen tekst voor leeg ("Ontdek nieuwe releases", "Nog niets met een ster",
  …), een mislukte laadbeurt toont "Kon niet laden" en een laadbeurt in gang een puls op "…"; de
  laatste tegel van een oneven grid spant nu twee kolommen. De "alles tonen"-knop is niet meer in
  hoofdletters. De rijen "onlangs uitgebracht"/"onlangs toegevoegd" tonen compacte regels
  (`TrackRowCompact`) in plaats van kaarten met een placeholder, en elke kaart/regel gebruikt nu
  hetzelfde artwork-met-tint-fallback als de speler. Bladeren opent weer meteen op het
  categorierooster; geavanceerd zoeken zit voortaan achter een filterknop naast het zoekveld, en de
  categorietegels zijn een stuk lager.

- **De koptekst van de telefoonspeler stond in hoofdletters (`AFSPELEN UIT: NAAM`), genres en
  label waren platte tekst die na één regel afkapte, en "meer info" zat achter twee knoppen: een
  `(i)` onderaan en een aparte lyrics-knop bovenaan.** De koptekst is nu twee regels — een klein
  "Afspelen vanuit" boven de vetgedrukte naam — en blijft een knop naar het album. Rechtsboven
  staat één ⋮-knop die het bestaande `TrackDetailsSheet` opent (artiest, album, hierna afspelen,
  wachtrij, songtekst als die er is, details); de `(i)`-knop is weg. Genres en label zijn dezelfde
  tikbare pillen als in de sheet (nieuw gedeeld `MetaChips.svelte`) en wikkelen door in plaats van
  af te kappen; de releasedatum stond al in de sheet en verdwijnt uit deze rij. De artiestenregel
  (`ArtistList` `size="lg"`) is 44px hoog met een chevron, de sterren zijn 44×44px tikdoelen met een
  24px ster, en shuffle, herhalen en de onderste rij iconen staan allemaal op 24px.

### Fixed
- **De importer pakte downloads uit die de browser nog aan het schrijven was.** De extractiestap
  gaf elk bestand in de importmap aan patool, ook de `.crdownload` die Firefox nog vasthield.
  patool kijkt naar de inhoud en niet naar de extensie, dus een half geschreven `.rar.crdownload`
  met een al leesbare RAR-header werd afgekapt uitgepakt en het bronbestand daarna onder de
  schrijver vandaan gequarantainiseerd. Op 16-09 liep het zichtbaar mis: de ronde die om 15:00:08
  `HC-2026-WEEK-37-FLAC.rar.crdownload` in de lijst zette, was om 15:03:09 bij dat bestand
  aanbeland en toen had de browser het al hernoemd — alle drie de backends meldden `was not
  found`. Vijf archieven, zes ERROR-regels, en geen ervan was een echt probleem: alle vier de
  voltooide archieven kwamen een ronde later gewoon binnen. Bestanden met een `.crdownload`,
  `.part`, `.partial` of `.tmp` worden nu overgeslagen tot ze hun definitieve naam hebben, de
  conventie die `news.py` intern al volgde.
## [0.64.1] - 2026-09-16

### Fixed
- **Een andere taal kiezen in de app ververste het scherm en veranderde niets.** De taalkeuze
  zette de webkant meteen om en liet de shell de activity opnieuw aanmaken, maar het opslaan
  naar het account hing achter een debounce van 400 ms — die timer stierf mee met de WebView.
  Na het herladen kwam de taal uit `localStorage` wél goed op, waarna `applyAccountSettings`
  de oude taal van het account er weer overheen zette. `LanguageSetting` wacht nu tot het
  account de nieuwe taal heeft (`flushLocaleSave`) voordat hij `setAppLocale` aanroept; in een
  browsertab verandert er niets, daar herlaadt niets.
## [0.64.0] - 2026-09-16

### Added
- **Artiestcuratie in Beheer.** `library_artists` vult zichzelf — de scanner slaat elke naam op die
  een taggerregel ooit maakte — en zo'n een op tien is een echte artiest. Er is nu een wachtrij,
  in de vorm van Genre Curatie: per naam goedkeuren, afkeuren of corrigeren naar een andere
  spelling, in bulk per pagina. Elke beslissing gaat naar `rules_ignored_artists`, dus de tagger
  handelt ernaar zonder nieuwe regelcode; de 2.658 bestaande redirects staan als afgekeurd
  voorgesorteerd. Naast elke naam staat een **advies** uit de analyse van 0.0.54, nu eindelijk
  ergens aan vastgemaakt: "verwijderen" voor wat geen naam kan zijn (`Premiere`, `OUT NOW`,
  `***`), "samenvoegen met X" voor spellingvarianten en een losse `DJ`/`MC` (`Dr.Peacock` →
  `Dr. Peacock`, `DJ Angerfist` → `Angerfist`), met de reden erbij. Het woordenboek van de
  analyse zijn uitsluitend de goedgekeurde namen — geen bootstrap uit de data zelf, want die gaf
  `Rbr → RBR ©` — en een herschrijving naar een spelling met mínder nummers wordt niet
  geadviseerd. Een advies doet nooit iets uit zichzelf; "Advies opvolgen" is de knop.

- **Alle taggerinput onder Beheer › Curatie, elk op een eigen pagina.** Naast Genres, Artiesten
  en Podcasts nu ook **Labels** (elk label met nummers, catalogus-id's, genreregels en
  moederlabel; Bewerken opent de labelpagina), **Festivals** (naam, spellingen, editiedatums en
  actief — de drie tabellen die `FestivalHelper` leest en die tot nu alleen via SQL te vullen
  waren, met een "test een tekst"-vak dat de echte matcher over een titel laat lopen vóór je
  opslaat) en **Lineups** (de tekstbestanden onder `metadata/festival-lineups`: plak een line-up,
  "Controleren" zegt welke namen de bieb matcht en biedt de dichtstbijzijnde spelling voor de
  rest, opslaan schrijft de bieb-spelling). Nieuwe endpoints: `/api/rules/festivals` (+ `/probe`),
  `/api/rules/lineups` (+ `/match`), `GET /api/curation/labels`. Volgorde van de groep: Tagger,
  Genres, Artiesten, Labels, Labelvoorstellen, Podcasts, Festivals, Lineups.

- **De vijf daily mixes zijn nu ook te zien, niet alleen op te vragen.** Web-Home toont een
  "Dagelijkse mixen"-rij met vijf tegels (Zachter/Middenin/Harder plus de artiest en het label van
  de dag) in plaats van de ene "Dagelijkse mix"-rij; elke tegel krijgt de titel/subtitel die de
  server al berekende, een kleur (het genre-tintje van de meest voorkomende genre in de mix, anders
  een vaste groen→blauw→rood-schaal op bandpositie; de artiest-tegel probeert eerst een
  artiestfoto, anders een kleur op basis van de naam) en een eigen afspeelknop. De klassieke
  `daily-mix` blijft bereikbaar via zijn eigen `/daily-mix`-route, maar is geen zesde tegel. Op de
  telefoon wordt dit één tegel "Dagelijkse mixen" (Knop) of dezelfde vijf-tegelrij (Overzicht),
  via de bestaande Home-instelling voor de dagelijkse mix — geen nieuwe instelling. De feedpagina
  zelf toont nu ook een regel met de hardheidsband en hoeveel plekken zijn aangevuld vanuit tracks
  zonder bekende hardheid, wanneer van toepassing.

- **Een rondleiding bij het eerste bezoek en een handleiding in de app.** Wie voor het eerst
  inlogt krijgt zes korte stappen: taal, nummers of sets, wat er op Home staat, hoe lijsten
  eruitzien, (op de telefoon) downloaden op mobiele data, en een verwijzing naar de handleiding.
  Elke stap schrijft dezelfde instelling als de instellingenpagina, dus er is geen tweede kopie.
  Het account onthoudt welke stappen het gezien heeft; komt er in een latere release een
  instelling bij, dan verschijnt alleen die ene stap, met een "Nieuw"-label. Overslaan telt ook
  als gezien — de rondleiding blijft niet terugkomen. De handleiding staat als tabblad onder
  Instellingen en in het profielmenu: per onderdeel wat het is, waar het zit, en een knop
  erheen; bovenaan een knop om de rondleiding opnieuw te doorlopen.

### Changed
- **Web-sidebar en telefoon-Bladeren zijn nu één lijst.** `Sidebar.svelte` en `BrowseGrid.svelte`
  hadden elk een eigen kopie van de bibliotheeksecties, met eigen volgorde en deels andere iconen;
  beide lezen nu `navigation.js`, en een test houdt de gerenderde sidebar en het gerenderde grid aan
  dezelfde set. Wat er anders wordt: de telefoon krijgt "Nummers" (of "Sets", naar de actieve modus)
  als eerste tegel — de volledige lijst was daar alleen via de Home-tegels bereikbaar — en de tegels
  staan in de volgorde van de sidebar. "Luisteren" heet in beide "Luisterstatistieken", zodat de
  luisterpagina herkenbaar is als de statistieken die het zijn. Op de telefoon blijft "Bladeren" ook
  actief op de pagina van één genre, label, jaar of lineup en op de nummers/sets-lijst, zoals dat al
  voor een artiest of album gold.

- **De drie spectrum-dagelijkse-mixen namen de luisteraar zijn eigen smaak als meetlat voor "hard".**
  MR !798 leidde de zacht/midden/hard-grens af uit iemands eigen gewogen 33e/67e percentiel. Gemeten
  op productie voor Teun, direct na 0.63.0: die grens kwam uit op 62,5/92,5, met hardheidsbronnen
  genre 1601 / artiest 613 / label 160 / tempo 3 / geen 186. Resultaat: "Zachter" werd ruwe
  hardstyle + techno + mainstream hardstyle (800 kandidaten), "Middenin" werd uptempo hardcore /
  bouncy uptempo / zaagtempo (579), en "Harder" bleef over met alleen terror/speedcore — 71
  kandidaten, het releasevenster opgerekt naar 365 dagen en 13 plekken aangevuld vanuit tracks
  zonder bekende hardheid. Wie veel uptempo draait, mag niet zien dat uptempo daardoor "het midden"
  wordt: het spectrum gaat over de muziek, niet over wie er net naar luistert. De grenzen liggen nu
  vast op 50/75 (op dezelfde genre-ankers: hardstyle en mainstream hardstyle blijven zacht, raw
  hardstyle/hardcore/mainstream hardcore midden, gabber en zwaarder hard), instelbaar zonder deploy
  via `feeds_hardness_edges`. De eigen gewogen p33/p50/p67 van de luisteraar worden nog steeds
  getoond (profielweergave, dry run) — ze bepalen alleen niet langer de grens.

### Removed
- **`muma-soundcloud-worker-full-once` is uit de stack.** De eenmalige volledige SoundCloud-sweep
  (`--no-break-on-existing`, zonder `--repeat`) stond sinds 0.27.0 voor niets: de downloader doet
  zelf elke `deep_sweep_days` een deep pass, en juist het uitzetten van break-on-existing was wat
  de 429's opleverde. De container stond als "offline" op het Beheer-overzicht en als vaste
  uitzondering in de nachtelijke check; beide zijn weg. `--remove-orphans` bij de volgende deploy
  ruimt hem op prod op.
## [0.63.0] - 2026-09-16

### Added
- **Vijf daily mixes in plaats van één.** `rules_genres` kreeg een `hardness`-kolom (0-100,
  bewerkbaar op de genre-edit-pagina naast de hiërarchie): geseed met een handmatige lijst
  ankers (Deep House 10 tot Speedcore 100) en overgeërfd via `rules_subgenre_hierarchy` voor
  elk genre zonder eigen anker. Een track leent, als hij zelf geen gescoord genre draagt, de
  hardheid van zijn label, dan van zijn artiest, dan van zijn tempo. `GET /api/feeds` somt nu
  zes tegels op met titel en subtitel: `daily-mix-soft`/`-mid`/`-hard` verdelen de eigen
  luistergeschiedenis in drie tertielen (Zachter, Middenin, Harder), `daily-mix-artist` en
  `daily-mix-label` draaien dagelijks door de top 10 artiesten/labels — welke van de tien het
  wordt, bepaalt een hash van gebruikersnaam en datum, niet een toevalsgenerator. `daily-mix`
  blijft de klassieke, ongefilterde mix — geen band, dus een track zonder gescoord genre verliest
  er nooit zijn plek door — zodat auto en telefoon niets hoeven te wijzigen. Een band die na het
  verruimen van het releasevenster (90 → 365 dagen → geen venster) nog te weinig kandidaten heeft,
  vult de resterende plekken aan met tracks zonder bekende hardheid in plaats van leeg te blijven;
  het aantal zo aangevulde plekken staat in de respons (`filled_from_unknown`).

- The phone's full-screen player again shows genre, release date and label under the track, and a new details button opens a track info sheet (cover, chips for genre/label/festival/mood, technical details, artist/album navigation) matching what the retired Kotlin player offered -- plus a "Song" button that jumps straight to every version of the current track.

### Changed
- **De tegels op Home en in het Favorieten-tabblad kregen weer het strakke Bladeren-uiterlijk.**
  `QuickAccessTile` was een grijze rij met een klein vierkant; hij is nu de compacte versie van de
  gekleurde Bladeren-tegel — effen kleur, een geroteerd icoon en een dikgedrukte titel — met een
  cover als achtergrondfoto zodra er een beschikbaar is. Home en Bladeren delen nu ook kleur en
  icoon per sectie (Memories, Favorieten). De "Goedemorgen/Goedenavond"-groet boven Home is op de
  telefoon verdwenen; die kostte alleen ruimte boven de tegels en staat nu alleen nog op desktop.

- **De schakelaar tussen Nummers en Sets op de telefoon verhuisde naar de bovenbalk.** De losse rij
  pillen boven Home, Bladeren en Favorieten is vervangen door een compacte segmented control
  ("Nummers | Sets") in één lijn met het zoekveld en de profielknop — precies zoals de
  desktop-sidebar het al deed. De telefoon-UI werd daarnaast zo'n 10% compacter: de bovenbalk,
  de inhoud, de Home-shelves en de onderste navigatiebalk kregen ieder een kleinere marge of
  padding, zonder de tikdoelen onder de 44px te duwen. Desktop is ongewijzigd.

### Fixed
- **Release Radar en Daily Mix laadden niet in de shell (telefoon/tablet), wel op desktop.**
  `feeds.js` haalde `/api/feeds/release-radar` en `/api/feeds/daily-mix` op zonder de
  `X-API-Key`-header mee te sturen — elke andere `/api/*`-aanroep in de app (curatie,
  genre-regels, presets) doet dat wel. De server wijst een feed-aanvraag zonder key af met
  401, want een feed is per account: de systeemsleutel mag nooit iemands eigen aanbevelingen
  opvragen. Beide feeds sturen de sleutel nu net als de rest van de app.
## [0.62.0] - 2026-09-15

### Added
- **Geavanceerd zoeken, en het resultaat bewaren als snelkoppeling.** Nieuw op `/new-preset`
  (via "+ Nieuwe snelkoppeling" boven de tegels op het startscherm, en op de telefoon bovenaan
  het tabblad Zoeken): kies zoveel genres, artiesten, labels, festivals en jaren als je wilt —
  binnen één soort telt elk, ertussen moeten ze allemaal kloppen — plus een ratingbereik,
  sortering, nummers of sets en een aantal. De lijst eronder volgt de keuze live via dezelfde
  `getSongs`-clusteraanroep die een tegel afspeelt. Opslaan maakt er een dynamische
  afspeellijst van in MuMa, in de tegel-spelling die de Kotlin-app leest: een tegel op het
  startscherm, en sinds Android Auto die lijst van de server leest ook een rij in de auto onder
  Afspeellijsten. Een bestaande tegel is nu te bewerken via "Bewerken" in het menu van de
  tegelpagina (`/preset/<id>/edit`); de snelle "opslaan als preset" op een gefilterde lijst
  blijft bestaan en schrijft dezelfde spelling.

### Changed
- **De Over-pagina is een versie-overzicht.** Naast de LMS-versie staan nu de MuMa API-versie
  (`/health`), het serveradres en de git-hash plus bouwtijd van de webinterface
  (`version.json`); in de app ook versie, build, pakket, Android-versie en toestel, met een knop
  "Controleren op updates".

- **Telefoon: startscherm, navigatie, details en instellingen na de eerste testrit.** De
  onderbalk is nu Home | Bladeren | Favorieten: Bladeren houdt het zoekveld en elke categorie,
  met Artiesten, Afspeellijsten, Albums, Downloads en Favoriete nummers als eerste rij;
  Favorieten toont alle snelkoppelingen (presets) als blokken met "+ nieuw" bovenaan, en is
  bedoeld om later meer soorten favorieten te dragen. De chip-rij van het oude tabblad
  Bibliotheek is weg. Het startscherm volgt eindelijk de Home-instellingen die de
  instellingenmigratie al opsloeg maar nergens las: Memories, Release radar, Daily mix en
  Favoriete nummers als één blokje elk in een twee-koloms grid, Recent uitgebracht en Recent
  toegevoegd als rij, en "uit" verbergt de sectie. Een "⋯" per nummer opent een detailblad
  met album, genre, datum, duur, plays, rating en elke actie die tot nu toe alleen op de
  desktop bij hover bestond (versies, lyrics, hierna afspelen, in wachtrij, downloaden). De
  instelling "2 of 3 regels" werkt: regel drie is "album • datum". Instellingen zijn compact
  in plaats van de desktop-maat.

### Removed
- **De webspeler kent geen "Terug naar de klassieke interface" meer.** De knop op het
  inlogscherm en de rij in Instellingen → Apparaat riepen `switchToLegacyUi` aan op de telefoon;
  die interface bestaat sinds muma-mobile 7.0.0 niet meer, dus de knop, de rij, de groep
  "Interface" op de Apparaat-tab en de plug-in-methoden `switchToLegacyUi`/`openLegacySettings`
  zijn uit de shell-laag gehaald.

### Fixed
- **Eén LMS-thread gaf op alles 500 zodra de app opnieuw geopend werd.** `getSong`, `stream`,
  `scrobble`, `getMemories` — alles wat op die thread landde faalde met `Stale object,
  auth_token`, tot een herstart. Dbo bewaart objecten per sessie en de sessie is per thread:
  thread A hield jouw token op versie N, thread B stempelde `last_used` naar N+1, en de
  volgende bump van A schreef op zijn oude kopie. De `catch` in `processAuthToken` ving dat
  niet — de flush zit in `~WriteTransaction`, buiten elke catch — en het vuile object bleef in
  de sessie hangen, zodat elke latere write-transactie op die thread hem opnieuw flushte. Nu
  wordt het token vóór de bump opnieuw gelezen (onder de write-lock), expliciet geflusht
  binnen de try, en bij een stale write weggegooid.

## [0.61.0] - 2026-09-14

### Added
- **De "Apparaat"-tab dekt nu bijna alles wat het klassieke instellingenscherm ooit deed.**
  Netwerktimeout, max. bitrate bij vastzetten, automatisch offline schakelen, cachetijd van
  mapoverzichten, zichtbaarheid voor andere apps en verbergen voor de mediascanner staan er nu als
  gewone rijen. Auto-apparaten koppelen gaat voortaan met een echte bluetooth-kiezer in de tab zelf
  in plaats van via het oude scherm; "Scherm automatisch aanzetten" vraagt de systeemtoestemming
  direct aan. Een cachelocatie kiezen of terugzetten gebeurt met de systeem-mappenkiezer, zonder
  het oude scherm te openen. De muma-gebruikers-ID en -API-sleutel staan er nu ook bij, alleen om te
  zien — die vult inloggen al in. De rij "Alle app-instellingen…" is weg: er is nu niets meer dat
  hiernaartoe verwijst.
- **Instellingen die op de telefoon per apparaat stonden, volgen nu het account.** De indeling van
  het startscherm (welke secties, hoeveel ze tonen) en een deel van de weergave-instellingen
  (tracknummer, regels per rij, bitrate bij artiest, sorteren op schijf, limiet per genre,
  bevestigen voor het downloaden van een set) staan voortaan bij "Algemeen" en gelden op elk
  apparaat waarop is ingelogd, niet meer alleen op de telefoon waar ze gezet zijn.
- **De gekozen taal werkt nu ook door in de systeemschermen van de app**, niet alleen in de tekst
  van de webinterface zelf.

- **Nergens op de webspeler stond hoe de automodus aangaat.** De legacy handleiding
  (`ManualFragment`) legde uit dat het aansluiten op Android Auto het autoscherm zelf al opent en
  dat de "Automodus"-schakelaar alleen voor rijden zonder gekoppelde auto is — maar die tekst wordt
  met de handleiding zelf opgeruimd, en de instellingenpagina had alleen de schakelaar, zonder dat
  verhaal. Instellingen → Over MuMa heeft nu een sectie "Hoe werkt…" met die ene paragraaf. De rest
  van de handleiding beschreef schermen die de webspeler al op dezelfde manier toont, inclusief het
  verschil tussen vastgezette en gecachete nummers (`cacheSizeHelp` legde dat al uit) — daar hoefde
  niets bij.

- Inside de Android-app draait de nieuwe interface nu op de bestaande afspeeldienst: de webspeler logt zichzelf in met de server en het account die op de telefoon staan, geeft de wachtrij aan de notificatie en Android Auto door, en vindt na een herstart van de WebView zijn plek in het nummer terug. In de browser verandert er niets.

- **Instellingen krijgen een "Apparaat"-tab in de app.** Wifi-only downloads, cachegrootte en
  "Cache wissen", max. bitrate voor mobiel en wifi, preload-aantal, hervatten bij koptelefoon of
  bluetooth, hardware-audio-offload, automodus en het scrobble-schakelaartje waren tot nu toe
  alleen bereikbaar via het klassieke instellingenscherm, dat vanuit de nieuwe interface nergens
  aan te klikken was. De tab is alleen zichtbaar in de app zelf; een rij onderaan opent het
  klassieke scherm voor alles wat hier niet staat.

- **Een crashrapport uit de nieuwe interface leest nu als een verhaal in plaats van een leeg
  logbestand.** Navigatie, afspelen, wachtrijwijzigingen, waarderingen, downloads, in- en uitloggen
  en instellingen schrijven allemaal één regel naar hetzelfde actielogboek dat de Kotlin-app al
  gebruikte; een JavaScript-fout die de app nooit toonde, komt er nu ook met stacktrace in terecht.
  Een rapport vermeldt voortaan ook of het uit de webinterface of de klassieke app komt, welke
  frontend-build draaide en welke WebView hem toonde.

- In de app is de muziek die je gedownload hebt nu zonder verbinding te doorbladeren en af te spelen — nummers, sets, albums, artiesten, genres, labels, favorieten en zoeken komen van de telefoon zodra de server niet bereikbaar is — met een eigen Downloads-pagina die per album en per set laat zien wat er staat, hoe groot het is en hoe ver een download is, een downloadteken in de nummerlijst en een maatvraag voordat je een set van honderden megabytes binnenhaalt. In de browser verandert er niets.

- **De speler kende geen songtekst.** De legacy `LyricsFragment` haalde die op via
  `getLyrics(artist, title)`, maar de webspeler had nergens een knop. LMS beantwoordt songtekst
  wel echt — `handleGetLyricsBySongId` in `MediaRetrieval.cpp` leest `db::TrackLyrics`, gevuld door
  de scanner uit ingesloten tags en bijpassende `.lrc`-bestanden — en `TrackList.svelte` toonde
  hem al voor een rij in de bureaubladlijst. `Player.svelte` haalt de songtekst nu op voor wat er
  speelt (per track-id, niet de fuzzy artiest/titel-match die `LyricsFragment` deed) en toont een
  knop zodra er tekst is: een bottom sheet in het "Nu speelt"-scherm op de telefoon, een klein
  paneel naast de wachtrijknop op het bureaublad. Zonder songtekst voor het spelende nummer
  verschijnt er niets — geen "geen songtekst"-plek die voor de meeste nummers leeg blijft staan.

- **De setup-wizard opende na een update; de webspeler heeft geen wizard.** Voor
  muma-mobile 7.0.0 moet de app na een update op Home openen met bestaande downloads, niet op een
  carrousel — maar wat er veranderd is moet een luisteraar nog wel te weten komen. `MumaSystem`
  geeft nu `appVersion()` (de `versionName` van de APK, iets anders dan de bundle-versie die
  `platform.diagnostics` stuurt: dat is een git-hash zonder relatie tot `CHANGELOG.md`-koppen). Een
  nieuwe `mobileReleaseNotes.js` vergelijkt die met een in `localStorage` onthouden vorige versie
  en toont, alleen bij een echte upgrade en nooit bij een nieuwe installatie, wat er veranderd is —
  via dezelfde `ReleaseNotesModal.svelte` die `TopBar.svelte` al gebruikt voor de release notes van
  de LMS-server zelf. De tekst komt uit muma-mobile's eigen `CHANGELOG.md`, gelezen via een nieuwe
  `MumaSystem.releaseNotes()` uit hetzelfde asset-bestand dat `copyChangelog` al voor de oude
  "Wat is er nieuw"-knop klaarzet — niet gebundeld in de webspeler zelf, want die build draait in
  een Docker-context die alleen `services/frontend` ziet. Tonen kost nog steeds geen netwerkverzoek:
  de tekst zat al in de APK.

- **Een tik op de minispeler op de telefoon opende voorheen niets.** Die tik opent nu een full-screen
  "Nu speelt"-scherm (cover, titel/artiest, sterren, seekbar, shuffle/vorige/afspelen/volgende/herhalen,
  een equalizer- en een wachtrijknop), te sluiten via de chevron, een swipe omlaag op de cover of de
  terugknop. De wachtrij opent op de telefoon voortaan als bottom sheet in plaats van nergens. De deep
  link die de melding op Android gebruikt (`player`) opent dit scherm op de telefoon; op desktop blijft
  hij het wachtrijpaneel openen. Shuffle en herhalen sturen op de telefoon (native afspelen) nog
  dezelfde browser-only stores aan als altijd — dat op de afspeeldienst zelf laten werken is een
  bekende openstaande vervolgstap, niet in deze wijziging opgelost.

- **Presets op het startscherm.** De tegels die de Kotlin-app al jaren heeft — "Random Uptempo",
  "Recent Raw Hardstyle" — staan nu ook in de webspeler, bovenaan Home, in dezelfde lijst: het
  zijn de dynamische afspeellijsten van je account in MuMa, dus een tegel die op de telefoon is
  gemaakt staat op het web en andersom. Tik opent de lijst met een afspeelknop; het menu op die
  pagina verwijdert de preset. Nieuw maken kan vanaf elke gefilterde lijst (genre, label, jaar,
  Alle nummers/Sets) met "Opslaan als preset": de huidige filterstand — genre, jaar, minimaal
  aantal sterren, sortering, nummers of sets — wordt bewaard in het formaat dat de Kotlin-app
  leest. Afspelen gaat via dezelfde `getSongs`-aanroep als op de telefoon, dus tegels met meerdere
  genres of jaren werken ook.

- **MuMa Voice in de webspeler.** De microfoon werkt nu ook op het Svelte-scherm, niet alleen in de
  Kotlin-app: een microfoonknop op het zoektabblad (alleen zichtbaar als het toestel spraakherkenning
  heeft), en de tegel/snelkoppeling/auto-modus openen dezelfde nieuwe pagina in plaats van het
  startscherm. Wat je zei en hoe MuMa dat begreep staat op het scherm; bij een dubbelzinnige naam
  komt de vraag met tikbare keuzes ("bedoel je het album of de afspeellijst?") en luistert de
  microfoon meteen weer mee voor een gesproken antwoord. Een duidelijke opdracht speelt meteen af,
  via dezelfde `getSongs`/`getAlbum`/`getPlaylist`-aanroepen en wachtrij als een preset of een
  Home-tegel. "Wat verstaat MuMa" en een inklapbare diagnoseleist met de laatste verzoeken zitten
  er ook op. De spraakherkenning en de audio blijven native — alleen het scherm eromheen is nu web;
  het woordbegrip (`core/voice`, de genre-, artiest- en labelherkenning) is ongewijzigd Kotlin en
  draait via de nieuwe `MumaSpeech.interpret`-bridge.

- **Sets kregen geen eigen afspeelknoppen.** De speler (desktop-balk en Now Playing) toont voortaan
  −30 s/+30 s-knoppen naast play/pause zodra het geladen nummer een set is (dezelfde tien-minuten-
  grens als de rest van de app, `isSet` uit `downloads.js`), rekent positie en duur in h:mm:ss in
  plaats van m:ss, en vervangt de klikbare balk door een `<input type="range" step="1">` zodat een
  positie in een bestand van twee uur ook echt te verslepen is; de pijltjestoetsen op die balk
  springen ±30 s in plaats van de standaard 1 s-stap. Songs-modus verandert niet. `TrackList`'s
  duurkolom toont voor een set nu h:mm in plaats van m:ss, per rij bepaald (niet per modus), zodat
  een gemengde lijst nooit de verkeerde vorm toont.
- **Setpositie volgde het apparaat niet.** Een nieuwe `setResume`-sleutel in de account-
  instellingenblob (dezelfde blob als favoriete genres en taal) onthoudt de laatst gespeelde positie
  per werk-id, met een cap van 50 en een throttle van 15 s tijdens het afspelen plus een directe
  schrijving bij pauzeren, wisselen van nummer en `beforeunload`. Bij het starten van een set met een
  bewaarde positie tussen de eerste en de laatste minuut springt de speler er automatisch naartoe en
  toont een meldingsknop "Opnieuw" om alsnog van voren te beginnen. Werkt zowel via de browser-
  engine als via de native speeldienst (`platform.player.state()`).

- **De nieuwe interface kende geen rijscherm.** De Kotlin-app opent al jaren automatisch een groot
  scherm — vorige/afspelen/volgende, ster-beoordeling, microfoon voor spraak, genre- en
  favorieten-mixtegels — zodra de telefoon een gekoppelde auto ziet, maar de webspeler in de nieuwe
  schil had daar niets tegenover: een auto die verbond liet de gebruiker gewoon op het gewone scherm
  zitten.
- Een `CarModeView` op route `car` doet nu hetzelfde: transport en beoordeling lopen via de
  bestaande `platform.player`/`setRating`-paden (geen tweede wachtrij-eigenaar), de mixtegels
  starten dezelfde shuffle-wachtrij als de Kotlin-tegels deden, en het scherm opent zelf zodra
  `platform.system.carConnected` afgaat of, bij een koude start die de verbinding al mist, via een
  eenmalige `carState()`-check. Wegtikken sluit het scherm voor de rest van deze rit — een dubbel
  signaal van dezelfde verbinding (denk aan een bluetooth-hapering) opent het niet opnieuw — en de
  volgende keer dat de auto verbindt, wel weer. Ook bereikbaar via het overflow-menu.

- **Radio en het nieuws van het uur speelden helemaal niet op de telefoon in de nieuwe interface.**
  Radio stuurt het `<audio>`-element rechtstreeks aan om halverwege een nummer in te haken, en een
  bulletin speelt van een blob-URL af; de schil heeft geen van beide -- `PlaybackService` bezit de
  afspeeldienst. Beide knoppen gaven meteen op met "speelt nog niet in de app". De speeldienst had
  die twee al, ingebouwd voor Android Auto en Assistent (`RadioPlaybackController`/`RadioSync.kt`,
  `NewsPlaybackController`/`NewsQueueRules.kt`): een kanaal starten is één media-id die
  `onAddMediaItems` al herkent, een bulletin is één sessiecommando dat al beide kanten van de wissel
  op zich neemt, inclusief het opnieuw intunen van radio als die aan stond. Twee nieuwe
  plugin-methoden (`startRadio`/`stopRadio`/`toggleNews`) en twee velden op `state()`
  (`radioChannel`/`newsPlaying`) zijn de hele uitbreiding; de webinterface merkt zo ook een kanaal of
  bulletin op dat van buiten de WebView kwam -- Android Auto, Assistent, of een WebView die is
  herschapen terwijl er iets speelde -- en bouwt de juiste knoppen dan terug op in plaats van een
  gewone wachtrij te tonen.

### Changed
- **Elk verzoek aan de server loopt nu via één resolver, en er verandert niets zichtbaars.** Zo'n
  twintig bestanden deden zelf `fetch(\`/rest/...\`)` op basis van de pagina-origin — cover art,
  streams, playlists, scans — terwijl `/api/*`-aanroepen al via `apiBase()`/`mumaApiUrl` liepen.
  Binnen de komende Capacitor-schil is de pagina-origin `https://localhost`, dus zo'n relatieve
  `/rest/...` zou tegen de WebView praten in plaats van tegen de muziekserver. `restUrl()` in
  `src/lib/store.js` bouwt nu elke Subsonic-URL op `credentials.url`, met dezelfde terugval naar
  `window.location.origin` die er al was; op het web is dat exact dezelfde string als een relatieve
  fetch. De derde kopie van die terugval in `LoginPage.svelte` is vervangen door de helper. Fase 0
  van `docs/designs/universal-ui/`.

- **Home en de overzichten toonden op een telefoon twee kaarten per rij, halve schermbreedte
  groot, zodat één sectie al de hele hoogte innam en de pagina eindeloos doorscrolde.** Onder
  Tailwinds `md`-grens (en waar dat niet volstond, achter de `isMobile`-store) zijn Home-secties nu
  een horizontaal scrollende rij van vaste kaarten van 140 px — zoals Spotify's eigen "Daily Mix"-
  rijen — in plaats van een raster van twee kolommen. Genres, labels, podcasts, festivals, jaren en
  lineups (allemaal via `CollectionGrid`) en de albums-, artiesten- en zoekresultatenrasters gaan
  naar drie kolommen met kleinere tegels. Playlists krijgen op de telefoon een lijst met een 56 px
  miniatuur per rij in plaats van een tegelraster — dat is wat Spotify's eigen Bibliotheek-tab ook
  doet, terwijl de genre-/labeltegels een raster blijven omdat Spotify die ook zo toont. Een
  ontbrekende cover (het MuMa-merkteken) staat nu klein, gedempt en ingekaderd in plaats van
  levensgroot en wit uitgelicht. Desktop (vanaf `md`) is in geen van deze schermen aangeraakt.

- Op de telefoon nemen de filters van Songs, Sets en Playlists niet langer een half scherm in voordat de eerste rij komt. Genre, Jaar, Rating, Sorteren en een Ongewaardeerd-schakelaar staan nu in één horizontaal scrollbare rij chips; een actieve chip toont zijn waarde en is groen gevuld, met een × om hem te wissen. Een tik opent een van onderen inschuivend paneel (nieuw `BottomSheet.svelte`) met de opties, in plaats van een `<select>`. Zoeken is een loep-chip die uitklapt in plaats van een altijd zichtbaar veld. Playlists krijgt dezelfde aanpak: Favorieten/Alle/Van mij/Openbaar/Privé als chips in één rij, een sorteerchip met veld én richting in het paneel, en het aantal staat nu in de sectieregel ("296 playlists") in plaats van los rechts te zweven. De nummerlijst toont geen "TITLE"-kolomkop meer op de telefoon en de sterren staan onder de artiestnaam. Desktop blijft ongewijzigd.

- De navigatie op de telefoon is nu Spotify-stijl: onderaan staan alleen nog Home, Zoeken en Bibliotheek — Songs/Sets is geen tab meer maar een modus-knop boven Home, Zoeken en Bibliotheek, Downloads is een keuzeknop in de Bibliotheek-tab geworden en Beheer zit in het profielmenu. De Zoeken-tab toont, zolang er niet gezocht wordt, een raster met alle sidebar-secties (genres, labels, podcasts, festivals, jaren, lineups, artiesten, albums, memories, geschiedenis, luisterstatistieken, favorieten) zodat niets van de desktop-sidebar op de telefoon onbereikbaar blijft. De desktop-indeling verandert niet.

- **Afspelen zit vanaf nu achter een platformlaag, en er verandert niets zichtbaars.** `Player.svelte`
  deed alles zelf met zijn `<audio>`-element — laden, spelen, spoelen, volume, de equalizer, de
  Media Session, en een eigen timer omdat de browser van de tv geen `timeupdate` stuurt — en dat is
  precies het stuk dat op een telefoon door `PlaybackService` gedaan wordt. Die motor staat nu in
  `src/lib/platform/`, achter één `platform`-object met `player`, `storage`, `speech`, `diagnostics`
  en `system`; de implementatie wordt één keer gekozen bij het importeren, en dat ene punt is waar
  een Capacitor-schil zich later inhaakt. Wachtrij, shuffle, radio, nieuws en jam-sync bleven staan
  waar ze stonden. Dezelfde DOM, dezelfde knoppen, dezelfde 1.318 bestaande tests ongewijzigd groen.
  Fase 0 van `docs/designs/universal-ui/`.

### Fixed
- **Minispeler op de telefoon groeide tot drie keer zijn hoogte** zodra het huidige nummer geen
  hoes had. De placeholder-hoes krijgt op de telefoon een rand van 18%, en die werd berekend
  over de hele balk in plaats van over de 44px van het hoesje. Het hoesje staat nu in zijn
  eigen kader, dus de rand blijft binnen de 44px.

- **De webinterface hielp een lus op de telefoon-app in stand houden die het afspelen nooit liet
  starten.** Een commando van de afspeeldienst zonder nummer en zonder wachtrijlengte — de
  tussentoestand van een wachtrijwissel die zichzelf nog aan het bijwerken was, niet een echte
  "vorige" of "volgende" — werd tot nu toe gelezen als een stap in de eigen wachtrij, wat
  `currentTrack` verplaatste en een nieuwe wachtrij naar de telefoon stuurde. De hand-off stapt nu
  niet meer op een leeg commando, en onthoudt bovendien bij welke wachtrij en positie al eerder is
  gestuurd, zodat dezelfde stand nooit twee keer wordt doorgegeven — ook niet wanneer de
  afspeeldienst zelf tijdelijk een verouderde stand teruggeeft.

- **"Toevoegen aan wachtrij" bereikte de afspeeldienst op de telefoon nooit.** De webinterface
  beslist wat er in de wachtrij staat maar houdt hem niet vast, dus elke wijziging reist als één
  `setQueue` met de héle lijst. Stond het spelende nummer niet in die lijst — en dat is de gewone
  toestand na een kaartje op het startscherm of een zoekresultaat — dan werd de lijst weggegooid en
  ging alleen dat ene nummer over. Het toegevoegde nummer zat niet in het bericht en werd dus nooit
  gespeeld; vóór 0.60.2 begon de spelende set er ook nog van vooraf aan. Een nummer zonder lijst
  erachter gaat nu vóór de wachtrij in plaats van ernaast, precies zoals de browser met dezelfde
  stores doet, en toevoegen, hierna afspelen, verwijderen, herordenen, leegmaken en "speel deze
  lijst vanaf hier" sturen allemaal de complete wachtrij met de juiste positie mee. De UI volgt
  daarnaast een `next` van de notificatie nu ook als het bericht over de nieuwe status nog niet was
  aangekomen — twee losse berichten over de brug lieten de app een nummer achterlopen.

- **De knop "Sets" onderin de app navigeerde niet.** Een tik zette de weergave op `sets` terwijl de
  modus nog op `songs` stond, en het effect dat die twee gelijk houdt zette de weergave meteen weer
  terug: het adres bleef `/songs` en de merkkleur bleef groen. Beide helften verhuizen nu samen, en
  de schakelaar in de zijbalk op een groot scherm blijft werken zoals hij werkte.

- **Management en Bibliotheek meldden "Not available without a connection" terwijl de telefoon
  gewoon online was.** `subsonicJson()` zette de `offline`-vlag op elke netwerkfout, ook een enkele
  time-out of een niet-JSON antwoord (een proxy-foutpagina gooit een `SyntaxError` uit
  `response.json()`, geen `TypeError` van `fetch` zelf, maar werd tot nu toe hetzelfde behandeld).
  Eenmaal gezet bleef de vlag staan tot het enige andere schrijfpunt, het Android
  connectivity-event, weer *veranderde* — schermen zonder eigen offline-bron (playlists, feeds,
  memories, listening, Management) lieten daarna hun "unavailable"-melding zien tot een herstart,
  terwijl Songs gewoon doorwerkte omdat die view wél een lokale bron heeft. Een mislukte aanvraag
  vraagt nu `storage.isOffline()` opnieuw voor de vlag omgaat; bevestigt het apparaat dat niet, dan
  reist de oorspronkelijke fout gewoon door naar de aanroeper, precies zoals in de browser. Staat de
  vlag nog van een eerdere blip, dan wordt diezelfde controle ook vóór het overslaan naar de
  lokale bibliotheek gedaan, zodat een herstelde verbinding meteen weer geprobeerd wordt in plaats
  van te wachten op een los connectivity-event.

- **Now Playing op de telefoon lag onder de kop en de onderbalk.** Het schermvullende
  Now Playing zit in de speler, en die had als rasteritem een eigen stapelcontext (`z-20`);
  de plakkende zoekkop (`z-30`) en de onderbalk tekenden er overheen, dus de sluitknop,
  "speelt uit" en de equalizer/wachtrij-knoppen onderaan waren onbereikbaar. De speler staat
  nu boven beide. De sluitknop wijst bovendien omlaag (hij wees omhoog), en de knoppen op de
  instellingenschermen ("Wijzigingen opslaan", "Cache wissen", ...) breken op de telefoon
  niet meer over twee regels.

- **Wachtrij en nummerlijsten op de telefoon.** Een nummer zonder hoes kreeg in de rij een
  placeholder van ~240px (de 18%-rand van de placeholder rekende over de hele rij), en de tabel
  was breder dan het scherm: de titelkolom rekte mee met de langste titel en de
  hover-knoppenkolom nam 100px in zonder ooit zichtbaar te zijn. De placeholder-rand geldt nu
  alleen voor de tegels, de tabel heeft een vaste kolomindeling zodat titels afkappen, en de
  knoppenkolom is op de telefoon weg — behalve in de wachtrij en op een afspeellijst, waar
  "verwijderen" en de download-knop altijd zichtbaar zijn.

- **Uitloggen in de Android-shell deed zichtbaar niets.** `handleLogout` wiste alleen de
  localStorage-cache en herlaadde de pagina; de credentials op de telefoon zelf bleven staan.
  `bootstrapShell()` las ze bij het opnieuw opstarten gewoon terug uit Kotlin en logde de
  gebruiker meteen weer in, dus de knop leek dood. `handleLogout` wacht nu eerst op het nieuwe
  `platform.system.signOut()` — in de shell wist dat het wachtwoord, de muma API-key/refresh-token
  en de wachtrij op de telefoon; in de browser is het een no-op die meteen resolvet — voordat de
  rest van de sessie wordt gewist en er herladen wordt. Na een nieuwe aanmelding via de Svelte
  LoginPage in de shell schrijft `platform.system.saveCredentials()` het paar ook weer terug naar
  Kotlin, zodat downloads, Android Auto en de klassieke interface dezelfde sessie zien. Een
  Google-aanmelding in de shell doet dat nog niet — dat blijft web-only, zie de code-comment bij
  `handleGoogleResponse`.

- **De playlists-tab en playlist-detailpagina omzeilden de offline-schakelaar volledig.** `Dashboard.svelte`
  haalde `getPlaylists` en `PlaylistView.svelte` haalde `getPlaylist` met een losse `fetch` op, terwijl
  elke andere lijst via `subsonicJson()` gaat -- die valt terug op `platform.storage.query` zodra de
  shell geen route naar de server heeft. Beide gaan nu via `subsonicJson()`, en `playlists`/
  `playlist-detail` staan in `viewHasOfflineSource` zodat de weergave dat ook weet. Zie het
  gelijktijdige mobile-fragment voor het `OfflineSubsonic`-antwoord dat dit nu daadwerkelijk kan
  beantwoorden.
- **Er bestond een tweede, ongebruikte "wifi only voor downloads"-instelling.** De `downloadsWifiOnly`
  store in `store.js` werd naar het account gesynchroniseerd, maar de enige plek die hem kon
  schrijven rendert nooit (de rij bestaat alleen als `platform.storage.supported`, en dan schrijft
  `GeneralSettings.svelte` al rechtstreeks de echte Kotlin-instelling). Die dode store, zijn
  `persist`-regel en de account-sync zijn verwijderd; `Settings.isWifiRequiredForDownload` (geschreven
  via de `wifiOnly`-sleutel) is de enige plek waar dit nog vandaan komt. `DownloadService` bleek die
  vlag al te lezen en een download op mobiel netwerk al te laten wachten tot wifi terug is.

- **Shuffle en herhalen deden niets op de telefoon, en de muziek stopte aan het einde van de
  wachtrij.** De webspeler besliste zelf welk nummer volgde -- een eigen shuffle-spoor, een eigen
  herhaalteller -- terwijl de afspeeldienst op de telefoon zijn eigen, vaste volgorde afspeelde en
  daar nooit iets van hoorde. De knoppen zetten alleen een vlag in de webinterface; op de telefoon
  veranderde er niets aan wat er werkelijk speelde, en een wachtrij die opraakte stopte gewoon. Beide
  standen gaan nu naar de afspeeldienst zelf, die ze al kent (`shuffleModeEnabled`/`repeatMode`), dus
  Android Auto, de melding en het einde van de wachtrij gedragen zich er meteen naar. In de browser
  verandert er niets.

- **In de nieuwe interface op de telefoon begon een aangetikt nummer nooit te spelen.** De
  afspeeldienst kreeg de wachtrij wél binnen, maar bleef op pauze staan: het `setQueue`-bericht
  vroeg niet om te starten, en het `load`-bericht dat dat daarna moest doen werd weggegooid door de
  bewaker "de dienst staat al op dat nummer" — want het aannemen van een wachtrij zet de dienst
  meteen op die positie. Een kaartje op het startscherm of een zoekresultaat kwam nog verder: dat
  zet alleen het huidige nummer en geen wachtrij, en de dienst kan alleen spelen wat hij vasthoudt,
  dus daar gebeurde helemaal niets. Het startverzoek reist nu mee met de wachtrij, en een nummer
  zonder lijst erachter wordt zelf de wachtrij. De unit-test hierop kon dit niet zien: de nagemaakte
  speler verzette het huidige nummer niet bij `setQueue`, zoals de echte plug-in dat wel doet.

- **Een map met `.mp3` in de naam werd elke tagronde als nummer geparsed, en faalde elke keer.**
  `parse_folder` zocht bestanden met `Path.glob`, en die matcht op naam — dus
  `/mnt/music/EPs/This is Terror/TITCD018 - Srb - Rocket Science (2015).mp3`, een map, kwam
  binnen als kandidaat. `stat()` en `needs_processing` slagen allebei op een map, dus het liep
  pas stuk in mutagen, als `IsADirectoryError: [Errno 21]`. Dat is vijf `Parse_song failed` per
  nacht op productie (2026-09-10) die nooit minder konden worden: geen enkele volgende ronde
  maakt een map leesbaar als audio. De glob levert nu alleen echte bestanden op.

## [0.60.2] - 2026-09-11

### Fixed
- **LMS stierf zodra een andere schrijver zijn database vasthield.** De verbinding zette
  `journal_mode=WAL` en `synchronous=normal`, maar geen `busy_timeout` — dus stond die op nul, gaf
  SQLite bij elke botsing meteen `SQLITE_BUSY`, en bij het opstarten kwam dat als onafgevangen
  exception uit `ANALYZE`: proces weg, autoheal herstart, volgende opstart botst opnieuw. Twee
  achtergrondschrijvers van muma kostten de server op één dag 102 en 43 herstarts.
- `busy_timeout=15000`: LMS wacht nu tot vijftien seconden op een slot in plaats van te sterven. WAL
  laat lezers al altijd door, dus dit serialiseert alleen ooit twee schrijvers — en een schrijver van
  muma houdt het slot een paar seconden, niet vijftien.
- **Een rating vanaf de telefoon kwam als 500 terug zolang muma zijn uursync draaide.** De
  song-versie-sync liep 285.000 tracks langs met per rij een `UPDATE ... WHERE` die alleen bij een
  verschil iets schreef — maar een UPDATE die niets raakt neemt het schrijfslot van SQLite tóch, van
  de eerste rij van een chunk tot de commit. De artiestafbeeldingen deden hetzelfde in één transactie
  van 11.762 rijen. LMS wacht daar niet op: een Dbo-transactie leest eerst en schrijft dan, en een
  lezer die wil schrijven terwijl het slot bezet is krijgt van SQLite direct `SQLITE_BUSY`, zonder
  dat de busy-timeout meedoet. Dus `insert into "rated_track" ... database is locked`, een 500 in de
  app, en de rating weg. Tien minuten per uur, elf keer in de logs op één ochtend.
- Beide syncs lezen nu eerst en schrijven alleen het verschil, in korte transacties: de
  versie-kolommen in batches van honderd, de afbeeldingen per artiest. Na de eerste ronde klopt bijna
  alles al, dus wordt er bijna niets geschreven en is het slot bijna nooit bezet.

## [0.60.1] - 2026-09-11

### Fixed
- **"Algemene API-fout", "Playback could not start", "Scrobble failed HTTP 500" — één oorzaak.** Elk
  geauthenticeerd verzoek deed een schrijftransactie op het auth-token: gebruiksteller ophogen,
  `last_used` bijwerken. Dbo versioneert die rij, dus twee verzoeken met hetzelfde token — het nieuwe
  startscherm van de app vuurt er meerdere tegelijk af — laden allebei versie 165, de tweede
  schrijver verliest, en dát verzoek wordt afgebroken met `Uncaught exception from handleRequest`.
  Negen keer in een uur op één token; om 08:55:36 drie binnen een halve seconde: stream, scrobble en
  cover art tegelijk.
- De schrijfactie gebeurt nu alleen als hij ertoe doet: een token met een gebruikslimiet houdt zijn
  teller, en `last_used` schuift hooguit één keer per minuut in plaats van bij elke aanroep. Al het
  andere blijft een leesactie.
- Verliest een verzoek die race alsnog, dan wordt dat genegeerd in plaats van het verzoek af te
  breken. De andere kant heeft dezelfde rij net bijgewerkt; het token was geldig toen we keken, en
  een aanroep laten mislukken over een boekhoudkundige botsing is de ene uitkomst die niet kan.

## [0.60.0] - 2026-09-11

### Added
- **Het startscherm van de app is instelbaar.** Onder Instellingen → Startscherm krijgt elke sectie
  één keuze — **knop**, **overzicht** of **uit** — plus hoeveel hij toont. Alles op knop vult samen
  één raster bovenaan (Memories, Release radar, Dagelijkse mix, favorieten, shortcuts, in vaste
  volgorde), alles op overzicht houdt zijn eigen kop eronder. Favorieten staan er nieuw bij en
  beginnen uit. `HomeLayout.resolve()` is een pure functie over de opgeslagen waarden, dus wat een
  bestaande gebruiker na de upgrade krijgt is te testen zonder Android: het oude memories-vinkje zet
  memories nog steeds uit, `home_shortcut_count` en `home_list_count` gaan ongewijzigd mee, en een
  waarde die de app niet kent valt terug op een standaard. Ontwerp in `docs/designs/home-sections/`.
- **Recent uitgebracht en Recent toegevoegd waren in 6.34.0 van het startscherm verdwenen.**
  `primary.xml` had vier vaste sectieslots en `MainFragment.render()` koppelde die op index aan de
  secties van de view model, dus de twee feeds namen de plekken van de twee recent-lijsten in — met
  hun "Meer"-knop, die daarna de verkeerde lijst opende. De slots zijn weg: er wordt er één
  geïnflate per sectie die de view model noemt, en de acties komen uit de sectie zelf.
- `HomeCard.key` was `type:itemId`, waardoor hetzelfde album dat zowel Favorieten als Shortcuts
  aanleveren één identiteit was en de diffing één van de twee knoppen liet vallen. De aanleverende
  sectie zit er nu in.
- De dagelijkse mix en de release radar hebben een eigen pagina op de telefoon
  (`trackCollectionFragment` met een `feed`-argument): MuMa's volgorde, geen filters eroverheen,
  niet sorteerbaar en geen paginering.

## [0.59.0] - 2026-09-11

### Added
- **De dagelijkse mix en de release radar staan nu ook in de web-UI en op de telefoon**, niet alleen
  in de auto. Op het startscherm staan ze bovenaan als twee rijen; "toon alles" opent de hele feed
  met een afspeelknop, op `/daily-mix` en `/release-radar`.
- **De rij die "Release Radar" heette op het webstartscherm was de radar niet.** Dat was
  `getSpotifyPlaylist?id=spotify:release_radar`: de hele bibliotheek onder tien minuten, gesorteerd
  op releasedatum — dezelfde lijst voor elke luisteraar, persoonlijk in naam alleen. MuMa's echte
  radar weet wat dit account draait en neemt de naam en de plek over. Het server-endpoint blijft
  bestaan voor wie het nog aanroept.
- Een feed die leeg terugkomt laat zijn rij weg in plaats van een kop boven niets te zetten. Leeg is
  een echt antwoord — er kwam deze week niets uit dat past — en dat hoort er anders uit te zien dan
  een lijst die nog laadt.

- **Productie wordt elke nacht om 02:00 nagelopen, en een fout die niemand had gezien wordt
  een fix-MR in plaats van een regel in een log.** `scripts/nightly-prod-check/` op de
  runnerhost leest `/health`, de containers, alle ERROR/CRITICAL-events van de laatste 24
  uur en de logstaarten via de API, vouwt ze tot vingerafdrukken en vergelijkt met een
  grootboek van eerdere oordelen. Alleen wat nieuw is, piekt of terugkomt gaat naar één
  Claude-run (`claude-opus-5`) met de skill `muma-nightly-prod-check`, die per punt een
  oordeel velt en bij een eenduidige codefout een MR naar `develop` opent met label
  `claude-nightly-fix` — maximaal twee per nacht, nooit gemerged zonder approval. Elke
  nacht eindigt in één ntfy-bericht op `music-management-claude`, verstuurd door de
  shell-supervisor uit een gevalideerd resultaat, dus ook een vastgelopen run meldt
  zichzelf. De MR-watcher merget nu alleen op approval van `muma` en een groene
  pipeline voor exact de te mergen revisie, en de drie automaten delen één lock op de
  clone.

### Fixed
- **De lms.db-sync liep zes keer per uur in plaats van één keer.** Er draait een tweede
  LMS-instantie (`alpha`) die de migratie naar databaseversie 118 nooit heeft gedraaid. De
  herhaalpoging uit 0.55.0 zag daardoor elke ronde "server nog niet gemigreerd" en herhaalde de
  vólledige pass — 285.360 tracks, ook voor de server die net correct was weggeschreven. Zes keer
  per uur, tegen een database die de speler open heeft staan.
- Een herhaalpoging gaat nu alleen nog over de servers die daadwerkelijk zijn overgeslagen. De eerste
  ronde dekt alles, elke volgende noemt precies de instantie waarop gewacht wordt — en de
  waarschuwing daarna zegt welke dat is, in plaats van hoeveel het er waren.

- **De versie-sync legde de speler plat.** LMS sterft aan een vergrendelde database — een
  onafgevangen exception, het proces stopt — en de sync hield dat slot vast: elke ronde alle 285.671
  rijen herschrijven, met dertig seconden geduld per statement en vijftien seconden tussen elke
  nieuwe poging. Resultaat: **102 herstarts** en een onbereikbare bibliotheek.
- De rolverdeling was omgekeerd. Dit is een achtergrondtaak en LMS is de speler; als beide hetzelfde
  slot willen, hoort degene naar wie niemand luistert te wijken. De wachttijd gaat van dertig
  seconden naar twee, het aantal pogingen van tien naar drie, en de pauze ertussen van vijftien
  seconden naar een minuut — wachten in plaats van duwen. Wat blijft liggen kost niets: de volgende
  ronde schrijft dezelfde rijen.
- **En er wordt alleen nog geschreven wat verandert.** De `UPDATE` draagt dezelfde vier waarden
  nogmaals als voorwaarde, dus een rij die het al goed heeft wordt niet aangeraakt. Na de eerste
  ronde is dat vrijwel alles: 285.000 ongewijzigde rijen per uur herschrijven is wat deze taak
  überhaupt in het pad van de speler bracht.
- **Een mislukte sync liet zijn verbinding open staan.** `sqlite_conn.close()` stond ná de
  `try`-body, dus bij een fout werd hij overgeslagen en bleef de transactie hangen — een slot dat
  niemand meer losliet. Nu in een `finally`.

## [0.58.0] - 2026-09-10

### Added
- De release radar en de dagelijkse mix zijn nu te starten vanuit de auto. MuMa rangschikt de feed
  en kent zijn tracks alleen bij bestandspad; de server kent ze bij id. Het nieuwe
  Subsonic-endpoint `getSongsByPath` legt die brug — het lost bibliotheekrelatieve paden op naar
  afspeelbare songs, in de volgorde waarin ze gevraagd zijn, en laat een pad dat de server niet
  heeft weg in plaats van de hele aanvraag te laten mislukken.
- `library_tracks.release_date`, elk uur overgenomen uit de server (`ORIGINALDATE`, anders `DATE`)
  door dezelfde lms.db-pas die gebruikers, playlists en song-versies al synchroniseert. Beide feeds
  filteren op een releasedatum en lazen die tot nu toe uit `library_track_audio_features`, een
  kolom die de ml-analyzer vult: op productie stond die nul keer gevuld en dekte hij een kwart van
  de bibliotheek, dus zowel de radar als de dagelijkse mix gaf altijd nul tracks terug. Twee
  bestanden onder één track die het oneens zijn leveren geen datum op, en een datum die verdwijnt
  wordt teruggeschreven als NULL — anders blijft een track na een tagcorrectie voor altijd in de
  radar staan.

### Fixed
- **De releasedatum-sync had de bibliotheek elk uur leeggehaald.** Productie draait twee servers:
  `stable`, waar iedereen van speelt, en `alpha`, waarvan de database zes weken oud is en 330.153
  tracks bevat tegen 338.662, met 194.816 datums tegen 238.207. De sync draaide per server, net als
  de sync die gebruikers, playlists en song-versies naar elke server schrijft — dus wie het laatst
  draaide besliste, en alpha zou zo'n 43.000 datums wissen en de 8.500 tracks die hij nooit gezien
  heeft leegmaken. Een feit dat je *uit* de servers leest moet je over alle servers samen beslissen
  voordat je iets wegschrijft; dat is de omgekeerde richting van de syncs ernaast en vraagt de
  omgekeerde opzet. "Deze server kent dit bestand niet" en "dit nummer heeft geen datum" zijn nu
  twee verschillende antwoorden.
- **`library_tracks.release_date` kent drie toestanden en het verschil tussen twee ervan telt.**
  NULL betekent dat geen enkele server het bestand heeft — een gat, en de feed valt dan nog terug op
  de kolom van de ml-analyzer. De lege string betekent dat een server het bestand wél heeft en er
  geen datum is waar iedereen het over eens is; dat is een besluit, en de feed respecteert het in
  plaats van terug te vallen op precies de waarde die zojuist tegengesproken werd. Daarom leest
  `feeds/queries.py` nu een CASE en geen COALESCE.
- **Een jaartal naast een dagdatum is precisie, geen tegenspraak.** Een FLAC met `2026` en een MP3
  met `2026-09-04` zijn één release op twee precisies; `2019` naast `2026-09-04` is dat niet en
  levert geen datum op. De sync gooide het jaartal eerder weg vóórdat hij op tegenspraak controleerde.
- **De feeds in de auto deden niets na een herstart van de dienst.** Een tik komt binnen op de
  session-callback-thread, en daar werd de netwerkcall rechtstreeks gedaan: op de main thread levert
  dat `NetworkOnMainThreadException` op, wat de app opving als "lege feed" — een knop die stilletjes
  niets doet. Loopt nu via de service-scope, net als de sterren- en random-paden ernaast.
- De tweede feed-cache naast de repository is weg. Die kende dag noch server, dus na middernacht
  speelde "alles afspelen" de ranglijst van gisteren, en na het wisselen van account of server die
  van de vorige gebruiker — met de track-ids van de vorige server. De cache die overblijft is op
  slug, dag én server gesleuteld, en onthoudt een half opgeloste feed niet meer voor de rest van de
  dag.

## [0.57.1] - 2026-09-10

### Fixed
- **De sync gaf het op zodra LMS zijn database even vasthield.** Bij de deploy van 0.56.0 startte LMS
  zijn eigen scan, de database zat op slot, en de sync stopte na **één van de 285.332 tracks**.
  Daarna probeerde niets het opnieuw, want hij draaide alleen bij het opstarten — dus LMS werkte een
  dag lang met een verouderd beeld en toonde nog gewoon elke kopie van een nummer.
- Een lock is de server die werkt, geen fout. Een blok dat op slot loopt wordt nu afgewacht (tien
  pogingen, vijftien seconden ertussen) in plaats van de hele ronde weg te gooien, en de wachttijd op
  een statement gaat van 5 naar 30 seconden — vijf was precies te kort voor een scanstap. Een blok
  dat op slot blijft wordt overgeslagen en geteld; de volgende ronde schrijft dezelfde rijen.
- Een fout die géén lock is wordt niet afgewacht: wachten op een kapot schema helpt niemand en
  begraaft de echte melding.
- **En de sync draait nu in een lus, niet alleen bij het opstarten.** De versie-worker groepeert
  ongeveer 500 tracks per uur zolang hij achterstand heeft, en wat hij leert bereikte de server pas
  bij de volgende deploy. Elk uur, in te stellen met `LMS_DB_SYNC_SLEEPTIME`.

## [0.57.0] - 2026-09-10

### Added
- **Een Room-schema dat van vorm verandert zonder van versienummer te veranderen laat CI nu vallen.**
  `services/muma-mobile/app/schemas/identity-hashes.json` legt de identity hash van elk geëxporteerd
  schema vast, en `tests/ci/test_room_schema_versions.py` vergelijkt. Zo'n wijziging was tot nu toe
  een schone diff in een gegenereerd bestand, en de app merkte het pas op de telefoon van iemand die
  zijn cache al gevuld had.

## [0.56.0] - 2026-09-10

### Added
- **`canonicalOnly` is een filter in de query geworden, geen lus die pagina's bij elkaar scant.** De
  webspeler klapt rijen samen door in batches door te scannen tot een pagina vol is — dat moest, want
  de oude heuristiek was niet in SQL uit te drukken. `is_canonical` wel: één predicate in de gedeelde
  queryopbouw van `find_advanced` en `countAdvanced`, waardoor paginering, sorteren én tellen het
  onderling eens blijven.
- Het predicate laat een track zonder groepering expliciet staan
  (`is_canonical <> 0 OR work_id IS NULL`). Alleen op `is_canonical` filteren zou de helft van de
  bibliotheek laten verdwijnen zolang de worker zijn achterstand wegwerkt.
- Een `workId` schakelt het filter uit: alle versies van één nummer opvragen en samenklappen tot één
  ervan zijn tegengestelden, en dat mag niet van de volgorde van parameters afhangen.

## [0.55.0] - 2026-09-10

### Added
- **`getSongs` accepteert nu `workId`,** zodat ook de app alle versies van één nummer kan opvragen.
  Die filter zat alleen in `getSpotifyTracks`, en de app bladert via `getSongs` — een versielijst die
  alleen de web-UI kon opvragen zou de telefoon een canonical laten tonen waar hij niet langs kan
  kijken.

### Fixed
- **De lms.db-sync gaf het op als de server nog aan het migreren was.** Bij een deploy herstarten
  beide diensten tegelijk en muma wint meestal: hij synchroniseert vóórdat de server zijn eigen
  schemamigratie heeft toegepast, ziet geen versiekolommen en slaat over. Overslaan is juist —
  schrijven in een schema dat halverwege een migratie staat is precies wat je niet doet — maar er
  kwam daarna niets meer terug, dus de kolommen bleven leeg tot iemand de container met de hand
  herstartte.
- Dat gebeurde bij de deploy van 0.54.0: de sync sloeg over om 20:16, en zonder die handmatige
  herstart had die release een functie uitgebracht die stilletjes niets deed.
- De sync probeert het nu opnieuw zolang een database om die ene reden is overgeslagen: zes pogingen,
  een minuut ertussen, en daarna een waarschuwing met hoeveel servers nog niet klaar zijn. Alles
  anders — een vergrendelde database, een onbereikbare server, helemaal geen lms.db — is al
  best-effort binnen de sync zelf en krijgt hier bewust geen tweede ronde.
- De logregel zegt nu ook wélke server hij overslaat. Er draaien er twee, een stabiele en een alpha,
  en een regel zonder naam kost je de tijd om dat uit te zoeken.

## [0.54.0] - 2026-09-09

### Added
- **LMS weet nu welke bestanden hetzelfde nummer zijn.** muma bepaalde dat al — het heeft de
  label-provenance en de downloadarchieven die beslissen welke versie wint, en LMS heeft geen van
  beide — maar het bleef in muma's eigen database staan. De server krijgt vier kolommen op `track`
  (`work_id`, `is_canonical`, `version_kind`, `version_score`, migratie naar databaseversie 118) en
  muma vult ze in dezelfde lms.db-ronde die al gebruikers, playlists en artiestafbeeldingen
  synchroniseert. Geen endpoint, geen API-sleutel, geen HTTP in het bladerpad.
- Het Subsonic-antwoord voor een nummer draagt `workId`, `isCanonical` en `versionKind` mee. Er wordt
  **niets gefilterd**: de web-UI heeft juist alle versies nodig om ze tot één regel te bundelen en de
  rating en genres van die bundel op te tellen. Additieve velden; bestaande clients merken niets.
- **De brug is het bestandspad**, want een LMS-track-id en een muma-track-id hebben niets met elkaar
  te maken. `library_paths.candidate_paths()` kent elke schrijfwijze die het proberen waard is en
  wordt hier hergebruikt in plaats van een tweede matcher — twee kopieën van die regel die uit elkaar
  lopen is precies hoe gespiegelde ratings ooit op een dood id belandden.
- **Alles wat onbekend is blijft zichtbaar.** Een track die muma nog niet heeft gegroepeerd — op elk
  moment ongeveer de helft van de bibliotheek, terwijl de worker zijn achterstand wegwerkt — houdt
  `is_canonical` op 1 en krijgt een lege `work_id`. Hetzelfde voor een pad dat niet matcht. Een
  filter hierop moet falen richting een bestand twee keer tonen, nooit richting muziek verbergen die
  bestaat.
- Een rij die eerder een antwoord kreeg wordt actief gecorrigeerd in plaats van met rust gelaten:
  zonder dat blijft een track die na een split zijn werk verliet voorgoed verborgen.
- De sync slaat een server die de migratie nog niet heeft gedraaid over in plaats van te falen — dat
  gat bestaat tussen het uitrollen van de images en de eerste start van de server — en een vergrendelde
  database kost deze ronde en niets meer.

- **Een nummer heeft nu een eigen pagina met al zijn versies.** Route `/song/<id>`, in dezelfde vorm
  als de album- en artiestpagina: de canonical bovenaan, daaronder elke versie, allemaal direct
  afspeelbaar. De knop ernaartoe staat naast de songtekst-knop en verschijnt alleen bij een nummer
  dat de server heeft gegroepeerd — een knop naar een lege pagina is erger dan geen knop, en terwijl
  de worker zijn achterstand wegwerkt draagt ongeveer de helft van de bibliotheek nog geen werk.
- De pagina haalt de versies zelf op en leidt ze niet af uit de lijst waar je vandaan kwam. Dat moet
  ook: de regel die je aanklikte ís de versie die de server koos, en de andere waren samengeklapt
  voordat de browser ze zag. `getSpotifyTracks?workId=<id>` levert ze mét afspeelbare id's, wat
  muma's eigen versie-API niet kan — die kent paden en muma-id's, en daar heeft de speler niets aan.
- Een nummer met maar één versie zegt dat, en een mislukte oproep zegt dát het mislukte in plaats van
  een lege pagina te tonen. Subsonic meldt zijn eigen fouten met HTTP 200 en een fout in de body, dus
  de status in die body is het enige dat vertelt of het werkte.

### Changed
- **"Eén regel per nummer" gebruikt nu het oordeel van de server in plaats van twee gokken.** De
  schakelaar in de web-UI deed twee dingen tegelijk: LMS kreeg `deduplicate=true` en klapte rijen
  samen op een genormaliseerde artiest plus titel, en de browser deed daarna hetzelfde nog een keer.
  Beide telden hun score op, en dat is precies de omkering die het versiemodel moest wegnemen — een
  320kbps SoundCloud-rip (+5200) versloeg een officiële 192kbps radio-edit (+2500).
- Allebei groeperen ze nu op `work_id` en houden ze de versie die muma als canonical aanwees. De
  score dient alleen nog als tie-break voor een werk waarvan de winnaar nog niet herberekend is, en
  die score is die van de server, niet een tweede berekening.
- **Wat de server niet heeft gegroepeerd blijft staan.** Een track zonder `workId` krijgt een sleutel
  van zichzelf en verdwijnt dus niet. Dat is geen randgeval: terwijl de worker zijn achterstand
  wegwerkt draagt ongeveer de helft van de bibliotheek geen werk, en die verbergen zou de lijst legen
  van muziek die er gewoon is. Hetzelfde geldt voor een antwoord van een server die migratie 118 nog
  niet heeft gedraaid: een ontbrekende `isCanonical` betekent "wel tonen".
- 106 regels heuristiek uit `Spotify.cpp` en de volledige inhoud van `deduplicate.js` zijn vervangen
  door het toepassen van wat er al besloten was.
- Nieuw: `getSpotifyTracks?workId=<id>` geeft alle versies van één nummer, met afspeelbare id's — dat
  is wat de versielijst achter een regel straks nodig heeft. muma's eigen `/api/songs/{id}` kent
  paden en muma-id's, en daar kan de speler niets mee. Een `workId` zet dedupliceren uit, want anders
  klapt het antwoord terug naar de ene versie waar je juist langs wilde kijken.

### Fixed
- **De SAST-baseline gooide de onderbouwing weg die iemand er met de hand in had gezet.** Het hele
  bestand wordt bij elke `SAST_WRITE_BASELINE=1` opnieuw opgebouwd uit `REASONS`, maar de redenen
  staan óók in dat bestand — en dat is waar je ze leest, dus daar werden ze bewerkt. Dat is twee keer
  misgegaan: één keer zo hard dat degene die het herstelde een waarschuwing voor de volgende lezer in
  het bestand achterliet, en op 2026-09-08 opnieuw, goed voor 36 regels audit-werk. Er stond geen
  enkele test op dit script, en dat is precies hoe hetzelfde ongeluk zich kon herhalen.
- Elke sectiekop draagt nu een stempel (`# --- <regel> --- [r:abc12345]`) van de tekst die de
  generator er zelf neerzette. Klopt de tekst nog bij dat stempel, dan mag hij vervangen worden — een
  reden bijwerken blijft dus een gewone bewerking. Klopt hij niet meer, dan heeft een mens er getypt
  en **weigert de generator te schrijven**: hij toont wat er verloren zou gaan en zegt dat het in
  `REASONS` thuishoort. `SAST_BASELINE_FORCE=1` overrulet dat en gooit het alsnog weg.
- Vergelijken met `REASONS` in plaats van met een stempel kan niet: dan is "iemand heeft hier getypt"
  niet te onderscheiden van "de reden is bijgewerkt", en zou elke normale bewerking de generator
  blokkeren.
- De vijf secties die alleen in het bestand stonden zijn naar `REASONS` verhuisd — de ntfy-URL, de
  LmsScanTrigger-noot, de audit van `SoundcloudArchive.py` en `events.py`, de geschiedenis van de
  tools-container van x3 naar x5, en de rechtenreden van de importer. Woord voor woord nagelopen: er
  is niets inhoudelijks verdwenen.
- `tests/ci/test_sast_baseline_rationale.py` pint het vast, inclusief een test die de baseline van
  déze repository leest en faalt zodra er weer een alinea in staat die een regeneratie niet kan
  reproduceren.

## [0.53.0] - 2026-09-09

### Added
- **Een hertag van een download was blind voor alles wat de downloader wist.** yt-dlp overhandigt
  zijn info-dict één keer, aan de postprocessor; elke keer daarna loopt de tagger over de
  bestandsboom en roept `parse_folder(channel, song_type)` aan zonder `extra_info`. Wat de eerste
  ronde niet in de tag schreef, was daarna onbereikbaar. Sinds 0.51.0 bewaart de archiefrij een
  gesnoeide kopie van die dict, en die werd door niets gelezen — de kolom lag er, de hertag ging er
  langs.
- `services/tagger/download_info.py` leest hem terug en `Tagger.parse_song` geeft hem door aan
  dezelfde `BaseSong._apply_extra_info` die de downloadkant gebruikt. Die vult een tag alleen als
  hij leeg is; het genre is de uitzondering en gaat daarna langs `ResolveGenreRule`, precies zoals
  elk ander afgeleid genre — een geblokkeerd genre komt er dus niet via deze weg alsnog in.
- Gematcht op het absolute pad dat het archief opschreef, en op niets anders. De tagger loopt over
  de schijf en leert nooit een video-id, dus het pad is de enige sleutel die beide kanten hebben.
  Een bestand dat sinds zijn download is verplaatst of hernoemd vindt niets en wordt getagd zoals
  het vandaag is. Bewust geen terugval op de bestandsnaam: twee kanalen met hetzelfde bestand
  zouden dan stilletjes elkaars metadata krijgen.
- `migrate_v23_download_archive_path_index.sql` indexeert de kolom waarin elk van de twee tabellen
  dat pad houdt — SoundCloud in `filename`, YouTube in `path`. Zonder index is dit een volledige
  scan over 157.393 respectievelijk 53.366 rijen per bestand.
- Vooruit-werkend, net als de kolom zelf: 77 rijen dragen vandaag een info-dict, elke nieuwe
  download komt erbij. Er wordt niets teruggehaald bij SoundCloud, want die kant beantwoordt een
  burst met 403.

### Fixed
- **Elke geïmporteerde release landde onschrijfbaar voor iedereen behalve root.** De importer draait
  als root met de standaard umask, dus wat hij uitpakt en verplaatst komt binnen als `root:root`,
  mappen `0755` en bestanden `0644`. Root merkt daar niets van — het verplaatsen, het taggen en de
  scan slagen allemaal — maar over SMB krijgt de share-gebruiker `other::r--` en faalt elke latere
  schrijfactie met `[Errno 13] Permission denied`.
- Gemeten op 2026-09-08 over de EPs-mappen die sinds 2026-09-01 zijn aangeraakt: **631 op `0777`,
  19 op `0755`** — precies de mappen die zijn aangemaakt nadat de handmatige rechtenreparatie van
  2026-09-05 langs de boom was gegaan. De release-date backfill liep op 9 bestanden daaruit vast.
  Een sweep repareert wat er op dat moment staat en zegt niets over de import van morgen, en dat is
  de reden dat dit in de importer thuishoort en niet in een script.
- `make_library_writable()` zet na de verplaatsing mappen op `0777` en bestanden op `0666` — wat de
  rest van de bibliotheek draagt sinds de reparatie van 5 september. Het draait vóór de tagronde,
  want die is de eerste die naar deze bestanden schrijft; als root zou die het toch wel redden, maar
  alles daarna niet.
- Best effort, en het zegt het als het misgaat: een `chmod` die niet plakt levert een WARNING per
  pad en een telling op, geen mislukte import. De release staat op dat moment al op zijn plek, en
  hem dan alsnog laten falen zou de bibliotheek in een slechtere staat achterlaten dan een bestand
  dat alleen leesbaar is.

- **Zestien afleveringen van één radioshow stonden als zestien versies van één nummer.** De
  groepering kijkt naar artiest en titel, en een set of aflevering draagt elke week dezelfde titel:
  16 keer "Andromedha Guest Mix" van een uur, 14 keer "The Boom Room", 11 keer "Forerunners Guest
  Mix". Gemeten op productie: 214 works met in totaal 560 lange opnames, waarvan er **346 zouden
  verdwijnen** zodra het canonical-filter uit fase 2 aangaat — een jaar wekelijkse show
  teruggebracht tot één aflevering. Een opname langer dan 15 minuten krijgt nu een eigen work en
  groepeert niet meer op titel.
- De grens is niet gevoelig gekozen: van de tracks in works met meer dan één versie lopen er 576
  langer dan 10 minuten en 566 langer dan 20. Alles wat lang is in deze bibliotheek is dus héél
  lang, en elke waarde in die lege band scheidt dezelfde twee populaties. Een lange track groepeert
  daarmee ook niet meer met een korte versie van dezelfde naam; dat kost een extended mix zijn plek
  naast de radio-edit, en dat is de veilige kant: iets twee keer tonen is beter dan het verbergen.
- **Elke SoundCloud-rip telde als officiële release.** De worker vroeg of een bestand in het
  downloadarchief stond door de bestandsnaam te vergelijken met `downloads_soundcloud_archive.filename`
  — maar alle 157.393 rijen daarin bevatten een absoluut pad, dus die vergelijking kon nooit waar
  zijn. Gevolg: de 1.162 SoundCloud-tracks die óók een label dragen kregen de provenance-bonus die
  voor een officiële release bedoeld is, en konden dus de release verslaan waar ze een rip van zijn.
  Precies de omkering die deze scoring moest wegnemen. Beide archieven worden nu op het volledige
  pad gematcht (SoundCloud in `filename`, YouTube in `path`), geïndexeerd door `migrate_v23`.
- `scripts/repair_song_works.py` verplaatst de al gegroepeerde afleveringen zelf: het herberekent
  elke sleutel en meldt deze apart als `long-form`. Voor de scores is er een nieuwe vlag,
  `--rescore-downloads`, die de gelabelde downloads uit hun work haalt zodat de worker ze met de
  gerepareerde test opnieuw beoordeelt. Beide zijn dry-run-baar; draai eerst `--dry-run`.

## [0.52.0] - 2026-09-08

### Added
- **Wat een bestand zei vóórdat de tagger het aanraakte, wordt nu vastgelegd.** De tagger
  herschrijft tags ter plekke en bewaarde geen kopie. `ORIGINAL_TITLE` en `ORIGINAL_ARTIST` zijn de
  twee velden waarvan iemand merkte dat ze verdwenen en waar toen met de hand een redding voor is
  gebouwd, elk in een eigen regel; van de rest was er geen antwoord op "waar kwam dit bestand mee
  binnen". En ook niet op "welke regel besliste dat", want de regels staan in de database en
  veranderen. Nieuwe tabel `library_ingestion_records` (`migrate_v22_ingestion_records.sql`) met per
  bestand de volledige tagset zoals gelezen, de versie van de code, en een vingerafdruk van de
  regeltabellen op dat moment.
- Eén rij per bestand, geschreven de eerste keer dat de tagger het opent en daarna nooit meer
  bijgewerkt: een latere ronde ziet een bestand dat deze tagger al herschreven heeft, dus zijn idee
  van "binnenkomst" is minder waard dan dat van de eerste. De vingerafdruk is één query per
  tagronde, niet per bestand.
- Bewust geen kopie van het bestand. De tagger verandert de audiostream niet, dus 5,3 TB audio
  dupliceren beantwoordt een vraag die niemand stelt; wat er op het spel staat is de metadata, en
  dat is een paar honderd bytes per track.

### Changed
- **De importketen verwijdert niets meer definitief; wat hij weggooit gaat in quarantaine.** Vier
  plekken deden een onherroepelijke `os.remove` of `rmtree` op een beoordeling die fout kan zijn.
  `Extractor.run` gooide het bronarchief weg zodra uitpakken lukte — dus vóórdat de renamer en de
  mover de release geplaatst hadden, en voor een labelrip is dat archief de enige pristine kopie die
  er ooit van bestaat. `Mover.remove` en `Renamer._resolve_collision` verwijderden een bronmap die
  ze als duplicaat beoordeelden, en die beoordeling (`is_same_release`) vergelijkt relatieve
  bestandsnamen en groottes, niet inhoud. En `BaseSong.__init__` verwijderde een `.m4a` die mutagen
  niet kon lezen, terwijl "mutagen kan dit niet lezen" iets anders is dan "hier zit geen audio in".
  Alles gaat nu naar `<quarantine>/<datum>/<categorie>/`, en `Quarantine.sweep()` ruimt het op na
  `quarantine_retention_days` (standaard 30). Twee nieuwe instellingen onder Paden.
- **De ene mover-tak vergeleek wel, de andere niet.** `_resolve_conflict` draait `is_same_release`
  voordat hij iets weggooit; de `FileExistsError`/`shutil.Error`-tak deed dat niet en verwijderde de
  bron op de uitzondering alleen. Een release die toevallig tegelijk in dezelfde bestemming landde
  werd zo weggegooid zonder dat er ooit iemand naar gekeken had. Beide takken stellen nu dezelfde
  vraag.
- De scanner loopt verborgen mappen niet meer in. Zonder ingestelde quarantainemap landt die naast
  de muziekroot als `.quarantine`, en het indexeren daarvan zou precies de bestanden terugbrengen
  die de importer net besloot niet te houden. `@eaDir` van Synology gaat om dezelfde reden mee.

### Fixed
- **De NFO-backfill controleerde zijn eigen voorwaarde niet meer op het moment dat hij schreef.**
  `plan_release` weigert een bestand dat al een `ORIGINAL_ARTIST` heeft en weigert een regel die
  andere artiesten noemt dan het bestand bevat — maar dat oordeel staat in een plan dat uren oud is
  tegen de tijd dat het geschreven wordt. De volledige planfase over 48.958 releasemappen duurde
  zes uur, en de tagger schrijft ondertussen naar diezelfde bestanden: sinds 0.51.0 legt
  `CaptureDisplayArtistRule` bij elke download een credit vast. `apply_plan` stelt de vraag nu per
  bestand opnieuw en slaat over wat inmiddels een eigen credit heeft (`skipped_gained_original`) of
  wat de wording niet meer beschrijft (`skipped_artists_changed`), in plaats van een verse waarde
  te overschrijven met een verlopen.
- Het `.failed`-bestand bevatte alleen paden, terwijl `--from-plan` `wording<TAB>pad` leest. Het
  bestand dat je overhield om geweigerde schrijfacties later opnieuw te draaien, was dus precies
  het formaat dat niet teruggelezen kon worden — de wording stond nergens anders. Het wordt nu in
  het planformaat weggeschreven.

- **9.188 tracks stonden op naam van een artiest die niet bestaat.** SoundCloud zet een marker vóór
  de echte credit — `PREMIERE ｜ TARS - Rumble [NNVA03]`, `FREE DOWNLOAD - Exilles - Crude
  Definition`. De artiestenregels knippen de titel in segmenten en kiezen het segment dat het beste
  matcht met een naam in `library_artists`. Zodra een marker die wedstrijd één keer wint, staat hij
  *in* `library_artists`, matcht daarna perfect met zichzelf en wint elke volgende titel: 9.188
  tracks onder "Premiere", 329 onder "FREE DOWNLOAD", 43 onder "PREVIEW". Bij 3.874 daarvan staat de
  echte artiest nog gewoon in de titel, waar de regel hem heeft laten liggen.
- De ignore-lijst kende deze namen niet, en zou ze ook niet hebben tegengehouden: beide regels die
  hem lezen (`CheckArtistRule`, `AddMissingArtistToDatabaseRule`) kijken pas naar de ignore-lijst
  *nadat* ze `library_artists` hebben geraadpleegd, en al deze namen staan in `library_artists`.
  `InferArtistFromTitleRule` trekt de ignore-lijst zonder correctie nu af van de namen waartegen hij
  mag matchen, dus een marker kan niet meer uit een titel gekozen worden en het segment met de echte
  artiest komt aan de beurt. Een naam mét correctie blijft wél kiesbaar — dat is precies hoe
  `CheckArtistRule` de kans krijgt de juiste spelling erin te zetten.
- `migrate_v22_promo_marker_artists.sql` zet elf markers op de ignore-lijst. Er wordt niets
  verwijderd: de artiestenrijen blijven staan en hun tracks houden wat ze hebben tot de deep run het
  bestand opnieuw leest. Een artiestenrij weggooien zou `library_tracks.primary_artist_id` en
  `library_works.primary_artist_id` verweesd achterlaten, waar geen foreign key op staat.
- **De brede pijp `｜` werd op drie plekken niet herkend.** SoundCloud gebruikt hem omdat `|` niet in
  een bestandsnaam mag, dus de twee betekenen hetzelfde — maar `InferArtistFromTitleSingleDashRule`
  en de laatste-redmiddelregel vervingen alleen de ASCII-versie. `PREMIERE ｜ TARS - Rumble` viel
  daardoor uiteen in twee segmenten waarvan het eerste `PREMIERE ｜ TARS` was: een artiestennaam die
  nooit heeft bestaan. Eén `normalise_pipes()` voor alle regels.

- **LMS zou de quarantaine gewoon geïndexeerd hebben.** De muma-scanner slaat verborgen mappen
  sinds de vorige wijziging over, maar LMS is een tweede indexer met een eigen regel — en die heeft
  er geen: `exploreFilesRecursive` daalt elke map in en stopt alleen bij een `.lmsignore`
  (`ScanStepScanFiles.cpp`, naam uit `ScannerSettings.hpp`). Zonder ingestelde quarantainemap landt
  die als `.quarantine` naast de muziekroot, precies de boom waar de LMS-bibliotheek op wijst, dus
  een geparkeerde dubbele release was als LMS-tracks teruggekomen — het besluit dat de importer net
  had genomen, ongedaan gemaakt door de indexer. De quarantaineroot krijgt nu bij aanmaken een
  `.lmsignore`. Dat gebruikt LMS' eigen mechanisme in plaats van zijn scanner aan te passen.

## [0.51.0] - 2026-09-07

### Added
- **Wat yt-dlp over een download wist wordt nu bewaard.** De postprocessor kreeg de volledige
  info-dict, de tagger pikte er vier velden uit (`BaseSong._apply_extra_info`) en de rest verdween
  zodra het proces verderging. SoundClouds `genre`, `tags` en `description`, YouTubes
  `artists`/`track`/`album`/`release_year` uit het muziek-credits-paneel, en de hoofdstukindeling
  van een set van twee uur stonden nergens opgeschreven — over 53.295 YouTube- en 157.387
  SoundCloud-rijen. Nieuwe kolom `info_json` op `downloads_soundcloud_archive` en
  `downloads_youtube_archive` (`migrate_v21_download_info_json.sql`).
- De blob wordt eerst gesnoeid (`services/downloader/info_json.py`). `formats`, `thumbnails` en
  `automatic_captions` zijn transportdetails die binnen een paar uur verlopen en vormen bijna het
  hele gewicht van de 100-800 KB die een ruwe YouTube-dict weegt; wat overblijft is 5-15 KB, met een
  harde bovengrens. Een `description` die daar in z'n eentje overheen gaat wordt weggelaten; blijft
  het dan nog te groot, dan slaat de rij niets op in plaats van een halve JSON.
- Vooruit-werkend, met opzet. Bestaande rijen blijven `NULL`: voor SoundCloud terughalen zou één
  `yt-dlp --dump-single-json` per track kosten en die kant beantwoordt een burst met 403. Op de
  YouTube-kant vult een herdownload wél een lege kolom aan, want die tabel is echt op
  (video_id, download_type) gesleuteld.
- Er wordt niets mee gedaan bij het taggen. Dit legt alleen vast wat de downloader te horen kreeg.

- `GET /api/library/genres` geeft per genre een `tint` mee: de kleur waarin dat genre getekend
  wordt. De web UI en de mobiele app tonen een genre allebei als gekleurde tegel, en met een tabel
  aan beide kanten was Hardstyle vroeg of laat oranje op de ene plek en magenta op de andere — een
  verschil dat niemand ziet tot beide naast elkaar openstaan, en dat van geen van beide kanten te
  testen is. De kleur wordt afgeleid van de naam en niet opgeslagen. Additief veld; bestaande
  consumers merken niets.
- De genre-tegels in de web UI dragen die kleur nu. Een genre dat MuMa niet kent houdt de
  brand-kleur die de tegel altijd al had.

### Changed
- **De helft van de pipeline draaide op de container die naast GitLab zelf staat.** De CI-LXC deelt
  node `server` met gitlab (cap 15G) en lms (cap 11,9G, en die zit eraan); de caps van alle CT's
  samen zijn 58G op 30G fysiek geheugen. Alle jobs die hun omgeving in een Docker-image meedragen
  (`mobile:format`, `mobile:lint`, `mobile:unit`, `mobile:build-debug`, `muma:smoke`, `muma:images`,
  `muma:e2e`) dragen nu de `fast`-tag, zodat het werkstation ze overneemt zodra het aan staat.
- **Jobs die hun toolchain van de host lenen blijven bewust ongetagd.** De twee runners draaien niet
  dezelfde versies (LXC: Python 3.11, node 24; werkstation: Python 3.13, node 20), dus
  `backend:unit`, `frontend:*` en `frontend:e2e` zouden een andere uitslag geven afhankelijk van
  welke runner het eerst polt. Een nieuwe policy-test houdt daarnaast de jobs met productie-
  credentials — deploy, tag, APK-upload — permanent op de LXC. `backend:integration` en
  `muma:contracts` horen ook in die groep: die starten hun database wél in Docker maar draaien
  `python3 -m pytest` vanaf de host, en faalden op het werkstation in vijf seconden met `No module
  named pytest`.

### Fixed
- **Een download hield "Lil Texas & Albino" nergens vast.** `CleanTagsRule` bewaart de
  artiestenregel zoals hij op het bestand stond, maar alleen als hij hem zelf nog moest splitsen.
  Bij een SoundCloud- of YouTube-download komen de artiesten uit de titel:
  `InferArtistFromTitleRule` draait ervóór en levert de ARTIST-tag al gesplitst aan, dus de
  "is er iets veranderd"-test van `CleanTagsRule` sloeg nooit aan en de weergavenaam ging verloren.
  8 van de 344.757 tracks op productie hadden er een.
- De credit wordt nu in twee stappen vastgelegd, en dat is het lastige deel. `InferArtistFromTitleRule`
  *onthoudt* alleen het ruwe segment, en alleen als dat segment precies uiteenvalt in de namen die
  eruit gekomen zijn — de tekst waar een naam uit gelezen is, is namelijk niet vanzelf een credit:
  `set_cleaned_artist` gooit "(live)" en losse achtervoegsels weg, en de fuzzy-takken houden alleen de
  kandidaten over die op een bekende artiest matchten. `Angerfist (live)` of een naam die de
  bibliotheek juist wegliet als credit wegschrijven is erger dan geen credit, want de webspeler toont
  `display_artist` in plaats van de artiestenlijst. De nieuwe `CaptureDisplayArtistRule` draait als
  laatste van de artiestenregels en schrijft de credit alleen weg als die de artiesten nog benoemt
  waar het bestand uiteindelijk mee eindigt — zo levert
  `Angerfist & Miss K8 - Track (feat. Albino)` géén credit op in plaats van eentje die twee van de
  drie artiesten noemt. Een waarde die al op het bestand stond wordt nooit overschreven.

- **Het genre dat bij een label hoort werd nooit op een labelrelease gezet.**
  `InferGenreFromLabelRule` bestond, had een eigen test en stond in de regellijst van geen enkel
  songtype. `rules_label_genre` werd daardoor alleen gelezen via `InferGenreFromAlbumArtistRule`, dat
  dezelfde tabel raadpleegt op de naam van een YouTube-kanaal — nooit op de publisher. Een echte
  release in de EPs-boom kwam er dus zonder genre uit zodra de artiesten zelf geen genreregel hadden,
  en dat las als een niet-gecureerde release in plaats van als een regel die nergens draait. De regel
  zit nu in `LabelSong`, vóór de subgenreregel zodat een labelgenre ook nog verbreed wordt.
- **De ketentest liep om de labelmap heen.** In `docker/compose.test.yml` stonden
  `eps_folder_path` en `import_folder_path` allebei op `/mnt/music`, dus elk bestand op het volume
  zag eruit als een labelrelease en de drielaagse mappenstructuur waar de tagger publisher en
  catalogusnummer uit leest werd nooit doorlopen. Nieuw:
  `tests/bdd/features/label_import.feature` loopt een scene-release door label, artiesten,
  weergavenaam en beide genres heen, en `services/tagger/Song/LabelSongTest.py` doet hetzelfde per
  veld inclusief de releasedatum uit de NFO.
- De tagger slaat een ontbrekende EPs-map nu over in plaats van eruit te vliegen. Die uitzondering
  nam de achtergrondlus mee, en `/health` meldde de hele dienst degraded om een map die een minuut
  later weer terug was.

### Security
- **De nachtelijke image-refresh liet twee productie-images achter op de base waar ze op gebouwd
  zijn.** Die taak herbouwt `muma-base` met `--no-cache` en pusht hem, dus die pakt de
  Debian-security-pakketten van die dag mee — maar `muma-telegram` en `muma-importer` bleven staan
  op wat hún laatste build erfde, en dat is de release. Zo dook `CVE-2026-33164` (libde265, HIGH,
  upstream al gefixt) op in beide images terwijl de base waar ze op gebouwd zijn al schoon was. Er
  was geen pin om te bumpen: de images waren simpelweg ouder dan hun base. De refresh herbouwt nu de
  hele familie die FROM `muma-base` komt; een test leidt die lijst af uit de Dockerfiles, dus een
  nieuwe worker-image kan hem niet stilletjes missen.
- Ontwikkelketen: `postcss-selector-parser` naar 7.1.6 (GHSA-w9m9-85wc-3x92, denial of service via
  ongecontroleerde AST-recursie). Dev-dependency van de eslint-keten, komt niet in een image terecht.

## [0.50.0] - 2026-09-07

### Added
- **MuMa heeft sinds maart 2024 luisterbeurten opgeslagen en ze nooit teruggegeven.** `/history`
  somde ze één voor één op, niemand telde ze. Er is nu een pagina **Luisteren** met totalen, een
  tijdlijn, een uur-van-de-dag- en dag-van-de-week-grafiek, je meest gedraaide tracks, artiesten en
  labels, en waar je luisterde — over 30 dagen, 12 maanden of alles. Zeven nieuwe leesendpoints
  onder `/api/listening`; geen nieuwe tabellen.
- **De pagina zegt zelf wat ze niet weet, boven de grafieken in plaats van eronder.** 33.461 van de
  53.760 opgeslagen luisterbeurten (62%) zijn nooit aan een track in de bibliotheek gekoppeld: die
  tellen mee in de totalen, de tijdlijn en de bronnen, maar kunnen in geen ranglijst voorkomen. En
  maar 876 luisterbeurten hebben ooit vastgelegd hóe lang er gespeeld is, dus de luistertijd is een
  schatting die uitgaat van uitgespeelde tracks — `measured_secs`, `imputed_secs` en
  `estimated_secs` zijn drie aparte velden, geen samengevoegd getal dat een aanname als meting
  presenteert.
- **Uren en dagen staan in jouw tijdzone, niet in die van de database.** De databasecontainer draait
  op UTC, dus `HOUR()` zou een luisterbeurt van half één 's nachts in Amsterdam op de vorige dag om
  half elf zetten. De client stuurt een IANA-zonenaam mee en de indeling gebeurt in Python; een
  vaste offset zou de ene helft van het jaar goed zetten en de andere kapot maken.
- **Een API-sleutel van een gebruiker leest alleen de eigen geschiedenis.** `?username=` van een
  ander levert 403. De LMS-proxy geeft querystring en sleutel ongewijzigd door en controleert zelf
  niets, dus zonder deze check kon één sleutel ieders luistergeschiedenis lezen.
- Nieuwe index op `listened_at` in beide scrobble-tabellen (`migrate_v20_listening_indexes.sql`): de
  bestaande unique keys beginnen op `username` en helpen niet voor een vraag zonder gebruikersnaam.

## [0.49.2] - 2026-09-06

### Fixed
- **Een enkele rescan wiste de genres van de track die hij opnieuw inlas.** `ScannerManager` bouwt
  zijn `GenreRulesHelper` zonder cache en alleen `run_full` laadde die; `scan_single` niet. De
  genre-resolutie kwam daardoor leeg terug, en `_write_genres` doet zijn `DELETE` ook als er niets
  in te voegen valt. Dat raakte elke "rescan deze track" uit de webinterface en elke
  `/tracks/rerun-parse-path` die LMS stuurt. `scan_single` laadt de regels nu opnieuw, en een
  mislukte regel-query laat de bestaande genre-rijen voortaan staan in plaats van ze te wissen.
- **De scanner kon bestanden verwijderen en herschrijven terwijl hij ze alleen las.**
  `ReadonlySong` erft `BaseSong.__init__`, en die doet `os.remove()` op een m4a die mutagen niet
  kan openen en draait `NormalizeFlacTagsRule`, die een FLAC met kleine letters in de tagsleutels
  meteen opslaat. Alleen het indexeren van de collectie muteerde dus bestanden; een grote rescan
  concentreert dat. Lezen kost niets: `TagCollection._parse_flac` maakt de sleutels bij het lezen
  toch al hoofdletters.

## [0.49.1] - 2026-09-06

### Fixed
- **Elke afgeronde map werd een eigen scanverzoek aan LMS.** Zodra de melding in 0.49.0
  daadwerkelijk aankwam, logde LMS er vijf per seconde, urenlang — één per map die de tagger
  afrondde. Hij overleeft dat, want zijn eigen verzamelaar voegt de paden toch samen, maar elk
  verzoek bezet een Wt-thread en een uitgeputte Wt-threadpool is precies hoe deze server eerder
  de hele site 504's heeft laten geven. De wachtrij vertrekt nu als één verzoek met alle paden
  die er al in stonden, dubbele eruit. Er wordt nergens op gewacht: het punt van die wachtrij is
  dat een verplaatsing nooit blijft hangen op een muziekserver.

## [0.49.0] - 2026-09-06

### Added
- **De originele artiestschrijfwijze bleek niet vanzelf terug te komen, en is nu terug te halen uit
  de NFO.** Sinds 0.47 bewaart `CleanTagsRule` "Eternate & Prosphere" in `TXXX:ORIGINAL_ARTIST`
  vlak voor hij het in twee waarden splitst. De aanname daarbij was dat bestaande bestanden dat
  vanzelf zouden oppikken bij hun volgende tagronde. Dat klopt niet: een bestand dat al gesplitst
  is heeft niets meer te splitsen, dus de capture vuurt nooit meer. Gemeten over 400 bestanden
  onder de EPs-root draagt 120 een gesplitste artiest en **geen enkele** nog de originele
  schrijfwijze — voor de bestaande bibliotheek was het veld dus permanent leeg, niet tijdelijk.
  De NFO die met de release meekomt is geschreven vóór dat splitsen en zegt het nog wel.
  `scripts/backfill_original_artist_from_nfo.py` leest die tracklist, koppelt op tracknummer aan
  het bestand ernaast, en schrijft de schrijfwijze terug. De klep die dat veilig maakt: een regel
  wordt alleen gebruikt als die, gesplitst met de eigen regel van de tagger, exact dezelfde
  artiesten oplevert als er al in de tag staan — een write kan dus alleen de schrijfwijze
  herstellen en nooit een artiest toevoegen, weglaten of hernoemen. Dry run standaard.
  Alleen de EPs-boom heeft NFO's; Soundcloud, Youtube en artists hebben er nul, dus die vallen
  hier buiten.

### Fixed
- **Het bevestigen van een labelvoorstel kon een release in zichzelf stoppen.** `shutil.move`
  faalt niet als de bestemming al een map is: hij verplaatst de bron er *in*. De release komt
  dan één niveau dieper te staan, de scan indexeert hem twee keer, en niets meldt dat er iets
  misging. De mover van de importer leerde dat op 4 september; dit endpoint doet dezelfde
  aanroep en had die controle nooit. Op productie is het hier nog niet misgegaan — de 552
  mappen die zichzelf bevatten komen allemaal van de mover, van vóór die datum — maar de
  aanroep is identiek en de schade zou dat ook zijn. De regel staat nu op één plek,
  `services/common/Helpers/ReleaseFolder.py`, waar zowel de importer als music-manager bij kan:
  music-manager bevat `services/importer` niet, en dat is precies waarom de controle daar
  ontbrak. Botst de bestemming, dan verplaatst er niets, blijft het voorstel openstaan en telt
  de beheerpagina het apart in plaats van het als bevestigd op te tellen.

- **muma heeft LMS nooit verteld dat er iets veranderd was.** Er waren twee antwoorden op de
  vraag "waar staat LMS": de radioplanner las `LMS_URL` / `LMS_HOSTS` / `MUMA_SERVER_HOSTS` uit
  de omgeving en werkte, `LmsScanTrigger` las de instelling `lms_hosts` uit de configuratie —
  en `docker-compose.yml` vult die nergens, de regel staat uitgecommentarieerd. Wie nooit met de
  hand een host op de beheerpagina heeft ingevuld, had dus een scan-trigger die niets deed. Stil,
  want het verzendpad keerde zonder één logregel terug: een bibliotheek die een verplaatste map
  pas uren later oppikte, las als een probleem van LMS. Hetzelfde gold voor de API-sleutel, die
  onder twee namen door compose komt en waarvan de trigger er maar één kende. Beide antwoorden
  komen nu uit één plek, `services/common/Helpers/LmsEndpoint.py`: de instelling wint, de
  omgeving is de terugval, en als geen van beide iets oplevert zegt het log één keer precies wat
  er ontbreekt in plaats van niets.

## [0.48.0] - 2026-09-06

### Added
- **LMS kan voortaan één map scannen in plaats van de hele bibliotheek.** `startScan` accepteert een
  herhaalbare `path`-parameter, bibliotheek-relatief, en doet daar seconden over waar een volledige
  incrementele scan hier bijna een uur kost -- en pas een uur ná de vorige begint, dus een
  wijziging wachtte tot twee uur voordat je hem zag, met het oude pad al die tijd nog in de index.
  Een pad dat niet meer bestaat is expres geldig: dat is hoe de rijen onder een verplaatste map
  worden opgeruimd. De verwijderstap kreeg daarvoor een query met een half-open bytebereik in
  plaats van `LIKE`, want die is in SQLite hoofdletterongevoelig en matcht bovendien een buurmap
  waarvan de naam toevallig hetzelfde begint. Samen met `fullScan` betekent het "lees alles onder
  dit pad opnieuw". Overgeslagen worden alleen `Optimize` en het duplicatenrapport; het opruimen
  van wezen en het herberekenen van de clustertellingen blijven staan -- dat laatste overslaan is
  ooit de reden geweest dat elke genretelling op 0 stond. En een scoped scan schrijft zijn cijfers
  niet weg als `lastScan`, zodat de beheerpagina de laatste volledige scan blijft beschrijven.

- **Een direct scanverzoek pauzeert de periodieke scan en die gaat daarna verder waar hij was.**
  Voorheen brak zo'n verzoek de lopende scan af en verschoof het bovendien het volgende
  scanmoment naar "over een uur" -- bij een uurschema en een scan die bijna een uur duurt,
  betekende dat: altijd bezig, altijd afgebroken, en de klok altijd teruggezet, dus de
  bibliotheek-brede scan kwam nooit meer door zijn eigen stappen heen. De pauze hergebruikt de
  vlag die elke scanstap al op elke batchgrens controleert; de scanner onthoudt daarnaast
  alleen nog *waarom* die vlag omhoog ging. Bij hervatten begint de onderbroken stap opnieuw,
  de stappen ervoor niet, en hun cijfers blijven staan. Binnenkomende paden worden vijf
  seconden lang verzameld en samengevoegd, en vertrekken hoe dan ook binnen een minuut: een
  taggerronde die honderden mappen aanraakt kost de scan zo één stap-herstart per minuut in
  plaats van honderden.

- **Naast het incrementele schema staat nu een wekelijkse volledige herlezing.** Dezelfde
  bibliotheek-brede scan met `fullScan` aan, op een instelbare weekdag, standaard uit. Vallen
  beide momenten samen, dan wint de volledige: die doet alles wat de incrementele doet.
  music-manager stuurt sinds deze versie bij elke verplaatsing de betrokken mappen mee -- oude
  én nieuwe, want het oude pad is hoe de rijen onder een verdwenen map worden opgeruimd -- en
  doet dat vanaf een eigen thread, zodat een trage muziekserver een import nooit ophoudt.

### Fixed
- **De back-merge naar develop faalde bij elke release op `muma:changelog`.** Dat script eist een
  fragment van elke merge request, met een uitzondering voor `release/*` en `hotfix/*` — maar niet
  voor de merge request die master terugbrengt naar develop. Die voegt per definitie niets toe: de
  fragmenten die hij zou moeten dragen zijn net door de release opgegeten. Het gevolg is groter dan
  een rood vinkje, want een back-merge die niet kan mergen blijft openstaan, en een openstaande
  back-merge onderdrukt de branch-pipeline van master — waarmee de eerstvolgende release zijn tag
  én zijn eigen back-merge verliest. `master` → `develop` is nu net zo'n uitzondering als een
  release-branch, met tests voor alle vrijstellingen erbij; een branch die alleen "master" in zijn
  naam heeft, valt er niet onder.

- **De app-versie werd stilzwijgend gelijkgesteld aan de serverversie.** `versionName` van
  muma-mobile loopt bewust een minor voor op de root-`VERSION`, dus een fragment in
  `changelog.d/mobile/` belandde onder een versie die de app nooit gehad heeft. Daar is nu
  `--mobile-version` voor, en zonder die vlag weigert het script te draaien zodra er mobiele
  fragmenten liggen -- liever een release die stilstaat dan een changelog die liegt.

- **Het nieuws afspelen in de webinterface bleef na 0.46.0 hangen op "kon niet afspelen HTTP 504".**
  De vorige poging haalde een overbodige kopie per read weg, maar dat was niet waar de tijd zat.
  Gemeten aan de ontvangstkant op productie: de overdracht begint op 1044 KB/s en zakt naar 92 KB/s
  naarmate de body groeit -- kwadratisch, want Wt's HTTP-client plakt elke read aan de al
  opgebouwde response. 15 MB kostte zo ongeveer 150 seconden, terwijl MuMa het bestand in een halve
  seconde wegschrijft. De proxy stuurt één verzoek tegelijk, dus al die tijd liep ook elke
  artiestafbeelding erachter in een timeout. Een bulletin wordt nu in brokken opgehaald: dat zet
  Wt's eigen buffering uit -- die slaat alleen op zolang er een maximum staat -- en het aan elkaar
  plakken gebeurt in een string die vooraf gereserveerd is, wat wél lineair schaalt.

- **Elke merge request van Renovate bleef rood op `muma:changelog`.** Het script eist een
  changelog-fragment van iedere merge request, en Renovate schrijft die niet — er is aan die kant
  niemand om aan iets te herinneren. Het gevolg was niet alleen een rood vinkje: de meeste van die
  merge requests horen zichzelf te mergen, en een gate die nooit groen wordt zet die automerge
  gewoon stil, zodat de bumps blijven liggen tot iemand ze met de hand `no-changelog` geeft.
  `renovate/*` is nu een vrijstelling zoals `release/*` en de back-merge dat al waren. Een
  dependency-bump die wél een regel verdient, is er een die iemand gelezen heeft, en die kan het
  fragment toevoegen zoals op elke andere branch.

## [0.47.0] - 2026-09-06

### Added
- **"Henk feat Kees" werd in de bibliotheek altijd "Henk, Kees" — het woordje dat de twee namen
  verbond, was onherstelbaar weg.** `CleanTagsRule` splitst het artiestentag op "feat"/"vs"/"b2b"/"&"
  in losse `library_track_artists`-rijen, en die stap gooide de scheidende tekst zelf weg: alleen
  de namen bleven over. Het tagbestand zelf raakte de tekst ook kwijt zodra het een tagronde kreeg,
  dus er was daarna geen plek meer waar "feat" nog stond. De tagger schrijft de originele
  artiestregel nu, vóór die split, weg als een `TXXX:ORIGINAL_ARTIST`-frame — alleen wanneer de
  split ook echt iets veranderde, dus een los-artiest-bestand krijgt er niets bij. De scanner leest
  dat frame terug in een nieuwe kolom `library_tracks.display_artist`, en Bibliotheekbeheer toont
  die tekst nu in plaats van de kale kommalijst zodra hij er is.
  Geen backfill: een bestand krijgt dit pas bij de eerstvolgende tagronde om een andere reden, want
  de rauwe tekst bestaat alleen nog kort tijdens het schrijven zelf. Beperkt tot Bibliotheekbeheer —
  LMS en de mobiele app hebben hun eigen, losstaande artiestenmodel en blijven de kommalijst tonen.

- **Release Radar en Daily Mix, eerste versie.** De ranker leidt een smaakprofiel af uit je
  luistergeschiedenis, telt een luisterbeurt één keer op zijn diepste genre, en verdeelt de plekken
  over je genres in plaats van ze op score te sorteren -- anders vult het genre dat je het meeste
  speelt alle dertig plekken en zie je de rest nooit. Nog geen scherm: `GET /api/feeds/release-radar`
  en `scripts/feeds_dryrun.py` zijn wat er is, zodat de vensters op echte cijfers gekozen kunnen
  worden voordat er UI omheen komt.

### Fixed
- **Een muma-container zonder LMS-configuratie belde productie, en niets zei dat.** `lms_base_url()`
  viel bij ontbrekende configuratie terug op een hardgecodeerde `http://lms:5082`. Op de deployment
  klopt dat — `lms` is de container_name van de apart uitgerolde LMS-stack op hetzelfde netwerk — en
  juist dát maakte het gevaarlijk: een kale hostnaam wordt opgelost door de DNS die de host toevallig
  heeft, en op het kantoor-LAN wijst `lms` naar 192.0.2.27. De verouderde lokale stack op een
  werkstation belde daardoor **productie** elke vijf seconden met een sleutel die productie niet kent.
  Aan geen van beide kanten was dat te zien: LMS logt de weigering (`code = 44, msg = 'Invalid API
  key.'`) zónder client-adres, dus het leest als een storing in prods eigen radio-thread. Alleen het
  access-log van de reverse proxy verried dat de requests van een ontwikkelmachine kwamen. Er is nu
  geen default meer: ontbreekt alles, dan volgt een `LmsNotConfigured` met een leesbare melding, en
  `radio.py` degradeert dat tot één logregel per poging in plaats van stil verkeer naar andermans
  server. Meegenomen: `MUMA_SERVER_HOSTS` wordt nu ook gelezen. Dat is de variabele die
  `docker/docker-compose.yml` voor deze service daadwerkelijk zet, mét een commentaarblok waarom —
  de oude code las hem niet, dus de deployment werkte per toeval doordat de hardgecodeerde default
  toevallig gelijk was aan de ingestelde waarde.

- **117 losse nummers stonden als één song in de database.** De groeperingssleutel van de
  song-versies is `artiest:::titel`, met de versiemarkering uit de titel gestript. Een titel die na
  dat strippen niets overhoudt — leeg, één duif-emoji, een reeks combining marks, of alleen
  `(Radio Edit)` — leverde de sleutel `:::` op, en de UNIQUE-index op `work_key` maakte daar één
  work van. Op productie zat werk 89834 daardoor op 117 niet-verwante opnames, met nog 543
  titelloze tracks in de wachtrij om zich erbij te voegen. Zo'n titel identificeert niets, dus
  krijgt de track nu een sleutel voor zichzelf (`track:<id>`, naast de bestaande `split:<id>`); een
  lege *artiest* groepeert nog wel gewoon op titel, want de helft van deze bibliotheek heeft geen
  `primary_artist_id` en zet de artiest in de titel. `scripts/repair_song_works.py --dry-run`
  rapporteert wat er verkeerd staat, zonder vlag maakt het de groepering los zodat de worker
  opnieuw indeelt.
- **`library_works.work_key` vergeleek niet op bytes.** De kolom erfde `utf8mb4_general_ci`, waarin
  elk teken buiten de BMP hetzelfde collatiegewicht heeft: twee sleutels van gelijke lengte uit
  zulke tekens zijn dan gelijk, en de UNIQUE-index voegde hun works samen zonder een fout te geven.
  Exact de val die `migrate_v13` voor `channels.normalized_name` opruimde.
  `migrate_v19_work_key_binary.sql` zet de kolom op `utf8mb4_bin`; het repairscript haalt de rijen
  uit elkaar die al waren samengevoegd, doordat het van elke track de sleutel hérberekent in plaats
  van naar één symptoom te zoeken.
- **`migrate_v13` deed zelf nooit iets.** De guard telde de kolommen die al `utf8mb4_bin` zijn en
  koos bij `COUNT(*) = 0` de tak "is already utf8mb4_bin" — dus op een database die de migratie
  nodig had, sloeg hij hem stil over, en alleen op een al gemigreerde voerde hij de ALTER uit. Prod
  staat goed omdat `db_init.py` de tabel meteen binair aanmaakt, maar het bestand deed niet wat het
  claimt. De voorwaarde is omgedraaid.
- **Een track kon gescoord worden op de helft van zijn bestanden.** De batchquery van de worker
  limiteerde ná de join op `library_media_files`, en `LIMIT` telt gejoinde rijen. De laatste track
  van een batch werd zo afgesneden van zijn resterende bestanden, kwam mét work uit de ronde en
  keerde dus nooit terug: zijn FLAC kon één rij voorbij de limiet liggen terwijl zijn MP3 de
  canonieke versie werd. De batch wordt nu vóór de join gekozen.
- **Een gesplitste track bleef de oude groep besturen.** `split_track()` verplaatst de track maar
  liet de pin van de oude work naar hem wijzen, en `recompute_canonicals()` volgde die pin blind —
  waarmee de oude song een canonieke versie kreeg die inmiddels een andere song is. De pin wordt
  bij het splitsen gewist, en een pin die geen lid meer is telt niet meer mee.

## [0.46.0] - 2026-09-05

### Added
- **De changelog wordt niet meer op een feature branch bewerkt.** Elke wijziging legt een eigen
  bestandje neer in `changelog.d/`, en de release voegt ze samen onder de nieuwe versiekop. Dat is
  geen cosmetiek: het gedeelde `[Unreleased]`-blok merget niet alleen luidruchtig (een conflict
  tussen twee branches van dezelfde dag), maar vooral stil. Ships er een release terwijl jouw
  branch openstaat, dan ziet git "wij voegden regels toe" en "zij voegden een versiekop van twee
  regels in", past allebei toe, en jouw regels staan onder een versie die zonder ze naar productie
  ging. Vier branches in één sessie, en niets ving het: geen test leest de changelog, en
  `release-version-check.sh` controleert alleen dát er een gedateerde regel voor `VERSION` staat,
  niet wat erin staat. Een fragment is een nieuw bestand met een naam die niemand anders gebruikt,
  dus er valt niets te mergen. `muma:changelog` faalt een MR die er geen meebrengt, tenzij het
  label `no-changelog` erop zit.

- **Een agent kon productie alleen lezen door er als root op te SSH'en.** "Read-only" was een
  instructie in een skill-tekst, dus precies zo betrouwbaar als het model dat hem las, en elke
  databasevraag ging via het applicatie-account dat óók mag schrijven. Er is nu een MCP-server
  (`tools/muma_mcp`, draait lokaal, praat naar prod via de bestaande `/health`- en
  `/api/system/*`-endpoints plus een eigen databaseaccount) met zes tools: `prod_health`,
  `prod_containers`, `prod_logs`, `prod_tables`, `prod_describe` en `prod_query`. De grens ligt in
  de database: `muma-readonly` heeft `SELECT, SHOW VIEW` op één database, geen `FILE` — dus ook
  geen `SELECT ... INTO OUTFILE` — en `MAX_QUERIES_PER_HOUR 2000` plus `MAX_USER_CONNECTIONS 3`
  zodat een agent in een lus door MariaDB zelf wordt afgekapt. Daarbovenop weigert een guard alles
  wat niet met `SELECT`/`WITH`/`SHOW`/`DESCRIBE`/`EXPLAIN` begint, strípt hij commentaar vóór hij
  het sleutelwoord leest (`/*!…*/` wordt door MariaDB uitgevoerd, dus een validator die naar de
  originele tekst kijkt leest eroverheen) en gaat elke query in `START TRANSACTION READ ONLY` met
  `max_statement_time=10`. Logoutput gaat langs een maskeerfilter, want containerlogs bevatten
  echt credentials. `scripts/prod/create-readonly-db-user.sh` maakt het account aan;
  `scripts/prod/install-muma-mcp.sh` registreert de server en beweert niet dat hij read-only is
  maar probeert een `CREATE TABLE` en faalt als die slaagt.

### Changed
- **De lege hoes in de webinterface was nog altijd het Spotify-logo.** Het stond in zes bestanden
  (`spotify-fallback.svg` en `unknown-cover.svg`, elk in `services/frontend/public/images/`, in de
  LMS-`docroot` en in de `approot` waar de artwork service zijn standaardhoes vandaan haalt), en
  het was met de hand getekend, los van het merk. De placeholder is nu het MuMa-equalizerteken,
  afgeleid uit dezelfde `BARS`-constanten als het app-icoon en de notificatieglyph in
  `tools/render_branding_icons.py`, dus hij kan niet meer los gaan lopen van het icoon. De kleuren
  blijven de paneelgrijzen (`#282828` op `#181818`), want een ontbrekende hoes hoort dof te zijn en
  geen merkstempel.

### Fixed
- **Een genreregel op een artiest- of labelpagina bleef ongebruikt liggen.** De pagina sloeg de
  regel op en ververste de draaiende tagger, maar markeerde de bestanden niet voor een nieuwe ronde
   -- en zonder die markering heeft de tagger geen reden om er ooit nog langs te lopen. De regel
  wachtte dus achter een wachtrij van 165.394 bestanden, terwijl de pagina "Regel opgeslagen."
  meldde. De management-endpoints voor precies dezelfde regels deden dit al wél; die twee zijn nu
  één gedeelde `invalidate_quietly` in `RescanInvalidator`, zodat ze niet opnieuw uit elkaar kunnen
  lopen. De bevestiging noemt voortaan hoeveel bestanden er in de wachtrij zijn gezet, want "geen"
  en "duizend" zagen er tot nu toe hetzelfde uit.

- **De ntfy-melding van een download noemde de releasedatum niet.** De pushtekst is letterlijk
  `str(song)`, en die lijst somde titel, artiest, album, genre, publisher en pad op -- de datum zat
  er nooit in, terwijl dat juist het veld is waarop je een download beoordeelt. `BaseSong.__str__`
  zet er nu een regel `Released=` bij, wat in één klap ook de SoundCloud- en de import-melding
  vult, want alle drie sturen dezelfde string. De keuze tussen `DATE` en `ORIGINALDATE` volgt
  dezelfde regel als de web-UI en de app: neem de originele datum alleen als hij minstens zo
  precies is. Nieuw is dat de Python-kant ook de ongescheiden `20260903` aankan die yt-dlp als
  `upload_date` in `DATE` schrijft, en dat een scene-tag `2026-00-00` als `2026` uitkomt in plaats
  van als `00-00-2026`. Een videodownload wordt niet getagd en heeft dus geen Song; die melding
  leest de datum nu rechtstreeks uit het info-dict van yt-dlp.

- **Een release die je twee keer importeerde belandde in zichzelf.** `shutil.move` ziet een
  bestaande doelmap niet als botsing maar als "hier moet je in", dus de tweede kopie kwam één
  niveau dieper te staan: `Label/Release/Release/`. Er werd geen fout gegooid en niets gelogd. De
  opruimtak die de bron verwijdert sloeg pas aan bij de dérde kopie, als die geneste map óók al
  bestond -- dan pas gaf `shutil.move` een `shutil.Error`. Op productie hebben **429** releasemappen
  zichzelf op die manier ingeslikt, met als zichtbaar gevolg dat dezelfde track twee keer in de
  bibliotheek staat. De mover kijkt nu vóór de verhuizing of het doel bestaat en gebruikt daarna
  dezelfde regel als de renamer: gelijke bestandsnamen en -groottes betekent een dubbele download
  en de bron verdwijnt; verschilt de inhoud, dan blijven beide staan met een WARNING. De
  vergelijking zelf verhuisde naar `services/importer/release_compare.py`, want beide stappen
  hebben hem nodig.

- **Het nieuws afspelen in de webinterface gaf "kon niet afspelen" en legde en passant de hele
  MuMa-proxy plat.** De browser haalt een bulletin als blob op omdat een `<audio>`-element geen
  `X-API-Key` kan meesturen, en die 15 MB gaat door `MumaResource`. Gemeten op productie: MuMa
  schrijft het bestand in 0,9 seconde weg, maar de proxy gaf na 30 seconden 504 en de wachtrij
  bleef daarna nog 158 seconden bezet -- die stuurt één verzoek tegelijk, dus elk artiestplaatje
  erachter liep ook in een timeout ("Timeout waiting for MuMa response for artist ..."). De oorzaak
  zat niet in de recorder en niet in het netwerk: `SendQueue` hing een callback aan Wt's
  `bodyDataReceived`, ongeacht of het verzoek streamde. Wt leest in kleine stappen, dus een
  bulletin kwam binnen in tienduizenden read-completions, en elk daarvan werd gekopieerd en naar de
  strand gepost voor een handler die vervolgens niets deed. Die kopie gebeurt nu alleen nog voor een
  verzoek dat de brokken echt gebruikt -- dat is uitsluitend het downloaden van podcastafleveringen.

- **Het script dat het read-only databaseaccount aanmaakt kon niet draaien, en gaf soms stilletjes een
  leeg wachtwoord.** Twee onafhankelijke fouten, allebei zichtbaar geworden toen musicserver op
  2026-09-05 herstartte. Het root-wachtwoord werd gelezen uit `/tmp/.env.music-management`, en `/tmp`
  overleeft een reboot niet — de database was de hele tijd op en gezond, maar het bestand was weg. Er
  wordt nu eerst in de draaiende container gekeken (`docker inspect`), wat net zo goed "wat de stack
  echt gebruikt" is en wél een herstart doorstaat; het bestand blijft de terugval. En de
  wachtwoordgeneratie gebruikte `tr -dc ... | head -c 32`, wat onder `set -o pipefail` een val is:
  `head` sluit de pipe na 32 bytes, `tr` krijgt SIGPIPE en de pipeline eindigt op 141 — maar alleen
  soms, afhankelijk van of `tr` nog een keer schrijft voordat hij het merkt. De eerste run haalde het
  net wel, daarna niet meer, en het script stopte zonder één regel uitvoer. De invoer wordt nu vooraf
  begrensd en met `cut` afgeknipt, en een wachtwoord dat geen 32 tekens is laat het script hard falen.

- **De web-UI toonde het jaar waar de app de hele datum liet zien.** LMS stuurt twee datums: `date`
  is de datum van deze editie, `originalDate` de oorspronkelijke release. MuMa schrijft de datum die
  hij uit de NFO haalt in ORIGINALDATE, dus juist die tweede is de interessante -- een scene-tag als
  `2026-00-00` komt aan als een kaal jaar, terwijl `originalDate` `2026-09-03` bevat. De web-UI las
  alleen `date` en toonde dus "2026", terwijl "Recent uitgebracht" wél op de originele datum
  sorteerde: dezelfde track beweerde twee dingen op één scherm. De keuze volgt nu dezelfde regel als
  de Android-app al gebruikte -- neem de originele datum alleen als hij minstens zo precies is -- en
  staat in één gedeelde `trackDate.js` in plaats van twee kopieën van dezelfde datumfunctie.

## [0.45.0] - 2026-09-04

### Fixed
- **Een archief met één rare bestandsnaam liet de helft van zijn releases nooit binnen.** patool
  koos in dit image zelf `unrar-free`, en die breekt de héle extractie af bij de eerste naam die hij
  niet naar de locale van de container kan omzetten: `Pathname cannot be converted from UTF-16BE to
  current locale`. In `HC-2026-WEEK-34-MP3.rar` was één release met zero-width spaces in de
  bestandsnamen genoeg -- 13 van de 44 releases stonden op schijf, de andere 31 nooit. En omdat de
  fout vóór het opruimen van het archief viel, bleef hetzelfde archief elke cyclus opnieuw
  uitpakken en opnieuw falen. De importer probeert nu `unar` en daarna `7z` zodra patools eigen
  keuze faalt; beide lezen die namen wel. Een andere locale in de container helpt niet, dat is
  gemeten. Faalt élke backend, dan blijft het archief liggen met één ERROR-regel waarin alle drie
  de redenen staan.
- **Een release die je twee keer downloadde liep eeuwig vast bij het hernoemen.** `os.rename` naar
  een bestaande, niet-lege map geeft `ENOTEMPTY (39)`, en dat is in Python geen `FileExistsError`.
  De opruimtak werd dus overgeslagen, de melding kwam op INFO binnen tussen het gewone verkeer, en
  de map werd elke ronde opnieuw geprobeerd. Beide botsingen worden nu op dezelfde plek afgehandeld:
  komen de twee mappen op elke bestandsnaam en elke bestandsgrootte overeen, dan is het een dubbele
  download en verdwijnt de bron; verschillen ze, dan blijft alles staan met een WARNING die zegt
  waarom. Vergelijken gebeurt op namen en groottes, niet op hashes -- een release hashen is minuten
  NAS-verkeer per map, elke cyclus opnieuw.

### Added
- **De releasedatum-backfill kan nu op productie draaien, en zegt vooraf wat hij niet kan
  schrijven.** Het script stond alleen in de repository en geen enkele productie-image bevat
  `scripts/`, dus er was geen manier om het daar te starten zonder een checkout. Het draait nu als
  eenmalige container uit de tools-image (`release-date-backfill`), met de dry run als
  standaardcommando. Nieuw is `--check`: dat opent elk gepland bestand op `'r+b'` — precies de
  vraag die mutagen straks stelt — zonder één byte te schrijven, en meldt hoeveel bestanden
  geweigerd worden, welke dat zijn en per labelmap hoeveel. `os.access` is daar geen vervanging
  voor: die antwoordt uit de mode-bits, en juist een NFS-export of een Synology-ACL spreekt die
  tegen. Dat is hoe de vorige poging misging, met een tagger die meer opgeslagen bestanden meldde
  dan hij werkelijk geschreven had.

## [0.44.4] - 2026-09-04

### Fixed
- **Een artiest met een spatie in zijn naam gaf 400 Bad Request op zijn eigen bewerkpagina.**
  `GET /muma/api/curation/artists/Silky%20Noize` kwam nooit bij een route aan. Wt levert het pad
  al gedecodeerd af, en de algemene proxy in `MumaResource` stuurde dat letterlijk door -- met een
  echte spatie in de request-regel, waar MuMa alleen 400 op kan antwoorden. Het pad wordt nu
  opnieuw gecodeerd voordat het de deur uit gaat, waarbij `/` scheidingsteken blijft en de
  querystring onaangeroerd blijft. Dit gold voor elke naam met een spatie, een `&` of een
  niet-ASCII-teken, dus ook labels en genres, en voor de PUT/POST/DELETE-kant net zo goed.

## [0.44.3] - 2026-09-03

### Changed
- **Lineups zijn een boom geworden in plaats van een lijst van 393 regels.** De server meldt een
  podium, zijn editie en zijn festival als drie losse lineups, en die stonden allemaal naast elkaar
  op één pagina. Web en app tonen nu één niveau tegelijk: eerst de festivals, dan de edities, dan de
  podia. Binnen een niveau staat "Alles van ..." vooraan, want een editie is zelf ook een lineup en
  zou anders onbereikbaar worden. Zoeken kijkt langs het niveau heen naar alle lineups tegelijk en
  zet er bij waar een treffer vandaan komt, want "defqon 2014" typen is sneller dan er heen klikken.
  Op het web heeft elk niveau zijn eigen adres, in de app loopt de terugknop de boom weer omhoog.

## [0.44.2] - 2026-09-03

### Changed
- **Beheer en Instellingen hebben een knop terug.** De vorige-knop van de browser deed dit al, maar
  niets in beeld zei dat. De knop loopt de geschiedenis terug zoals je gekomen bent, en valt terug
  op de startpagina als je rechtstreeks op een beheer-URL binnenkwam en er dus niets van ons achter
  je ligt.
- **De bibliotheek toont alleen nog de ingangen die de gekozen modus kan beantwoorden.** Podcasts en
  festivals zijn opnames: de tagger schrijft geen van beide tags onder de tien minuten, dezelfde
  grens waar nummers-modus onder zoekt, dus die lijsten konden daar per definitie niets bevatten.
  Labels en lineups gaan over releases en geboekte artiesten en verdwijnen omgekeerd uit sets-modus.
  Artiesten, albums, genres en jaren staan in allebei.

## [0.44.1] - 2026-09-03

### Fixed
- **De back-merge naar develop viel bij elke release om, zonder dat er iets mis was.**
  `release:back-merge-develop` opent de MR en wachtte dan dertig seconden tot GitLab hem
  "mergeable" zou noemen. Maar een MR van een seconde oud draait zijn eigen pipeline, en het project
  eist dat die groen is -- dus die status is minutenlang `ci_still_running`, niet `mergeable`. Het
  script wachtte zijn budget op, merge-de alsnog, kreeg een kale `405 Method Not Allowed` terug en
  meldde dat als een conflict. Vier releases op rij is die job daardoor rood geworden terwijl er
  niets aan de hand was. Hij zet nu GitLab's auto-merge aan en stopt: de merge gebeurt zodra de
  pipeline groen is, zonder dat er een runner op staat te wachten. Alleen wanneer er echt een mens
  nodig is -- een conflict, een geblokkeerde MR -- stopt hij rood, mét de status waarop hij afsloeg
  in plaats van de foutmelding van een merge die tóch geweigerd zou worden.

## [0.44.0] - 2026-09-03

### Added
- **Het aantal nummers dat een lijst per keer ophaalt is nu instelbaar.** Dat stond vast op 50, wat
  op een trage verbinding lang wachten is en op een snelle onnodig veel verzoeken. De keuze staat
  bij Instellingen > Interface, geldt voor de nummerlijst en de geschiedenis, en reist met je
  account mee naar je andere apparaten.

### Fixed
- **De vorige-knop van de browser sloeg een pagina over.** Alles waar je binnen de app op klikte --
  een label, een genre, een artiest, een album, een zoekresultaat -- veranderde wel het scherm maar
  niet de URL, omdat het Dashboard zijn eigen kopie van de weergave bijhield. Van Labels naar Art of
  Creation en dan terug kwam je daardoor op de startpagina uit. Die kopie is nu dezelfde als die van
  de app, dus elk scherm heeft weer zijn eigen adres.
- **Vorige in willekeurige modus koos opnieuw willekeurig.** Ging je van A naar F, dan bracht vorige
  je op een derde nummer in plaats van terug naar A. Willekeurig afspelen onthoudt nu welk spoor het
  aflegde: vorige loopt dat terug en volgende loopt het weer vooruit voordat er iets nieuws wordt
  getrokken.
- **"Nieuws van het uur" meldde dat er geen bulletin was terwijl er een klaarstond.** Een bulletin
  van tien minuten is ongeveer 15 MB en de proxy naar MuMa bufferde tot 10 MB, dus de overdracht liep
  een tijdje en brak dan af. De proxy heeft nu ruimte voor een opname, geeft het inhoudstype door
  zodat de speler het bestand aanneemt, en de melding maakt voortaan onderscheid tussen "niets
  opgenomen" en "het kwam niet aan".

### Changed
- **Beheer staat nu onder je gebruikersnaam in plaats van in een schakelaar links.** De schakelaar
  hield het beheer en de speler uit elkaar als twee standen, terwijl het gewone pagina's met een
  eigen adres zijn: je gaat er nu heen via het menu onder je naam en met de vorige-knop weer terug.
- **De pagina Labelvoorstellen ziet eruit als de rest van het beheer.** Ze gebruikte klassenamen die
  nergens gedefinieerd waren, dus ze werd als kale tekst getoond. Elk voorgesteld label is nu een
  paneel met een tabel eronder, zoals bij genre- en podcastcuratie.

## [0.43.0] - 2026-09-03

### Added
- **Een lineup mag nu per podium en per editie worden vastgelegd.** De lineupmap las alleen losse
  bestanden, dus "Defqon.1", "Defqon.1 2014" en de RED-stage van die editie waren drie bestanden die
  dezelfde namen herhaalden. Een lineup is voortaan het pad naar zijn bestand
  (`Defqon.1/2014/RED`), en elke map op dat pad is zelf ook een lineup: die van de editie over al
  haar podia, en die van het festival over al zijn edities. Geen enkele artiestennaam staat daardoor
  twee keer opgeschreven. Bestaande platte bestanden blijven werken zoals ze werkten. Het
  importscript kreeg er `--stage` voor, en zet het bestand meteen op de goede plek.

### Fixed
- **De lineupnaam uit een verzoek werd rechtstreeks een bestandspad.** `festivalLineup=../../...`
  wees daarmee buiten de lineupmap. De naam wordt nu tegen die map opgelost en geweigerd zodra hij
  eruit stapt.
- **De app: de speler laadde geen enkele afspeellijst meer in.** Nummers aan de wachtrij toevoegen
  deed niets, zonder foutmelding. De speler-sessie kende de app sinds de media3-versiesprong geen
  enkel commando meer toe, en media3 laat een niet-toegekend commando stilzwijgend vallen.

## [0.42.2] - 2026-09-03

### Changed
- **De app meldt nu of het vullen van de wachtrij is aangekomen.** Een diagnostiekrapport liet zien
  dat honderd nummers werden toegevoegd en dat de wachtrij een milliseconde later nog leeg was,
  zonder dat de speler-sessie het verzoek ooit zag. Media3 laat zo'n verzoek stilzwijgend vallen als
  de controller niet verbonden is of het commando niet is toegekend, dus de app legt nu allebei vast
  op het moment van toevoegen.

## [0.42.1] - 2026-09-03

### Fixed
- **Instellingen opslaan voor een onbekende gebruiker gaf 500 in plaats van 404.**
  `POST /api/users/{id}/settings/{app}` liet de insert op de foreign key stuklopen, en dat leest als
  een kapotte server in plaats van als een aanroeper die een gebruiker noemt die er niet is. De app
  deed precies dat een dag lang, met `user_id=0`. Het bestaan van de gebruiker wordt nu eerst
  gecontroleerd.

## [0.42.0] - 2026-09-02

### Fixed
- **Een genre-besluit bereikte de draaiende tagger niet.** `POST /api/rules/genres/{id}/decide`
  markeerde de bestanden voor een retag, maar de tagger leest zijn genre-regels uit een helper die
  bij het opstarten is geladen en niet werd ververst -- de podcast-beslissing deed dat al wel. De
  retag die het besluit zelf in gang zette schreef het bestand dus terug met het genre nog op de
  oude manier opgelost, tot een herstart. Het besluit ververst nu `genre_rules`, zoals de
  curatiepagina's al deden voor hun regels.
- **Een uitgeschakeld account bleef tot vijf minuten doorspelen op LMS.** LMS onthoudt een
  goedgekeurd wachtwoord vijf minuten zonder music-manager opnieuw te vragen (de auth-cache uit de
  thread-pool-fix), dus `disable` bereikte de speler pas bij het eerstvolgende *ongecachte* verzoek.
  Uitschakelen en inschakelen porren nu de gebruikerssync van LMS, precies zoals de eerste-admin-setup
  dat al deed, en LMS gooit bij elke sync zijn hele auth-cache weg. De e2e-feature die dit gat
  vorige keer vastlegde bewijst nu ook het omgekeerde: een account dat LMS al binnenliet wordt bij
  het volgende verzoek geweigerd, niet bij het verlopen van een timer.

### Added
- **Eén doc dat zegt waar MuMa voor is, in plaats van negentien die zeggen hoe het werkt.**
  `docs/product-goal.md` legt het doel vast: elke combinatie van genre, jaar, artiest, label,
  festival en rating wordt een speelbare lijst. Downloaden, taggen en eigen bestandsbeheer zijn
  middelen. Wat er nergens anders stond en nu wel: de datumregel per materiaalsoort (nummers en
  sets op releasedatum, livesets op draaidatum met releasedatum als fallback), dat de regels de
  waarheid zijn en zowel de bestanden als de database uitvoer, dat MuMa het archief is en LMS de
  werkkopie, en de risico-volgorde waarin onherstelbaar verlies boven storingen gaat — waarmee
  tagger, downloader, importer en scanner een zwaardere bewijslast dragen dan de speler.

  Drie docs zijn erop bijgewerkt. `docs/analyzer-jobs.md` is verwijderd: het beschreef een tweede
  scanner met `analyzer/jobs/handlers.py` en `POST /api/v1/analyzer/library/scan`, en geen van die
  paden bestaat in deze repo. `docs/machine-learning.md` is herlabeld als onuitgevoerd voorstel,
  want het is een gespreksverslag over modellen die nooit gebouwd zijn. In
  `docs/architecture/responsibilities.md` stond dat ratings terug naar LMS geduwd kunnen worden en
  in `docs/designs/ratings-scrobbling/functional.md` stond die vraag nog open; beide zeggen nu
  hetzelfde als de doel-doc, namelijk dat de sync één kant op loopt en dat dat de bedoeling is.
- **Een lineup met de hand invoeren, en vooraf zien wat hij matcht.** `/music/metadata/festival-lineups`
  is leeg sinds de map bestaat, dus de Lineups-pagina op het web en de lineup-browse op de telefoon
  werken allebei en tonen niets. Een affiche typ je over van het festival zelf -- Partyflock, in de
  spec als voorkeursbron genoemd, verbiedt scrapers (artikel 5) en hergebruik zonder toestemming
  (artikel 6). Wat overtypen lastig maakt is de match: `getSpotifyTracks` filtert met
  `LOWER(artist_display_name) IN (...)` op de *hele* weergavenaam, dus een regel die deze
  bibliotheek anders spelt draagt stilzwijgend niets bij. `scripts/import_festival_lineup.py` leest
  het affiche, controleert elke regel tegen de artiestnamen die LMS werkelijk heeft, en meldt wat
  matcht, wat niet, en welke namen in de bibliotheek er het dichtst bij liggen -- voordat er iets
  wordt weggeschreven. Uit de bibliotheek zelf afleiden is geprobeerd en verworpen: warm-up mixes,
  livesets en podcast-afleveringen dragen dezelfde FESTIVAL-tag, dus dat "affiche" liep vol met
  namen die nooit op de line-up stonden.
- **e2e: een afgekeurd genre verdwijnt uit bestand, bibliotheek én speler.** `genre_rejected.feature`
  keurt het genre van de fixture af, laat de retag draaien, wacht tot de wachtrij leeg is, ziet de
  scanner het genre van de track halen en laat LMS herindexeren tot ook die het niet meer meldt.
  Het is de eerste feature die de bytes van de fixture verandert, en hij vond bij de eerste run twee
  dingen: het cache-gat hierboven, en dat de tagger een bestand los in de root van het volume nooit
  bezoekt (hij loopt alleen labelmappen, kanaalmappen en een vaste lijst generieke mappen). De
  fixture staat daarom voortaan onder `Top 100`, en `TAGGER_SLEEPTIME` staat in de teststack op een
  dag zodat de achtergrondronde niet zelf tussendoor gaat herschrijven.
- **De volgorde van de e2e-features staat nu in `conftest.py`, niet in hun bestandsnamen.**
  `FEATURE_ORDER` plus een `pytest_collection_modifyitems`-hook; een module die er niet in staat draait
  erna, op naam. De docstrings die op alfabetische volgorde leunden verwijzen nu naar de lijst.

## [0.41.0] - 2026-09-02

### Changed
- **De clang-tidy-image draait op alpine 3.24, en daarmee op LLVM 22 in plaats van 19.** Drie
  versies verder betekent nieuwe checks over ongewijzigde code: `server:lint` viel om op 259
  bevindingen, waarvan het grootste deel uit checks die in LLVM 19 niet bestonden
  (`misc-override-with-different-visibility`, `cppcoreguidelines-pro-bounds-avoid-unchecked-container-access`,
  `readability-inconsistent-ifelse-braces`, `misc-use-internal-linkage`,
  `bugprone-throwing-static-initialization`) en de rest uit herschreven meldingsteksten van
  bestaande checks, die de baseline op inhoud sleutelt. De baseline is opnieuw gegenereerd; de
  nieuwe secties dragen een noot dat ze bij de upgrade in één keer zijn geaccepteerd en bij de
  volgende aanraking van het bestand alsnog een audit verdienen. Een nieuwe vindplaats onder zo'n
  check laat de job nog steeds falen.
- **Elke component heeft nu een coverage-vloer, en die staat net onder het huidige cijfer.** Python
  ging van 92 naar 93 (CI meet 94,0), de frontend-drempels van 81/61/79/80 naar 82/65/79/81 (CI meet
  82,4/66,8/80,0/81,9). Mobile en server hadden geen vloer: `mobile:unit` houdt nu 16 vast (meet
  16,9) en `server:unit` 39 (meet 40,0). Het zijn ratels, geen doelen: omhoog zodra het cijfer
  klimt, nooit omlaag om een build groen te krijgen. `MOBILE_COVERAGE_MIN` en `SERVER_COVERAGE_MIN`
  overrulen ze lokaal, zoals `COVERAGE_MIN` dat al deed voor Python.
- **`server:unit` rapporteerde helemaal geen coverage-cijfer.** De `coverage:`-regex leest een
  `TOTAL`-regel die gcovr binnen de docker-build print, en buildkit vouwt die weg -- op een gecachte
  laag komt hij zelfs niet voorbij. Het script leest het totaal nu zelf uit de XML en print het op
  zijn eigen stdout in de vorm die de regex verwacht, dus GitLab laat het cijfer voortaan zien.

### Added
- **Unit-tests voor de drie minst gedekte modules van music-manager.** `routers/songs.py` (26%),
  `song_version_worker.py` (22%) en `scrobble_rematch.py` (52%) hadden hun regels wel gepind in pure
  functies, maar niet wat eromheen zit: dat een track met twee bestanden op zijn beste wordt gescoord
  en niet op zijn laatste, dat een pin de score verslaat en de ranking dan niet eens meer draait, dat
  een split oud én nieuw werk herberekent, dat de match-ladder stopt bij de eerste treffer en een
  uitgeschakelde trap nooit draait, dat fuzzy nooit buiten de kandidaten van een exacte sleutel komt,
  en dat elke listen apart wordt gecommit zodat een halve pass houdt wat hij koppelde.
- **e2e: tien foute wachtwoorden sluiten het account, niet de installatie.** `account_throttled.feature`
  gokt tien keer fout via de Subsonic API en laat zien dat LMS het account daarna als throttled meldt,
  ook met het juiste wachtwoord, en dat de admin gewoon doorwerkt. Onderweg bleek de emmer niet het
  account alleen te zijn maar adres-plus-account: een rechtstreekse aanroep vanaf de host valt in een
  andere emmer dan LMS's container. De feature zegt dat en leest de 429 daarom via LMS. Dat laatste is het incident van augustus: de limiet zat op client-adres, en voor
  LMS is elk verzoek hetzelfde adres. De account-features delen nu één stap in `conftest.py` die een
  account aanmaakt, naar LMS synct en wacht tot de admin hem in `getUsers` ziet.
- **De end-to-end keten dekt vier gaten meer.** `muma:e2e` liep tot nu toe de scan, de Subsonic-zoekopdracht,
  de stream, de rating-hop en één rechtstreekse scrobble na. Vier nieuwe Gherkin-features onder `tests/bdd/`
  lopen wat daar omheen zat en in productie al eens stuk is geweest: een play die via LMS's `/rest/scrobble`
  binnenkomt en als match landt in plaats van als unmatched (de echte route van telefoon en auto, die tot
  nu toe geen enkele test aanraakte); een genre-goedkeuring die de wachtrij verlaat, als besluit wordt
  vastgelegd en het bestand voor een retag markeert; de standaard-afspeellijst die een ongewaardeerd nummer
  aanbiedt aan een luisteraar die nog nooit een ster gaf; en een account dat in music-manager wordt
  uitgeschakeld en door LMS wordt geweigerd, zonder herstart of hersync. Die laatste legde onderweg vast wat
  niemand had opgeschreven: LMS onthoudt een goedgekeurd wachtwoord vijf minuten (de auth-cache uit de
  thread-pool-fix), dus een account dat al in gebruik was blijft op LMS zolang werken. De feature zegt dat
  hardop en test daarom met een account dat LMS wel kent maar nog nooit heeft binnengelaten. De volgorde van
  de features is bewust: elke nieuwe module sorteert achter de feature waarvan hij de uitgangssituatie
  verandert, en zegt dat in zijn docstring.

### Fixed
- **De podcast-tag bereikte nooit een bestand, dus de podcast-browse bleef leeg.** `podcast` en
  `podcast_episode` stonden in elke tag-map, maar in geen van de twee registratieblokken die mutagen
  de eigen tagnamen leren -- die lijst stond twee keer in de boom (`tagger.py` en `Song/BaseSong.py`)
  en is uit elkaar gegroeid. Op een MP3 gooide de schrijfactie daardoor `EasyID3KeyError: 'podcast'
  is not a valid key`, en dat gebeurde midden in `save_file`: het bestand werd niet opgeslagen, dus
  *alle* andere tags die de regels net voor dat bestand hadden bepaald gingen mee. Zichtbaar was daar
  niets van, want de parallelle worker gaf de fout terug in plaats van hem te loggen en `parse_folder`
  gooit die teruggave weg -- op productie 651 regels "Set tag podcast" in 24 uur, nul tags op schijf en
  nul fouten in het log. Drie dingen zijn recht: de registratie staat nog maar op één plek
  (`services/tagger/tag_registration.py`) en dekt beide podcast-tags, een tag die het formaat weigert
  laat de rest van het bestand voortaan staan in plaats van de hele opslag mee te nemen, en de
  parallelle worker logt zijn fout. Let op: de bestanden zelf zijn hiermee nog niet getagd -- de
  tagger leest ze de volgende ronde opnieuw (ze zijn nooit als verwerkt weggeschreven), en LMS toont
  een podcast pas als `PODCAST` in *extra tags to scan* staat.
- **De beheerpagina laadde niets meer en zei "Kon gegevens niet ophalen van de Management API".**
  Elke `/muma/api/...`-aanroep loopt via de LMS-proxy, die per aanroep een http-thread vasthoudt en
  alles boven de helft van de pool weigert -- tien op productie -- met een 503 en de kale regel
  `Too many requests to MuMa in flight`. De pagina vuurde er elf tegelijk af, dus de laatste kwam
  altijd als 503 terug; `res.json()` struikelde daarover met `Unexpected token 'T', "Too many r"...`
  en één mislukte aanroep nam het hele scherm mee. Het scherm houdt er nu vier tegelijk in de lucht
  (`mapWithLimit`) en zit een weigering uit in plaats van hem te melden (`fetchMumaJson`), want de
  ruimte wordt gedeeld met alles wat op dat moment nog meer met MuMa praat -- de artiestafbeeldingen
  van de speler voorop. Een antwoord dat geen JSON is levert voortaan een foutmelding met de status
  erin, in plaats van een parse-fout die naar de verkeerde kant van de verbinding wijst. `apiGet`
  van de Advanced Library-tab, die zes analyses tegelijk opvraagt, zit een weigering nu net zo uit.

## [0.40.1] - 2026-09-01

### Fixed
- **`security:secret-scan` liep tegen zijn tijdslimiet en liet daarmee releases stranden.** De job
  groeide deze maand van vier naar veertien minuten, tegen een limiet van vijftien, en viel om zodra
  er iets zwaars naast draaide. De oorzaak zijn de drie emulator-core dumps: die zijn wel uit de
  werkboom gehaald maar blijven bereikbaar in de historie, en gitleaks pakt elke blob uit die hij
  langsloopt -- dus herleest hij 3,9 GB bij elke run. Ze staan nu in de pad-uitzonderingen van
  `security/gitleaks.toml` en de scan doet er **30 seconden** over in plaats van 834.

  De reden bij die uitzondering is bewust een andere dan bij de regels erboven. Die gaan over
  bestanden die geen echte credential kúnnen bevatten; een core dump is een geheugenafdruk en kan
  dat juist wél. Daarom zijn ze eerst gescand en pas daarna uitgezonderd -- gitleaks heeft ze
  wekenlang bij elke run gelezen en niets gevonden. Het zijn bovendien drie vaste blobs die niet
  meer in de boom staan, dus deze uitzondering kan nooit stilletjes nieuwe inhoud gaan dekken.
- **De backupjob kon niet starten omdat een andere service in hetzelfde compose-bestand naar een
  database verwees die daar niet in stond.** De timers draaien hun compose-bestand standalone, en
  docker-compose v1 -- wat productie draait -- valideert het hele bestand voordat het één service
  start. `run --rm db-backup` stierf daardoor op `Service 'soundcloud-fetcher' depends on service
  'db' which is undefined`: een melding die naar de backup wijst terwijl het probleem de indeling
  van het compose-bestand is. De twee backupservices staan nu in een eigen
  `docker/docker-compose.backup.yml` dat op zichzelf klopt; een `depends_on` hebben ze niet nodig,
  want ze verbinden over het externe netwerk en falen luid als de database er niet is. Vier tests
  bewaken dat het bestand zelfstandig blijft werken en dat de units bestaande services aanroepen.
- **De herstelproef weigerde te starten op precies de read-only mount die hem veilig maakt.** Hij
  hergebruikte de padvalidatie van de backupjob, en die eist schrijfrechten -- terecht voor een job
  die dumps wegschrijft, maar de proef mount de dumpmap bewust alleen-lezen omdat een controle die
  zijn eigen bron kan overschrijven geen controle is. Twee juiste eisen die elkaar tegenspraken; de
  validatie kent nu `require_writable`, en de proef zet hem uit.
- **De herstelproef had superuser-rechten nodig voor twee views, en krijgt die niet.** De dump
  schrijft de views met een `DEFINER`-clausule, en zoiets terugzetten namens een ander account
  vereist `SET USER` -- een recht waarmee je je als elke gebruiker kunt voordoen, veel te breed voor
  een wekelijkse controle. De dump blijft ongewijzigd, want een echte restore draait als root en een
  getrouwe dump is het hele punt; alleen de proef haalt de clausule uit de stroom terwijl hij hem
  inleest. Die vervanging is bewust smal: alleen regels die met `/*!<nummer> DEFINER=` of
  `CREATE DEFINER=` beginnen, zodat een van de miljoenen INSERT-regels die toevallig de tekst
  bevat onaangeroerd blijft.

## [0.40.0] - 2026-09-01

### Added
- **Databasebackups die zichzelf bewijzen, in plaats van bestanden die er staan.** Het ontwerp uit
  `docs/superpowers/specs/2026-08-02-daily-db-backups-design.md` is gebouwd: `tools/db_backup.py`
  dumpt, verifieert, schoont op en klaagt als dat niet lukte. Drie systemd-timers in
  `scripts/backup/systemd/` doen 's nachts de dump, 's ochtends een verval-controle en zondags de
  herstelproef. Waarom het nodig was: het nieuwste bestand in `/muma/backups` was van 23 juli, er
  stond een dump van 0 bytes uit 5 juli tussen, en niemand had dat gezien.

  De verificatie is niet cosmetisch. `mariadb-dump | gzip > bestand` levert een geslaagde exit op
  als alleen de eerste helft faalt -- dat is precies hoe die dump van 0 bytes ontstond -- dus het
  comprimeren gebeurt nu in het proces zelf en er is één exitcode om te controleren. Daarnaast een
  ondergrens op de bestandsgrootte en de `-- Dump completed`-trailer, die een halverwege afgekapte
  dump onderscheidt van een complete.

  **De herstelproef is wat "backup" van "bestand" onderscheidt.** De job schrijft naast de dumps een
  `latest.json` met een exacte `COUNT(*)` per tabel; `tools/db_restore_check.py` zet de nieuwste
  dump wekelijks terug in een wegwerpdatabase en vergelijkt daartegen. Een verdwenen tabel, een
  leeggelopen tabel of een afgekapt bestand vallen daar ver buiten. De marge van 2% is rekenkunde,
  geen speling: `--single-transaction` fotografeert bij aanvang en de tellingen worden erna gelezen,
  dus een tabel waar constant bij geschreven wordt komt legitiem iets korter terug.

  **De verval-controle bestaat twee keer, met opzet.** Het ontwerp benoemde de gat eerlijk: een cron
  die helemaal stopt produceert geen fouten en dus geen alarm. Dat gat is precies wat vijf weken
  lang open stond. Dus meldt de timer het zelf én rapporteert music-manager het via
  `GET /health/backup`, dat 503 geeft zodra de nieuwste dump over de limiet is. Die tweede is de
  enige die blijft werken als hier alles stilvalt, want de Uptime Kuma-monitor die hem pollt draait
  ergens anders. Bewust los van `/health`: een verlopen backup is een echt probleem, maar geen
  storing van de dienst, en dat door elkaar halen laat de verkeerde pieper afgaan.

  `scripts/backup/install-systemd.sh` weigert te installeren als `HOST_BACKUP_PATH` op hetzelfde
  device staat als de datadir. Dat is geen pietluttigheid maar de toestand waarin prod verkeerde:
  `/muma/backups` en `/docker/music-management/mariadb` waren twee paden op één schijf, dus elke
  ooit gemaakte dump zou zijn verdwenen samen met wat hij beschermde. De job zelf kan dat niet zien
  -- die draait in een container zonder de datadir -- dus die check hoort op de host.
- **Een disk-janitor voor de CI-runners, zodat een volle schijf niet langer willekeurige jobs
  sloopt.** Drie keer deze maand liep een runner vol, en de storing wees telkens overal heen behalve
  naar de schijf: op 31 augustus faalden drie van de vier jobs op `no matching files` bij het
  uploaden van artifacts en noemde alleen `docker:build-images` de echte oorzaak. Het handmatige
  opruimrecept uit die incidenten zit nu in `scripts/ci/disk-janitor.sh`: per repository blijven
  `:latest`, `:stable` en de drie nieuwste versietags staan, van de Android-CI-images (>5GB per
  stuk) de twee nieuwste, en achtergebleven `muma-test-*`-stacks ouder dan twee uur gaan weg. Nooit
  met `-f`, zodat een image dat een lopende pipeline nog vasthoudt geweigerd wordt in plaats van
  weggerukt, en de buildkit-cache blijft met opzet ongemoeid — dat is de ccache die
  `muma-server:unit` op ~90s houdt in plaats van ~405s. De keuzelogica staat apart in
  `disk_janitor_plan.py` en wordt door tien tests gedekt zonder dat er een Docker-daemon of een
  volle schijf aan te pas komt. Draait geveegd tot 65% en stopt daar, zodat een runner die net
  boven de drempel zit niet elke keer één image opoffert. Loopt via een geplande pipeline
  (`DISK_JANITOR=true`) op de LXC — de job is expres ongetagd, want dat is precies wat hem altijd op
  de altijd-aanstaande host laat landen; voor andere hosts liggen er systemd-units in
  `scripts/ci/systemd/`. Faalt de job, dan is dát de bevinding: alles wat veilig weg kon is weg en
  de ruimte zit in de buildcache of buiten Docker.

### Changed
- **De crash-triage-skill strijkt de trailing slash uit `NTFY_URL`.** De notify-stap bouwde de URL
  als `$NTFY_URL/$NTFY_TOPIC`; eindigt `NTFY_URL` op een slash, dan antwoordt ntfy op de dubbele
  slash met een 301 die curl niet volgt, en verdwijnt de melding geruisloos (zo miste het bericht
  van e2e-testrapport 20). De skill gebruikt nu `${NTFY_URL%/}/$NTFY_TOPIC` en legt uit waarom.
- **muma-mobile bouwt zijn SBOM met `org.cyclonedx.bom` 3.4.1.** De 3.x-plugin splitst de ene
  `cyclonedxBom`-taak in tweeën: een `cyclonedxDirectBom` per project die de configuraties oplost,
  en `cyclonedxBom` die de resultaten samenvoegt. `includeConfigs` verhuisde daarmee naar die eerste
  taak, dus de losse `cyclonedxBom { includeConfigs = ... }` uit 2.x is vervangen door een
  `allprojects`-blok dat elke `cyclonedxDirectBom` op `releaseRuntimeClasspath` en
  `runtimeClasspath` zet. Dat het bij één `plugins`-regel op het rootproject blijft, is geen
  toeval: `CyclonedxPlugin.apply` registreert de directe taak ook in de submodules. De bedoeling
  van vroeger is daarmee overeind: het rapport telt 206 componenten en geen enkele
  detekt-, ktlint- of AGP-afhankelijkheid, waarvan de netty- en bouncycastle-bevindingen niets
  zeggen over de APK die daadwerkelijk verscheept wordt. Het rapport verhuisde van
  `build/reports/bom.json` naar `build/reports/cyclonedx/bom.json`; de halffabricaten per module
  staan in `build/reports/cyclonedx-direct/`. Renovate mag de major weer zelf oppakken.
- **Een mislukte SBOM maakt de dependency-audit rood in plaats van hem over te slaan.**
  `scripts/ci/dependency-audit.sh` zette bij een kapotte SBOM-stap `SKIPPED=1` en liep door, en
  omdat lokaal en op een feature branch ook `PROD_ENV_FILE` ontbreekt, eindigt die run sowieso met
  exit 2 -- een echte breuk in de Android-scan viel dus niet te onderscheiden van de dagelijkse ruis
  en las als een audit die geslaagd was. Zo'n sectie gaat nu in een aparte `BROKEN`-lijst die met
  exit 1 eindigt en bij naam vertelt wat er niet gedraaid heeft: exit 2 blijft voor een tool of
  variabele die er niet is, exit 1 is voor een scanner die alles had en tóch niets opleverde. De
  Gradle-uitvoer wordt bij zo'n mislukking meegeprint (de laatste 40 regels) in plaats van
  weggegooid, want een rode job zonder uitvoer is niet te repareren. Daarbovenop faalt de sectie nu
  ook op een SBOM die wél geschreven is maar minder dan 50 componenten bevat: precies wat een
  verkeerde `includeConfigs` oplevert, en anders een groene scan van vrijwel niets.
- **De mobiele dependencies gaan in één batch omhoog, en media3 vroeg er code voor terug.** Kotlin
  2.4, KSP 2.3, media3 1.11, koin 4.2, navigation 2.10 en een reeks androidx-bumps. media3 1.11
  sluit een deprecatiecyclus af waar de Jukebox-speler nog in stond: `Player` kent
  `hasPrevious`/`previous`/`seekToPreviousWindow` en hun vier Next-tegenhangers niet meer, dus die
  acht `override`s overschreven niets en compileerden niet. Niemand riep ze aan -- ze stuurden
  alleen door naar de MediaItem-varianten die ze vervingen -- dus ze zijn weg. Andersom voor
  `mute`/`unmute`: die staan nu wél in `Player` en hebben een `override` nodig.
- **De crash-triage kent nu een uitkomst voor "geldig rapport, niets te fixen".** Een synthetisch
  testrapport of een handmatig diagnoserapport zonder crash telde als mislukte fixpoging, waardoor
  een tweede identiek rapport na twee keer als opgegeven crash werd afgedaan. De skill zet zo'n
  rapport nu op `done` met ledger-uitkomst `no_defect`, zonder de pogingenteller te raken; de
  serverstatussen zijn ongewijzigd.
- **MariaDB gaat van 10.10 naar 12.3.** 10.10 is al ruim een jaar end-of-life en kreeg geen
  securityfixes meer. De bump raakt `docker/compose.test.yml` en alle drie de
  `docker-compose*.yml`-bestanden, dus ook prod. Let op bij het uitrollen: MariaDB ondersteunt
  officieel één major per keer en dit slaat er ruim tien over, dus de datadir *niet* ter plekke
  laten upgraden. De veilige volgorde is een dump maken, het `db`-volume weggooien en de dump
  terugzetten in de verse 12.3-container; de deploy maakt zelf al een gzipped dump in
  `/muma/backups`, en er staat een handmatige van 2026-08-31 (102 tabellen) klaar. Draai daarna
  `mariadb-upgrade` niet meer -- een geïmporteerde dump heeft dat niet nodig.
- **Een TypeScript-major wacht voortaan op het dependency-dashboard.** TypeScript 7 is de native
  herschrijving en `svelte-check` accepteert die nog niet als gewone upgrade: het weigert te starten
  tenzij TypeScript 6 er onder een npm-alias naast staat en elke aanroep `--tsgo` meekrijgt. Dat is
  een toolchain-migratie, geen versiebump, dus Renovate opent er geen merge request meer voor tot
  `svelte-check` TypeScript 7 op zichzelf aankan.

### Fixed
- **De databaseserver stond na de MariaDB 12-migratie op een andere collatie dan zijn eigen
  tabellen.** MariaDB 11.5 wijzigde de standaard naar `utf8mb4_uca1400_ai_ci`, en de overstap van
  10.10 naar 12.3 erfde die: de teruggezette tabellen hielden hun eigen `utf8mb4_general_ci`, maar
  alles wat er daarna bij gemaakt zou worden niet. Een join tussen die twee geeft `Illegal mix of
  collations` -- een fout die opduikt bij de eerstvolgende nieuwe tabel, ver van de upgrade die hem
  veroorzaakte. De drie productie-composebestanden pinnen de server nu op `utf8mb4_general_ci`, en
  `docker/compose.test.yml` doet hetzelfde, want anders draait CI op een andere collatie dan
  productie en zou juist dit verschil daar groen blijven. De schema's naar `uca1400` tillen is een
  aparte, bewuste klus: dat verandert wat als gelijk telt in een unique key.
- **Alle 22 HIGH-bevindingen in de productie-images van de dependency-audit.** Ze vielen in drie
  groepen en alleen de derde was echt onoplosbaar. Twintig ervan kwamen niet uit dit project maar
  uit de base image: `python:3.14-slim` levert openssl 3.5.6-1~deb13u2 vooraf geinstalleerd, en
  omdat de Dockerfiles alleen `apt-get install` deden bleef die versie staan hoeveel rebuilds er ook
  overheen gingen — Debian-Security had 3.5.7-1~deb13u2 allang klaar (CVE-2026-14456). Hetzelfde
  patroon bij LMS: `alpine:3.23` levert libcrypto3 en libssl3 op 3.5.7-r0 mee, en `apk add` op een
  al geinstalleerd pakket doet niets. `docker/Dockerfile.base`, `.music-manager`, `.tools` en
  `services/music-management-server/Dockerfile-release` upgraden nu eerst, zodat elke release-build
  de securitypocket meepakt in plaats van de bouwdatum van een base image te erven. Dat ruimt ook
  `linux-libc-dev` (CVE-2026-74662) en `sqlite-libs` (CVE-2026-11822, CVE-2026-11824) op, die
  simpelweg ouder waren dan de fix.
- **De laatste twee image-bevindingen staan opgeschreven in plaats van weggekeken.**
  `setuptools 70.3.0` (CVE-2025-47273) en `msgpack 1.1.2` (GHSA-6v7p-g79w-8964) zitten in de
  vendor-boom van pip zelf: pip levert `_vendor/bom.cdx.json` mee om te beschrijven wat het bundelt,
  en trivy leest dat bestand. Een kale `python:3.14-slim` meldt ze allebei voordat er ook maar één
  regel van onze Dockerfiles gedraaid heeft, en pip 26.2.1 is de huidige release — er is geen pip om
  naartoe te upgraden. Ze staan nu in `security/trivyignore` met die reden en met de controle
  waarmee je ze weer weghaalt.
- **De Python-helft van de dependency-audit scande drie van de vijf requirements-bestanden niet.**
  pip-audit lost elk bestand op in een wegwerp-virtualenv van de tooling-interpreter, en die stond
  in `scripts/lib/python-tooling.sh` nog op `python:3.11-slim` terwijl de service-images al op 3.14
  draaien. `librosa~=1.0.0` vraagt Python >= 3.12, dus `requirements.txt`,
  `services/music_manager/requirements.txt` en `services/ml-analyzer/requirements.txt` faalden met
  `No matching distribution found for librosa~=1.0.0` — wat leest als een verkeerde pin en het niet
  is. De reden dat de pin ooit 3.11 was, namelijk dat numpy 2.0.x geen wheel voor 3.13 had, verviel
  bij diezelfde stap: `requirements.txt` staat op `numpy~=2.5.2`, dat zelf >= 3.12 eist. De
  tooling-image volgt nu `docker/Dockerfile.*`. Alle vijf bestanden auditen weer, en `ruff`,
  `pylint` (9.66) en `mypy` draaien ongewijzigd in dezelfde image. Dat de job `allow_failure` is, is
  precies waarom dit maanden rood kon staan zonder gelezen te worden.
- **Twee merge requests die tegelijk hun images bouwden, sloopten elkaars build.** `docker:build-images`
  bouwt zonder te pushen onder een wegwerpnaam, en die naam was voor iedereen dezelfde: `muma-ci`.
  Alle gelijktijdige jobs schreven dus dezelfde tags in de ene image-store die de runner heeft. Op
  31 augustus bouwde pipeline 2074 zijn eigen `muma-ci/muma-base:0.39.0`, gebruikte die voor de
  downloader-image, en viel tachtig seconden later om bij de telegram-image met `pull access denied,
  repository does not exist or may require authorization` — een zusterjob had de tag er tussenuit
  gehaald, waarna buildkit hem op Docker Hub ging zoeken, waar `muma-ci` niet bestaat en ook nooit
  hoort te bestaan. De melding leest als een ontbrekende inloggegeven en is dat niet. Elke job bouwt
  nu onder `muma-ci-<job-id>`, dezelfde behandeling die `db:integration` eerder kreeg, en ruimt die
  naamruimte bij afloop zelf op. De disk-janitor rekent zo'n naamruimte voortaan af op ouderdom in
  plaats van op aantal, want geen enkele job hergebruikt die van een ander — op de oude telling zou
  elke afgebroken job zijn `:latest` voor altijd houden. Wat de release-build pusht verandert niet.
- **Een wijziging in `renovate.json` liet de SAST-scan links liggen die hem wél leest.** De
  `changes:`-regels van `security:sast` noemden het bestand niet, dus de packageRule die in !531
  werd toegevoegd ging ongescand naar develop -- waar semgrep hem alsnog vond, en de eerstvolgende
  merge request rood werd op een bevinding die niets met zijn eigen diff te maken had. `renovate.json`
  staat nu in die regels, en de zesde `renovate-missing-minimum-release-age`-hit is opgenomen in
  `security/accepted-sast-findings.txt` -- de reden die er al stond dekt hem: de regel wil de sleutel
  op elke entry herhaald zien, terwijl Renovate hem van de catch-all overneemt.

- **De Android-build gaat in één keer naar Gradle 9, AGP 9 en compileSdk 37, omdat het los niet kan.**
  Renovate bood deze drie als losse voorstellen aan en alle drie bleven rood, hoe vaak je ze ook
  opnieuw draaide. De reden staat in de foutmeldingen zelf, verspreid over drie taken: androidx.core
  1.19 weigert gebruikt te worden onder compileSdk 37, AGP 8.13 stelt 36 als maximum, en AGP 9 weigert
  te starten onder Gradle 8.14.5. Elk stuk wacht dus op het volgende, en pas de combinatie werkt.

  Dat is het patroon dat deze hele reeks kenmerkte. De androidx-bibliotheken duwden het nummer twee
  keer omhoog: eerst weigerden activity 1.13 en vijftien broertjes onder 36, daarna core 1.19 en nog
  drie onder 37. `checkDebugAarMetadata` meldt zo'n hele partij in één klap, wat eruitziet als een
  kapotte build terwijl er één getal te laag staat.

  `targetSdk` blijft bewust op 35. compileSdk bepaalt welke API's de code mág aanroepen; targetSdk
  bepaalt welk gedrag Android op het toestel van de gebruiker toepast, en dat verhoog je met een test
  op een echt apparaat.

  Android Lint meldde onder AGP 9 dertig bevindingen die de oude baseline niet dekt. Twee daarvan
  waren geen registratiewerk. `NewerVersionAvailable` leest `libs.versions.toml` en vlagt elf
  entries als achterlopend -- dat is Renovate's werk, en elf regels baseline zouden na elke
  dependency-MR alweer verlopen zijn; die check staat nu uit naast `GradleDependency` en
  `AndroidGradlePluginVersion`, die er om precies dezelfde reden al stonden. En `DefaultLocale` wees
  een echte bug aan, apart gefixt. De rest -- `UseKtx`, `TrimLambda`, `ReportShortcutUsage` -- zijn
  nieuwe checks over ongewijzigde code en gaan de baseline in.

  Twee dingen die meemoesten. Het CI-image kende android-37 niet, dus dat staat er nu bij — onder de
  naam `platforms;android-37.0`, want API 37 is de eerste met minor-SDK-versies en het kale
  `platforms;android-37` bestaat niet. sdkmanager meldt dat met één regel `Failed to find package`
  tussen twee voortgangsbalken en stopt dan met een foutcode, wat leest als een netwerkstoring in
  plaats van een verkeerde pakketnaam. De imagetag bevat een hash van het Dockerfile, dus het
  herbouwt zichzelf één keer. En de Gradle-versie in de version catalog stond nog op 8.11.1 terwijl
  de wrapper al op 8.14.5 zat; die waarde stuurt de
  `wrapper`-taak, dus `./gradlew wrapper` zou de wrapper stilzwijgend hebben gedowngraded. Ze staan
  nu allebei op 9.7.1.
- **Een standaard-vervaltijd voor delen opslaan brak de instelling in talen met andere cijfers.**
  `ShareHandler` schrijft `<aantal>:<eenheid>` naar de `defaultShareExpiration`-voorkeur met
  `String.format` zonder locale, en `Settings` leest hem terug met `split[0].toLong()`. In het
  Arabisch, Perzisch of Bengaals levert `%d` cijfers op die `toLong()` niet accepteert, dus
  `NumberFormatException` en een kapotte instelling. Het is een wire-formaat tussen twee regels
  eigen code, dus `Locale.ROOT`. Gevonden door de lint van AGP 9.
- **De Android-app zat in images waar hij niets te zoeken had.** Drie Dockerfiles kopieerden de
  complete `services/`-boom naar binnen, terwijl de containers die eruit rollen alleen Python
  draaien: de tools-image start `soundcloud_fetcher.py` en `process_genres.py`, music-manager is
  bewust API-only en de worker-images draaien downloader, telegram of importer. Meegereisd waren de
  18 MB Kotlin-bron van `services/muma-mobile`, de Svelte-bron van `services/frontend` en de
  C++-bron van `services/music-management-server`. Dat kostte niet alleen ruimte: bij de mobiele
  testresources zit een self-signed certificaat mét private key
  (`core/subsonic-api/src/integrationTest/resources/self-signed.pem`), dat een imagescan terecht
  als gelekt geheim aanmerkt. Elke Dockerfile kopieert nu alleen de pakketten die zijn eigen
  startcommando importeert, en de Android-boom is daarnaast uit elke build-context geweerd, zodat
  een volgende image hem niet opnieuw per ongeluk meeneemt. De frontend en de LMS-bron blijven
  bereikbaar voor de enige build die ze echt nodig heeft,
  `services/music-management-server/Dockerfile-release`.
- **Drie emulator-core dumps van samen 3,9 GB stonden in de repository.** Bij het debuggen van de
  segfault in de emulator-smoketest zijn `services/muma-mobile/core.91`, `core.92` en `core.387`
  meegecommit. Ze zitten sindsdien in elke clone en elke runner-checkout, en dat is de directe
  oorzaak van de `No space left on device`-fouten die dependency-pipelines lieten falen. De
  bestanden zijn verwijderd en `.gitignore` weert `core.[0-9]*` voortaan, zodat een volgende crash
  er niet opnieuw een achterlaat. De blobs zitten nog wel in de git-historie: een clone haalt ze op
  tot die historie herschreven wordt.

### Security
- **Het root-wachtwoord van de productiedatabase stond als platte string in zeven tools.**
  `check_backlog.py`, `check_media.py`, `cleanup_db.py`, `describe_tables.py`,
  `finalize_genres.py`, `integrity_check.py` en `migrate_db_renames.py` droegen alle zeven hetzelfde
  blok: `user = "root"`, het wachtwoord als literal, en `DB_HOST` met `192.0.2.27` als default.
  Wie zo'n script uit een checkout draaide, richtte zich dus als root op productie zonder daarom te
  vragen -- en `migrate_db_renames.rename_tables()` zet foreign key checks uit en hernoemt tabellen.
  De URL komt nu uit `tools/db_url.py`, dat de omgeving leest en niets invult: een ontbrekende
  variabele geeft een foutmelding in plaats van een gok. Een test in `tools/test_tools_imports.py`
  bewaakt dat.

  Verwijderen is niet genoeg: de waarde staat in de git-historie en is daarmee gepubliceerd tot hij
  bij de bron vervangen wordt. `security:secret-scan` sloeg er nooit op aan omdat gitleaks op
  tokenpatronen zoekt en dit een woordenwachtwoord is.
- **De twee backupcontainers draaien met een read-only rootfilesystem.** Ze schrijven maar op twee
  plekken -- het credential-bestand in een tmpfs op `/tmp` en de dumps op de gemounte `/backups` --
  dus hier kon de hardening wél aan, in plaats van de bevinding te accepteren zoals bij de
  langlopende services. Breekt het toch, dan meldt het zich: de systemd-unit faalt en
  `/health/backup` verloopt binnen 36 uur.
- **De music-manager-image draagt geen C-compiler meer met zich mee.**
  `docker/Dockerfile.music-manager` installeerde `gcc`, `libmariadb-dev` en `pkg-config` om een
  handvol wheels te bouwen waarvoor nog geen cp314-wheel bestaat, en haalde ze daarna nooit weg:
  `rm -rf /var/lib/apt/lists/*` gooit alleen de apt-index weg, niet de pakketten. Elke draaiende
  container had daardoor een complete toolchain aan boord, inclusief de kernel-headers uit
  `linux-libc-dev` waar `security:dependency-audit` CVE-2026-74662 op meldde. Het bouwen gebeurt
  nu in een aparte builder-stage; de runtime-stage is een schone `python:3.14-slim` waar alleen de
  virtualenv uit de builder in wordt gekopieerd, plus `libmariadb3` -- de gedeelde bibliotheek, niet
  het `-dev`-pakket met de headers. 135 pakketten werden er 90, en de image ging van 906 MB naar
  696 MB.

  Dit is niet dezelfde reparatie als !545. Die voegde `apt-get upgrade -y` toe en lost de melding op
  door *versie*: de gepatchte `linux-libc-dev` komt binnen bij elke rebuild. Deze lost hem op door
  *afwezigheid*, wat het verschil is tussen "vandaag niet kwetsbaar" en "kan er niet kwetsbaar voor
  zijn" -- en de volgende kernel-header-CVE raakt deze image niet meer. De `apt-get upgrade` blijft
  overigens in beide stages staan, om dezelfde reden als in `Dockerfile.base`.

  Wat er niet meekopieerde is even belangrijk: `pymysql` is pure Python, dus niets in
  `services/music_manager/requirements.txt` heeft bij het *importeren* een compiler nodig. De
  pakketten die wel uit broncode gebouwd worden -- soundfile, soxr, numba, scipy, scikit-learn --
  laden in de runtime-image zonder headers gewoon, wat nagelopen is door ze daar allemaal te
  importeren, en `scripts/test/core-smoke.sh` start de stack nog steeds groen op.
- **`unar` trok een complete build-essential de tools-image in.** Dezelfde kernel-headers zaten ook
  in `docker/Dockerfile.tools`, terwijl daar geen enkele compiler geïnstalleerd wordt. De oorzaak
  was `unar`: dat hangt via `gnustep-base-runtime` aan `gcc`, `g++`, `binutils`, `libc6-dev` en
  graphviz, en sleepte zo `linux-libc-dev` mee. De drie uitpakkers (`unrar-free`, `p7zip-full`,
  `unar`) stonden daar bovendien meegekopieerd uit `Dockerfile.base` en hoorden er nooit: alleen
  `services/importer/extractor.py` roept patoolib aan, en juist dat pakket wordt in deze image niet
  gekopieerd. Ze zijn weg, samen met de recommends. 501 pakketten werden er 314 en de image ging van
  1,85 GB naar 1,28 GB; ffmpeg, ffprobe, mariadb-dump, mariadb, curl en yt-dlp draaien er
  ongewijzigd, en de vijf modules die `tools/test_tools_imports.py` bewaakt importeren er nog.

  `docker/Dockerfile.base` heeft `unar` nog wel, en daarmee dezelfde build-essential in muma-base,
  muma-downloader, muma-telegram en muma-importer. Daar is het niet zomaar weg te halen -- de
  importer pakt er echt archieven mee uit -- dus dat is bewust een aparte vraag gebleven.

## [0.39.0] - 2026-08-31

### Added
- **De crash-triage-runner: van crashrapport naar goedgekeurde fix zonder handwerk ertussen.**
  Nieuw in `scripts/crash-triage/`: een webhook-listener die het rapport-id uit de
  `crash_hook_url`-POST spoolt en er serieel één Claude-triagerun per rapport op draait, een
  approved-MR-watcher (systemd-timer) die crash-fix-MR's met approval én groene pipeline merget en
  daarna de release laat cutten, plus systemd-units, een env-voorbeeld en een runbook-README voor
  de development-VM. De triagerun zelf volgt de nieuwe `muma-crash-triage`-skill in
  `.claude/skills/`: rapport ophalen, release-stacktraces eerst deobfusceren met de gearchiveerde
  R8-mapping, en alleen bij een eenduidige oorzaak een MR openen — mergen mag hij nooit zelf, dat
  blijft aan de approval-watcher na akkoord van Teun. Elke uitkomst wordt gemeld op ntfy-topic
  `music-management-claude`.
- **De R8-mapping van elke release-APK wordt voortaan bewaard.** Release-builds zijn geminificeerd,
  waardoor een stacktrace uit het veld zonder de bijbehorende `mapping.txt` onleesbaar is — en die
  werd tot nu toe nergens gearchiveerd. `publish.sh` zet de mapping naast de APK in `dist/` onder
  dezelfde versienaam (`muma-mobile-v<versie>-<code>-mapping.txt`), en `mobile:build-release`
  bewaart hem als GitLab-artifact zonder vervaldatum. Daarmee kan de crash-triage een
  release-stacktrace eerst deobfusceren voordat er iets geanalyseerd wordt.
- **Een binnengekomen crashrapport kan nu een externe triage-hook wakker maken.** De
  `crash_reports`-tabel kent voortaan een `status` (`new`/`analyzing`/`mr_open`/`done`/`failed`)
  en een `stacktrace_hash`, zodat een geautomatiseerde verwerker dezelfde crash herkent en niet
  twee keer aan het werk gaat. Na het opslaan van een rapport stuurt de server best-effort een
  POST met het rapport-id naar het nieuwe configveld `crash_hook_url` (groep Notifications, leeg
  = uit); de app-respons wacht daar niet op. Voor de verwerker zijn er twee nieuwe endpoints
  achter de system-API-key: `GET /api/diagnostics/crash-reports/{id}` en
  `PATCH /api/diagnostics/crash-reports/{id}/status`. Migratie: `migrate_v17_crash_report_status.sql`,
  met de gebruikelijke kolomguard in de router voor bestaande installaties. Dit is de serverhelft
  van de crash-triage-automatisering; het ontwerp staat in
  `docs/superpowers/specs/2026-08-31-crash-triage-automation-design.md`.

### Fixed
- **Een release-APK kan niet langer geüpload worden terwijl de unit-tests op dezelfde commit rood
  zijn.** `mobile:build-release` had alleen `release:version-check` als `needs`, en `needs`
  omzeilt de stage-volgorde; de gedeelde resource group serialiseert de Android-jobs wel maar
  ordent ze niet. Een falende `mobile:unit` blokkeerde daardoor de deploy, maar niet de
  APK-upload — en telefoons updaten automatisch vanaf de hoster. De job wacht nu expliciet op
  `mobile:unit`.
- **Een release-branch met een open MR draait de pipeline niet meer dubbel.** De bestaande
  dedupe-regel keek naar `$CI_OPEN_MERGE_REQUESTS`, die alleen in push-pipelines bestaat, dus
  release/hotfix-branches kregen een branch-pipeline én een MR-pipeline voor dezelfde commit — met
  twee Android-jobs die om dezelfde Gradle-home vochten. De MR-pipeline wordt nu onderdrukt; de
  branch-pipeline (waar `muma:deploy` in leeft) blijft.
- **`backend:integration` kan geen database van een parallelle pipeline meer slopen.**
  `db-integration.sh` gebruikte één vaste containernaam en poort 13306 en ruimt die aan begin én
  eind van de run met `docker rm -f` op, waardoor twee gelijktijdige pipelines elkaars MariaDB
  midden in de testrun weghaalden (de bekende `2013 Lost connection`-flake). In CI zijn naam en
  poort nu per job uniek (`CI_JOB_ID` plus een vrije poort); lokaal blijft het oude vaste adres
  werken voor `KEEP_DB=1`.
- **Ontbrekende release-secrets laten de pipeline nu vroeg falen in plaats van jobs stil te laten
  verdwijnen.** `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`, `APK_HOSTER_URL` en `SIGNING_STORE_FILE`
  gaten hun jobs op `rules:`-niveau: is zo'n variabele weg (verlopen token, per ongeluk
  verwijderd), dan valt de job geruisloos uit de pipeline — een overgeslagen job blokkeert niets,
  dus prod zou herstarten op oude images of een release zou zonder APK schepen zonder dat iets
  rood werd. `release:check-secrets` controleert deze vier nu expliciet, met een policy-test die
  afdwingt dat elke rules-gatende variabele in het checkscript voorkomt.

### Added
- **Een emulator-smoketest voert voortaan de échte release-APK uit.** De 6.21.0-startupcrash
  (bug-report 029) bestond alleen in de R8-geminificeerde build; unit-tests, detekt en lint zien
  allemaal ongeminificeerde code, dus de eerste uitvoering van een release-build was de telefoon
  van een gebruiker. `mobile:smoke` bouwt de release-APK, boot een headless
  ATD-emulator op KVM (passthrough op de runner-LXC sinds 2026-08-22), installeert, start via de
  launcher-intent (overleeft de icon-aliases) en eist na 15 seconden een levend proces zonder
  `FATAL EXCEPTION`. Een tripwire, geen UI-suite. De job gate't de release: `muma:deploy` wacht
  via de stage-volgorde en `mobile:build-release` heeft hem expliciet in `needs`, zodat een
  crashende APK de hoster nooit bereikt. De CI-image kreeg emulator, platform-tools en het
  `android-34 aosp_atd`-systeembeeld.

### Changed
- **De dependency-audit dekt nu ook Android en de productie-images.** `pip-audit` en `npm audit`
  lazen elk een declaratiebestand, maar de Android-dependencygraf had geen CVE-dekking (Gradle
  heeft hier geen lockfiles) en de gepubliceerde images bevatten een Debian/Alpine-userland dat
  nergens gescand werd. De CycloneDX-plugin schrijft voortaan de opgeloste graf van muma-mobile
  als SBOM (alleen runtime-classpaths — tooling-vondsten over detekt/AGP zeggen niets over de
  APK), en trivy scant die plus de zeven `:latest`-images op HIGH/CRITICAL, met `--ignore-unfixed`
  voor de images zodat onoplosbare base-image-CVE's de job niet permanent rood houden.
  Geaccepteerde vondsten horen met reden in `security/trivyignore`; de job blijft `allow_failure`
  en de timeout ging van 15 naar 30 minuten.
- **Android Lint is nu een gate in `mobile:unit`.** Lint stond volledig geconfigureerd in
  `app/build.gradle` (baseline, `abortOnError`, `warningsAsErrors`) maar geen enkele CI-job riep
  hem aan — dezelfde geschiedenis als detekt destijds. Ondertussen was de baseline verouderd en
  stond develop op 98 ongefilterde errors die nergens zichtbaar werden. De baseline is opnieuw
  gegenereerd (152 bestaande findings, inclusief een aantal echte `MissingPermission`-kandidaten
  die het afbranden waard zijn) en `./scripts/test/muma-mobile-lint.sh` draait voortaan als derde
  stap in de bestaande job: groen vandaag, rood op elke nieuwe finding. Via
  `checkDependencies=true` kijkt `:app:lintDebug` ook naar de core-modules.
- **Kleinere pipeline-reparaties uit dezelfde doorlichting.** Playwright rapporteert nu junit naar
  de GitLab-testtab (`frontend:e2e` had als enige suite geen zichtbare testresultaten);
  `mobile:build-release` is niet langer interruptible, zodat een nieuwe push geen upload
  halverwege afbreekt; `muma:images` ruimt in no-push-modus zijn versie-tags weer op zodat
  de runner-disk niet per release volloopt; een dode subset-regel op `muma:smoke` is weg; de
  verouderde "geen /dev/kvm"-claim bij de e2e-job klopt weer met de werkelijkheid (KVM-passthrough
  staat er sinds 2026-08-22, wat ontbreekt is een emulator-job); en het `.release_rule`-commentaar
  benoemt nu eerlijk welke jobs er wél en niet onder vallen.

## [0.38.1] - 2026-08-29

### Fixed
- **Een mislukte download nam de hele app mee, en dat gebeurde alleen bij slecht bereik.** In
  `DownloadService` telt `RETRYING` als eindtoestand, en de terugmeldfunctie haalde de track daarom
  eerst uit de actieve lijst en ging meteen op zoek naar volgend werk — nog vóór diezelfde track
  terug in de wachtrij was gezet. Op dat moment zag de dienst een lege wachtrij en geen actieve
  downloads, en stopte zichzelf. `onDestroy` zet daarbij het coroutine-bereik op `null`. Er lopen
  standaard drie downloads tegelijk en bij een wegvallende verbinding vallen die vrijwel gelijk om,
  dus de volgende afmelding liep tegen dat lege bereik aan met een `NullPointerException`. Die
  ontstaat in de afrondingshandler van de coroutine, waar de `CoroutineExceptionHandler` niet bij
  kan, en werd dus een harde crash in plaats van een regel in het logboek.

  De volgorde is omgedraaid: de wachtrij wordt bijgewerkt voordat er naar volgend werk wordt
  gekeken. Daarmee verdwijnt ook het stillere gevolg van dezelfde fout — een track die op
  opnieuw-proberen ging werd door het opruimen bij het afsluiten uit de wachtrij gegooid, en
  probeerde het dus nooit echt opnieuw. Verder leest `processNextTracks` het bereik nog één keer als
  lokale waarde en stopt het als de dienst al aan het afsluiten is, en een uitgestelde herstart die
  na dat afsluiten alsnog afgaat doet niets meer.

## [0.38.0] - 2026-08-27

### Added
- **Vier werkwijzes van deze repository staan nu als skill in `.claude/skills/`, zodat een agent ze
  oppakt op het moment dat het ertoe doet in plaats van achteraf.** `muma-release` beschrijft het
  hele pad van `release/x.y.z` tot een geverifieerde tag, `muma-mr-flow` wat er lokaal gedraaid moet
  worden voordat een tak de pijplijn in gaat en hoe een rode taak te lezen is, `muma-worktree-bootstrap`
  wat een verse worktree nodig heeft voordat er iets draait, en `muma-prod-check` hoe je productie en
  de homelab bereikt en uitleest.
  Ze zijn geschreven uit wat er in de praktijk misging, niet uit hoe het bedoeld was. Daarom staat er
  in elk stuk vooral wat er *niet* aan de hand is: een groene tak die toch niets uitrolt, een
  samenvoeging zonder conflict die de wijzigingenlijst stilzwijgend onder de verkeerde versie zet,
  vier taken die om de infrastructuur heen omvallen en de schuld bij de wijziging leggen, en een
  werkstation vol containers die dezelfde namen dragen als productie. `docs/release-management.md`
  blijft waar het model wordt uitgelegd; deze skills zijn de volgorde waarin het gedaan wordt.
- **`.claude/.gitignore` houdt de sessie-eigen rommel buiten de geschiedenis.** De map `.claude/` was
  tot nu toe helemaal onbekend bij git, en daarin staan naast deze skills ook de worktrees van
  lopende sessies en een `settings.local.json`. Die twee zijn nu uitgesloten, zodat een `git add .claude`
  niet per ongeluk een halve werkkopie meeneemt.

### Changed
- **De app compileert nu tegen Android 36, en dat is wat de androidx-updates deblokkeert.** Zestien
  bibliotheken tegelijk — androidx.activity 1.13 voorop — weigeren gebruikt te worden door iets dat
  tegen 35 compileert. `checkDebugAarMetadata` meldt die zestien in één klap, en dat leest als een
  kapotte build terwijl er één getal te laag staat.

  Alleen `compileSdk` gaat omhoog, `targetSdk` blijft bewust op 35. Die twee doen verschillende
  dingen: compileSdk bepaalt welke API's de code mág aanroepen, targetSdk bepaalt welk gedrag
  Android op het toestel van de gebruiker toepast. Dat laatste verhoog je met een test op een echt
  apparaat, niet als bijvangst van een dependency-bump.

  Het CI-image installeerde alleen android-34 en android-35, dus daar staat 36 nu ook bij. De tag van
  dat image bevat een hash van zijn Dockerfile, dus het wordt vanzelf één keer opnieuw gebouwd; er is
  geen publicatiestap die iemand kan vergeten.
- **numpy mag weer meebewegen, en dat is wat een nieuwere Python mogelijk maakt.** De pin stond op
  `~=2.0.2`, wat alles vanaf 2.1 uitsluit — en precies daar begint de dekking met kant-en-klare
  wheels voor nieuwere Python-versies. Gevolg: elke poging om `docker/Dockerfile.music-manager` van
  3.11 af te halen liet pip terugvallen op het zelf compileren van negentien megabyte C++-broncode,
  in een image dat wel `gcc` heeft maar geen `g++`. De foutmelding wees naar meson en naar een
  ontbrekende compiler, niet naar de pin, en dat is waarom het eruitzag als een probleem met het
  image in plaats van met een versienummer.

  Nu `~=2.4.6`, en nadrukkelijk niet de nieuwste. numpy 2.5 eist zélf Python ≥3.12, dus dat kan
  onmogelijk de versie zijn die je over de Python-bump heen tilt — die moet nog installeerbaar zijn
  op 3.11. De 2.4-reeks is de laatste die cp311 tot en met cp314 bestrijkt en is daarmee de enige
  pin die vóór én na de overstap werkt. Hij blijft ook onder de `numpy<2.6` die numba stelt, en
  librosa 0.10.2 legt zelf geen bovengrens op. Zodra de images van 3.11 af zijn komt 2.5 in beeld
  en mag dit weer verder.

  Daarmee komen de drie Python-versies in de images in zicht: `base` staat al op 3.13 terwijl
  `music-manager` en `tools` op 3.11 hangen, en dat verschil was tot nu toe niet te overbruggen.
- **Het Dependency Dashboard is weg; Renovate maakt gewoon merge requests aan.** Er stonden twee
  remmen op, los van elkaar. Het
  weekvenster `before 6am on monday` zette elke voorgestelde update in een lijst "Awaiting Schedule"
  op het dashboard, en drie regels — Python-majors, Gradle-majors en de basis-images — zetten hun
  updates in "Pending Approval". In beide gevallen gebeurde er niets tot je het aanvinkte. Allebei
  weg: een update die klaar is wordt nu vanzelf een merge request.

  Wat er níet verandert is wat zichzelf mag mergen. Geen van de regels waar de goedkeuring vanaf
  gaat heeft automerge — een major van fastapi, van AGP of van een basis-image opent voortaan uit
  zichzelf, maar blijft daarna gewoon staan tot iemand hem beoordeelt. Een openstaande merge request
  ís die beoordeling; de goedkeuringsstap ervóór was er een tweede keer overheen. Ze krijgen wel een
  label `major` of `docker`, zodat ze in de lijst te onderscheiden zijn van een gewone bump.

  De afkoelperiode van drie dagen blijft onaangeroerd. Dat is de bescherming tegen een pakket dat
  tien minuten geleden gepubliceerd is, en die reden staat helemaal los van hoe ongeduldig je bent.

  Met beide remmen eraf had het dashboard geen functie meer — het bleef een lijst van dingen die
  toch al vanzelf gingen gebeuren — dus die is uitgezet. Issue #1 sluit zichzelf bij de volgende
  draai. Wat je daarmee opgeeft is de plek waar Renovate zijn eigen klachten kwijt kon: dat er geen
  GitHub-token is voor changelogs, en dat `lucide-svelte` als verouderd staat aangemerkt zonder
  opvolger. Die staan nu alleen nog in het joblogboek.

  Omdat Renovate nu elk uur draait en niets meer op een venster wacht, staat `prHourlyLimit` expliciet
  op 2, naast de `prConcurrentLimit` van 5. Dat is géén poort maar een wachtrij: alles komt, alleen
  niet tegelijk. Dat is met opzet, want elke merge request start een pipeline, en veertien tegelijk
  betekent veertien pipelines die vechten om dezelfde database-container in `backend:integration`.

### Fixed
- **Renovate leverde npm-voorstellen af met een lockfile die er niet bij paste.** De eerste
  frontend-MR die de bot uit zichzelf aanmaakte werd meteen rood: `npm ci` weigert te installeren als
  `package.json` en `package-lock.json` uit de pas lopen, en Renovate had alleen de eerste bijgewerkt.

  De oorzaak lag drie stappen verderop en had niets met npm te maken. Het standaard renovate-image is
  een slanke variant zonder taalgereedschap; het haalt de node- en npm-versie die het nodig heeft pas
  tijdens de draai op, en vraagt daarvoor de GitHub-API welke releases er zijn. Zonder token zijn dat
  zestig verzoeken per uur, en met een uurlijkse bot zit je daar zo doorheen. GitHub antwoordde 403,
  containerbase meldde "No tool releases found", en zonder npm kan Renovate geen lockfile
  herbouwen — dus stuurde hij de wijziging maar half af.

  Wat het lastig te herkennen maakt is dat geen enkele foutmelding onderweg iets zegt over GitHub,
  over een limiet of over het image. Je ziet een MR met een halve wijziging en een `npm ci` die
  klaagt over jouw lockfile.

  Nu draait het op de `-full` variant met `binarySource=global`: node en npm zitten al in dat image,
  dus er wordt niets meer opgezocht. Een GitHub-token had het ook opgelost, maar dat vraagt om een
  inlog die dit project verder nergens voor nodig heeft. Het image is groter en staat na de eerste
  keer in de cache van de runner.

  Gecontroleerd met een droge draai: `Updated 1 lock files`. De enige die daarna nog faalt is
  TypeScript 7, en terecht — `typescript-eslint` eist `typescript <6.1.0`, dus die past gewoon nog
  niet.
- **Je backups en je migraties zouden stilletjes gebroken zijn bij de volgende database-upgrade.**
  MariaDB heeft zijn clientprogramma's in 10.5 hernoemd — `mysql` werd `mariadb`, `mysqldump` werd
  `mariadb-dump` — en in versie 12 zijn de oude namen helemaal verdwenen. Op vier plekken riepen we
  nog de oude naam aan. Eén daarvan was een test, en die viel om zodra Renovate mariadb 12 voorstelde;
  zo is het gevonden. De andere drie waren erger, want die worden door niets gedekt: het aanroepen
  van de migraties in `deploy.sh`, het maken van de backup in `backup_db.sh`, en de wachtlus in
  `dev.sh`.

  Wat dat zo vervelend maakt is hoe het faalt. Een ontbrekend programma geeft exit 127 en verder
  niets — geen foutmelding over de database, die draait namelijk prima. Bij de backup betekent het
  een bestand van nul bytes; de controle verderop in dat script vangt dat wel, maar pas nadat de
  backup niet gemaakt is. Bij de wachtlus in `dev.sh` zou hij eeuwig blijven wachten in plaats van
  af te breken.

  In de database-container staat de nieuwe naam er sinds 10.5 altijd, dus daar is het simpelweg de
  nieuwe naam. Op een host of in een service-image hangt het af van welk clientpakket geïnstalleerd
  is, en daar kiest `backup_db.sh` nu zelf: eerst `mariadb-dump`, anders `mysqldump`, en anders een
  duidelijke fout in plaats van een leeg bestand.
- **Een geplande taak sleepte de hele pipeline mee.** De wekelijkse downloader-verversing vraagt om
  één taak en kreeg de complete suite: lint, unit tests, integratietests, de Android-build. Op master
  hoorden `release:tag` en `release:back-merge-develop` daar ook bij, en die hebben dus elke week
  gedraaid — pipeline 1119 van 17 augustus laat ze allebei geslaagd zien. Het kwam niet aan het licht
  omdat er niets van kapot gaat; het kost alleen een uur runnertijd per week en het botst met de
  pipelines die er wél toe doen. Met de renovate-schedule erbij zou dat verdubbelen, en dat is hoe
  het gevonden werd.

  De oorzaak is één zin uit de GitLab-documentatie: in een geplande pipeline is `changes:` altijd
  waar. Elke taak die op een `changes:`-lijst draait matcht daar dus onvoorwaardelijk, en dat zijn er
  vijftien. Er staat nu een `.dedicated_schedule_guard` die als eerste regel in elke taak wordt
  aangehaald, behalve in de twee taken waarvoor een schedule bestaat. Een schedule zet precies één
  variabele, en al het andere gaat opzij.

  Vier tests in `tests/ci/test_gitlab_ci_policy.py` bewaken dat: dat elke taak de guard aanhaalt, dat
  hij vóór elke andere regel staat — regels worden op volgorde beoordeeld, dus een guard achter een
  `changes:`-regel krijgt het woord nooit — dat de twee uitgezonderde taken hem juist níet aanhalen,
  en dat elke schedulevariabele erin voorkomt. Die laatste is de val voor later: een nieuwe schedule
  waarvan de variabele hier ontbreekt krijgt stilzwijgend het oude gedrag terug.

## [0.37.0] - 2026-08-25

### Added
- **De bot die de afhankelijkheden bijwerkt draait nu ook echt.** `renovate.json` ligt sinds 0.24.0
  in de boom en beschrijft precies wat gegroepeerd wordt en wat zichzelf mag mergen, maar er was
  nooit iets dat het uitvoerde: geen enkele merge request, geen dependency dashboard, niets. De
  `renovate/*`-branches in de geschiedenis zijn van 2023 en komen uit Ultrasonic, niet hier. Er
  staat nu een `deps:renovate`-taak die de bot draait tegen deze eigen GitLab, via
  `scripts/ci/renovate.sh`. Zelf gehost, want de gehoste app van Mend bedient alleen gitlab.com; de
  gebruikelijke CI-template van renovate-runner valt om twee redenen af. Die moet op een eigen
  instance bij elke pipeline als externe `include:` van gitlab.com gehaald worden, én de taak die
  hij neerzet draait op een `image:` — en de runner hier is een shell executor, die zo'n taak nooit
  start. Het script draait de container daarom zelf, net als `secret-scan.sh` en `sast.sh` al deden.
  Er wordt niets van de werkmap in gemount: Renovate kloont de repository zelf via de API, en een
  tweede, verouderde kopie ernaast is alleen maar verwarrend. Een draai die niets doet omdat er iets
  misging telt niet als geslaagd — het script leest het logboek na op fatale meldingen, want Renovate
  eindigt met code 0 nadat het een repository heeft overgeslagen, en bij precies één geconfigureerde
  repository is dat niet van succes te onderscheiden.
  Hij loopt alleen vanaf een schedule met `RENOVATE=true`, zodat een gewone push nooit een bot kan
  starten die merge requests opent, en verdwijnt vanzelf als er geen token is ingesteld. De twee
  taken die op *elke* schedule meeliftten — de kwetsbaarhedenscan en de geheimenscan — zijn
  uitgezonderd van die ene, anders draaide de halve pipeline mee voor één bot.
- **Dependabot is bewust niet toegevoegd.** Dat is een product van GitHub en draait niet op een
  eigen GitLab; de poort ernaartoe is een losse dienst die je zelf zou moeten hosten, naast de
  configuratie die er al lag.

### Fixed
- **De Renovate-configuratie was ongeldig, en dat kon niemand weten.** De yt-dlp-regel zette
  `minimumReleaseAge` op `false` om de afkoelperiode van drie dagen te omzeilen, maar dat veld wil
  een tekst: `renovate-config-validator` noemt het een fout en de eerste echte draai zou erop zijn
  afgeknapt. Het staat nu op `"0 days"`, wat hetzelfde betekent en wél geldig is. Dat dit twee weken
  onopgemerkt bleef is precies omdat er nooit een bot draaide om erover te struikelen. In dezelfde
  moeite door is `prPriority` uit `vulnerabilityAlerts` gehaald — dat hoort daar niet en werd
  genegeerd.
- **De beheerpagina was gestyled met kleuren die niet bestonden, waardoor knoppen onleesbaar
  waren.** Dertien van de beheertabbladen gebruikten `spotify-green`, `spotify-gray`,
  `spotify-dark` en `spotify-lightgray`, maar die tokens staan nergens in `app.css` en er is nooit
  een `tailwind.config.js` in deze repo geweest. Tailwind maakte er dus geen enkele regel voor aan.
  Daarbovenop stond er 211 keer een `bg-opacity-*`- of `border-opacity-*`-klasse, en die hele
  familie is in Tailwind v4 vervangen door schuine-streepsyntax. Samen 786 klassen die niets
  deden. Zichtbaar werd dat als knoppen met zwarte tekst op een groene achtergrond die er niet
  kwam — zwart op zwart dus — en als vlakken die `bg-white bg-opacity-10` heetten maar massief wit
  werden, met witte tekst erop. Alles is nu omgezet naar de tokens die de rest van de webinterface
  al gebruikt: `brand` in plaats van een vaste groene tint, `muma-spotify-text` voor secundaire
  tekst en de nieuwe `muma-spotify-panel` (#181818) voor kaarten en panelen. Omdat `brand`
  meebeweegt met de weergavemodus, kleurt de beheerpagina voortaan ook blauw in Sets-modus in
  plaats van altijd groen te blijven.
- **De focusgloed bleef groen in Sets-modus.** De rand om een gefocust element volgde de
  merkkleur al, maar de gloed eromheen stond hard op de groene tint. Die rekent nu met dezelfde
  variabele, zodat rand en gloed in beide modi bij elkaar horen.

### Changed
- **Bijwerken zonder tussenkomst geldt nu ook voor de app en voor de webinterface zelf.** Tot nu toe
  mergede alleen het ontwikkelgereedschap zichzelf. Daar komen de afhankelijkheden van de
  webinterface bij (kleine en herstelversies, gedekt door vitest, typecheck, lint en de browsertest)
  en die van muma-mobile, in twee groepen: het test- en lintgereedschap zonder meer, en de
  bibliotheken waar de app zelf op draait alleen bij kleine en herstelversies. Een grote versie in
  Gradle is AGP, Kotlin of media3 die zijn API verandert; die wachten net als de Python-equivalenten
  op het dashboard.

  Dat testgereedschap staat als een uitgeschreven lijst van dertien coördinaten en niet als een
  match op `testImplementation`, en dat is geen omslachtigheid. De app gebruikt een version catalog,
  en Renovate werkt daar een gedeelde `version.ref` bij in plaats van één coördinaat. `kotlin-test-junit`
  en `kotlin-reflect` hangen aan dezelfde `kotlin`-verwijzing als de compiler, `kotlinx-coroutines-test`
  aan de coroutines waar de app op draait en `mockwebserver` aan okhttp. Wie die vier op hun
  test-klinkende naam in de veilige groep zet, laat een compilerupgrade zichzelf mergen onder het
  mom van een testafhankelijkheid. Ze staan daarom bewust in de runtime-groep.

## [0.36.0] - 2026-08-25

### Added
- **Alles wat het infoscherm van een nummer over dat nummer weet, is nu een ingang tot de
  bibliotheek.** Genre, jaar, label en mood staan er als chips en rijtjes die je kunt aantikken;
  je komt dan in de nummerlijst met dat filter. Het jaar filtert altijd op het jaartal, ook als de
  server een volledige releasedatum kent. Label en mood zijn nieuwe rijen — die stonden er nog
  niet. Een nummer van twee artiesten geeft bij een tik op de artiestenrij een keuzemenu: elke
  artiest apart, plus wat ze samen maakten. Dat laatste is het stuk dat nieuw is in de server:
  `getSongs` accepteert meerdere `artistId`-waarden en levert alleen de nummers waar ze állemaal
  op staan. Bij één artiest verandert er niets, dan blijft het één tik naar de artiestenpagina.
  Op de artiestenpagina zelf zit nu een knop "All tracks", want de albumlijst daar toont alleen
  releases waar de artiest de albumartiest van is — samenwerkingen staan op het album van een
  ander en waren zo niet te vinden. De server telt er meteen bij hoeveel nummers er in totaal aan
  het filter voldoen, en dat getal komt in de schermtitel te staan en achter het "samen"-item in
  het keuzemenu.
- **Een gewijzigde tagger-regel markeert nu zelf de bestanden die eronder vallen.** Wie een artiest
  aan een genre koppelt, een genre wit of zwart zet of een schrijffout omleidt, moest tot nu toe
  kiezen tussen één bestand (`rerun-parse`) en de hele bibliotheek (`/api/tagger/rescan`). Daartussen
  zat niets, terwijl daar het dagelijkse werk zit. Een nieuwe `RescanInvalidator` vertaalt de naam
  in de regel naar bestandspaden en zet die rijen in bulk op `needs_rescan`. Die match is bewust
  breed: hij telt als de artiestnaam exact klopt, óf als de term ergens in de titel of in het pad
  voorkomt, want de regels die een artiest uit een titel afleiden vindt geen enkele join. De rem
  daarop is dat een term korter dan drie tekens alleen op de artiestnaam matcht — een artiest die
  `D` heet zou anders de halve bibliotheek meeslepen — en dat `%` en `_` worden ge-escaped voordat
  ze in de LIKE belanden. Bestanden die de scanner nog nooit gezien heeft staan niet in
  `library_media_files` en worden dus niet gevonden; daarvoor blijft de volledige rescan bestaan.
- **De tagger-tab toont hoeveel bestanden op een retag wachten, en waaróm.** `GET
  /api/tagger/retag/pending` groepeert de wachtrij op reden en `POST /api/tagger/retag/run` start
  hem. Bewust geen automatische retag: een brede match kan meer raken dan bedoeld, en het aantal
  zien vóór je op de knop drukt is precies de rem die dat opvangt. Er is ook geen apart uitvoerpad
  nodig — `Tagger.run()` loopt de mappen af en vraagt per bestand `needs_processing()`, dus de
  gemarkeerde bestanden worden vanzelf opgepakt en de rest overgeslagen. Staat er niets klaar, dan
  verdwijnt het blok. De bestaande knop voor een volledige rescan blijft ernaast staan als botte
  fallback.
- **Artiest-omleidingen zijn eindelijk vanuit de applicatie te bewerken.** `rules_ignored_artists`
  stuurt vier tagger-regels aan (`InferArtistFromTitleRule`, `InferRemixerFromTitleRule`,
  `CheckArtistRule` en `AddMissingArtistToDatabaseRule`) maar had geen enkel endpoint: de tabel werd
  buiten muma om gevuld. Er is nu `GET`, `POST` en `DELETE` op `/api/rules/artist-redirects`. Staat
  er een `corrected_name`, dan wordt de naam hernoemd; staat die leeg, dan geldt de naam als "geen
  echte artiest". Geïnvalideerd wordt op de óude schrijfwijze, want dat is wat er vandaag in de
  bestanden staat — de gecorrigeerde naam draagt nog niemand.
- **BPM is aan te zetten vanaf de configuratiepagina.** `analyze_bpm` stond als module-constante op
  `False` in `BaseSong.py` en was dus alleen met een codewijziging aan te zetten; het is nu een
  gewoon `ConfigField` in de groep Tagger. Let op de kosten die in de beschrijving staan: ook mét de
  overslaan-regel hieronder decodeert de eerste ronde élk bestand één keer, dus dit tegelijk
  aanzetten met een volledige rescan is een slecht idee.
- **LMS krijgt bericht na een scanner-run en na het taggen van één bestand.** `LmsScanTrigger` stond
  al in git maar werd alleen door de tagger-lus aangeroepen. De trigger staat in beide gevallen
  buiten de lock, zodat een trage of onbereikbare LMS niets ophoudt. De bijbehorende sleutels
  `lms_hosts` en `lms_subsonic_api_key` bestonden alleen in de code die ze uitlas en niet als
  instelling; ze staan nu in de groep LMS op de configuratiepagina, met de API-sleutel als geheim.
- **De webspeler heeft nu een equalizer, net als de Android-app.** Tien banden van 31 Hz tot
  16 kHz, een voorversterking en zeven voorinstellingen (Vlak, Rock, Pop, Jazz, Klassiek, Bass
  boost, Zang); zodra je zelf een schuif aanraakt springt de keuze naar "Eigen". De instelling
  hangt aan de browser, niet aan het account — het is een correctie voor jouw speakers of
  koptelefoon, en die verschilt per apparaat. Twee dingen aan de Web Audio API bepaalden het
  ontwerp. Een `AudioContext` mag pas na een klik van de gebruiker beginnen, dus de audioketen
  wordt pas opgebouwd op het moment dat je de equalizer voor het eerst aanzet; wie het paneel
  nooit opent betaalt er niets voor. En `createMediaElementSource()` is onomkeerbaar: is hij
  eenmaal gedraaid, dan loopt alle audio van dat element de rest van de pagina door de keten.
  Uitzetten breekt de keten daarom niet af maar zet alle tien de banden op 0 dB, wat wiskundig
  hetzelfde is als niets doen — afbreken en opnieuw opbouwen zou het risico geven dat de speler
  stil blijft. Kan de keten niet gebouwd worden, of kent de browser geen `AudioContext`, dan
  verdwijnt de knop en speelt de speler precies zoals hij altijd deed. Een opgeslagen curve die
  niet helemaal klopt valt terug op vlak: een half geldige curve laat je met een geluid zitten
  dat je niet kunt verklaren en niet gekozen hebt.

### Changed
- **Beheer heeft geen platte lijst van eenentwintig tabbladen meer, maar acht ingangen.** Collectie,
  Curatie, Kanalen, Toegang, Systeem en Instellingen klappen open; Overzicht en Downloaders staan
  los, want een groep van één voegt alleen een klik toe. De tabbladen zelf en hun `/management/...`
  adressen zijn niet veranderd, dus bestaande links blijven werken, en welke groep openstond
  onthoudt je browser. Twee tabbladen zijn weg: Over stond ook al bij je persoonlijke instellingen,
  en Versies liet één versienummer zien dat het als zes verschillende presenteerde — `/api/versions`
  vroeg nooit iets aan een worker, dus dat "offline" dat het rood kon kleuren kon domweg niet
  voorkomen. Het echte versienummer staat op Overzicht.
- **Beheer op de telefoon opent op een index in plaats van op een rij tabbladen.** Dezelfde acht
  ingangen als op het web, in dezelfde volgorde: Collectie, Curatie, Kanalen, Toegang, Systeem en
  Instellingen als kopjes, met Overzicht en Downloaders er los tussen. De app had drie van de
  negentien pagina's en toonde die als drie tabbladen; negentien tabbladen naast elkaar leest
  niemand. Alle negentien staan nu in de lijst, ook de zestien die de app nog niet bouwt -- die zijn
  grijs met de regel dat ze voorlopig alleen op het web staan, zodat de index eerlijk laat zien wat
  Beheer bevat en een volgende ronde een regel aanzet in plaats van er een bij te zetten.
  Downloaders, Gebruikers en Toegangsverzoeken werken precies zoals eerst, alleen nu als eigen
  scherm met een terugknop erboven. De groepering is letterlijk overgenomen uit `MANAGEMENT_GROUPS`
  in de webui, en een test in de app leest dat bestand en vergelijkt het regel voor regel, zodat de
  twee lijsten niet uit elkaar kunnen lopen.

### Fixed
- **De tagger draaide dagenlang door met de regels die hij bij het opstarten had ingelezen.**
  `Cache.py` bouwt zijn helpers één keer bij import en `run_tagger_loop` blijft leven, dus een regel
  die je vandaag aanpaste werkte pas na de volgende herstart van de container. Dat zou de hele
  retag-invalidatie hierboven laten liegen: de bestanden worden netjes gemarkeerd, de tagger pakt ze
  op, en tagt ze opnieuw met de oude regels — het resultaat is identiek aan wat er stond en het
  lijkt alsof het markeren stuk is. `Tagger.run()` ververst nu als eerste handeling elke regelcache,
  zoals `ScannerManager.run_full` dat al deed voor de genre-regels. Daarvoor moesten `TableHelper`
  en `FilterTableHelper` allebei nog een `reload()` krijgen; alleen `LookupTableHelper` had er al
  een.
- **De BPM-regel heeft waarschijnlijk nooit gewerkt.** librosa geeft sinds 0.10.1 een ndarray van
  één element terug in plaats van een float, en `round()` daarop gooit `TypeError` — die werd stil
  opgeslikt, dus er werd geen BPM opgeslagen en er kwam geen regel in het log tenzij `debug` aan
  stond. De bestaande tests mockten een kale float en merkten er niets van. De conversie gaat nu via
  `item()` en dekt beide versies. Daarnaast slaat de regel een bestand over dat al een BPM draagt:
  BPM verandert niet meer als hij eenmaal bekend is, en het decoderen van audio is verreweg het
  duurste wat de tagger doet — zonder die grens zou elke retag een volledige heranalyse van de
  bibliotheek worden.

## [0.35.0] - 2026-08-25

### Added
- **De webui bladert nu ook op festival, jaar en lineup, net als de Android-app.** Drie pagina's
  onder Bibliotheek, met dezelfde kaartenrasters als Genres en Labels. De server kende de lijsten
  al (`getTags` voor FESTIVAL en YEAR, `getLineups` voor de lineups); wat ontbrak was dat
  `getSpotifyTracks` — het endpoint waar de hele webui zijn nummerlijsten uit haalt — niet op
  festival of lineup kon filteren. Dat kan het nu. Let op wat een lineup is: een tekstbestand met
  artiestennamen onder `/music/metadata/festival-lineups`, en de match gaat op de héle
  artiestennaam. `Angerfist` vindt dus niet wat op naam van `Angerfist & Outsiders` staat. Op prod
  staat nog geen enkel lineup-bestand, dus die pagina begint leeg.
- **Een lege Festivals- of Jaren-pagina zegt nu waaróm hij leeg is.** `getTags` kan niet uit elkaar
  houden of er niets getagd is of dat de tag nooit geïndexeerd werd, en dat laatste hield destijds
  de Podcasts-pagina leeg. Een beheerder krijgt nu te lezen dat de tag bij de extra tags van de
  scanner moet staan; wie geen beheerder is krijgt gewoon "nog niets", want het antwoord van de
  server bevat die instelling voor hen niet eens.

## [0.34.0] - 2026-08-24

### Fixed
- **Eén festival kon twee kaartjes opleveren, omdat dezelfde tag in twee schrijfwijzen op het
  bestand stond.** In m4a schrijft `_set_m4a_tag` de naam in hoofdletters
  (`----:com.apple.iTunes:FESTIVAL`), terwijl de EasyMP4-registraties naar het kleine-letters-atom
  wijzen en een oudere ronde `Festival` met een hoofdletter F achterliet. muma merkte er niets van:
  `TagCollection._parse_m4a` maakt de sleutel klein en leest ze allemaal. LMS niet — die leest beide
  atomen en maakt er twee clusters van. In een steekproef van 400 bestanden droegen 13 van de 116
  getagde bestanden het afwijkende atom. Vervelender: een nieuwe waarde ging alleen naar het
  hoofdletter-atom, dus het andere bleef met de oude tekst staan. De tagger vouwt nu bij elke ronde
  elk eigen atom naar de schrijfwijze die hij zelf gebruikt — niet alleen FESTIVAL, ook PARSED,
  PUBLISHER en RATING — en doet dat ook als er verder niets aan het bestand verandert, want anders
  bleef een oud atom eeuwig staan. Staat het canonieke atom er al, dan wint dat: daar staat de
  waarde die de regels zojuist opleverden. mp3 blijft `TXXX:festival` en wordt niet aangeraakt, want
  die naam kent LMS al.

### Added
- **Nummers kennen nu hun eigen versies, en er is er één die telt.** Eén nummer stond tot tien
  keer in de bibliotheek — een SoundCloud-rip, een YouTube-rip, de officiële radio edit, de
  extended mix, en dat alles nog eens als FLAC en als MP3 — en niets in het systeem wist dat dat
  hetzelfde nummer was. `library_works` komt boven `library_tracks` te staan, dat al de versielaag
  was, en een achtergrondlus hangt elke track onder het nummer waar hij bij hoort. Welke versie
  telt wordt bepaald door tiers die op volgorde beslissen: eerst herkomst (een officiële release
  met een label verslaat altijd een rip), dan de soort (radio, edit, original, geen markering,
  extended, instrumentaal), dan het formaat. Dat vervangt de opgetelde score van de oude
  deduplicatie, waarin een rip van 320kbps won van een officiële radio edit van 192kbps omdat
  formaat zwaarder woog dan versie. Een remix blijft een eigen nummer: de groepering strippen
  alleen haakjes waarvan élk woord een bekende versie-aanduiding is, dus "(Radio Edit)" verdwijnt
  en "(Wildstylez Edit)" blijft staan. Twee handmatige correcties zitten erbij, want de regels
  hebben het niet altijd bij het rechte eind: een versie vastpinnen, en een track die verkeerd is
  samengevoegd uit zijn groep trekken. Beide overleven een rescan. Er verandert nog niets aan wat
  je ziet of hoort — dit is het model en het bewijs dat het klopt; de speler en de webinterface
  gaan er in een volgende stap op leunen.
- **De instellingen van MuMa zijn nu vanuit de webui te bewerken.** Beheer heeft een tabblad
  Configuratie dat het schema rendert dat de backend zelf beschrijft: elk veld met zijn groep,
  type, uitleg en huidige waarde. Een instelling die in `config_store.py` bijkomt verschijnt er
  vanzelf, zonder frontend-wijziging. Opslaan stuurt alleen wat je echt veranderd hebt.
- **Hoeveel bestanden één 'nu toepassen' mag hertaggen is een instelling geworden.** Stond vast op
  2000 in de code. De juiste grens hangt af van je collectie en van hoe lang je de gewone
  tagger-ronde wil laten wachten, want zo'n batch houdt het tagger-slot vast. Nu `max_retag_files`
  onder Tagger, en de waarde wordt per verzoek gelezen, dus een wijziging geldt bij de volgende
  retag in plaats van na een herstart.
- **Het databasewachtwoord lekte via de config-API.** `GET /api/config` hing alleen aan "een
  geldige sleutel", niet aan een recht, dus elke ingelogde gebruiker kon alle instellingen
  opvragen — inclusief `db_pass`, de Telegram-hash en de Spotify-, Discogs- en Last.fm-tokens, in
  platte tekst. De drie config-endpoints hangen nu aan het nieuwe recht `config.manage`, en
  credentials verlaten het proces sowieso niet meer: ze komen gemaskeerd terug en het masker
  terugsturen laat de opgeslagen waarde ongemoeid. Binnen het proces blijft de echte waarde
  gewoon leesbaar, want de databaseverbinding heeft hem nodig.
- **De ntfy-velden op het events-tabblad waren altijd leeg.** `/api/config` antwoordt met
  `{config, groups}` maar de webui las dat als een platte map, dus `config.notify_url` bestond
  niet. Rechtgezet bij het ophalen.

## [0.33.0] - 2026-08-24

### Added
- **Een set die twee evenementen noemt krijgt nu beide namen, en er zijn 29 festivals bij.**
  De regel hield alleen de langste alias over, dus van "Reverze 2024 - Reverze Flashback" bleef er
  één naam staan en verdween de andere. Een set kan bij twee evenementen horen — een
  Flashback-set gedraaid op Reverze — en dat hoort net zo op het bestand als twee genres. De
  helper geeft nu elke herkende naam terug en laat alleen een treffer vallen die ín een langere
  treffer valt: "Intents Karnaval Festival" blijft één evenement, want de gecombineerde spelling
  staat als alias in de tabel. De namen gaan gesorteerd het bestand in, zodat een tweede ronde
  niets herschrijft, en de datum komt van de meest specifieke match die een editie kent.
  `migrate_v14_festivals_extra.sql` vult de tabel aan met evenementen waarvan wel sets in de
  bibliotheek staan maar die in geen enkele spelling bekend waren — onder meer Loudness,
  I AM HARDSTYLE, de losse Gearbox-events, Revealed Night, Creamfields, EDC Las Vegas,
  Ultra Music Festival en Vroeger Was Alles Beter — en geeft Flashback Festival de korte
  spelling die in bestandsnamen voorkomt. Kaal blijven `Gearbox` (2.066 labeluploads tegen 94
  sets), `Bass Events`, `Hardstyle Top 100` en `Wildstylez` erbuiten: dat zijn hier een label,
  een kanaal, een chart en een artiest. Omdat de regel alleen bestanden van tien minuten en
  langer labelt, raken namen die ook een tracktitel zijn geen losse nummers.
- **Shownaam en schrijfwijzen zijn te bewerken op de podcast-curatiepagina.** `tools/detect_podcasts.py`
  stelt het stuk bestandsnaam voor waarop het gegroepeerd heeft, en dat stuk belandde één op één in
  de `PODCAST`-tag van elke aflevering: een show die plat in `Soundcloud/Scantraxx/` ligt kwam binnen
  als "KELTEK Presents ｜ Pure Hardstyle ｜" in plaats van als "Pure Hardstyle". Goedkeuren was tot nu
  toe de enige knop, dus die naam was niet te herstellen. De curatiepagina heeft nu een bewerkscherm
  met de naam en de lijst schrijfwijzen erin, achter `POST /api/rules/podcasts/{id}/rename`,
  `POST .../aliases` en `DELETE .../aliases`. Dat repareert ook de dekking: de detector ziet alleen
  bestanden met een afleveringsmarkering, terwijl de tagger op elke schrijfwijze in titel én pad
  matcht. Voor Pure Hardstyle scheelt dat 11 van de 15 afleveringen tegenover alle 15. Een naam of
  schrijfwijze moet minstens vier letters of cijfers overhouden na normalisatie — korter is een
  substring die willekeurige bestanden raakt — en de oude naam blijft automatisch als schrijfwijze
  staan, omdat `PodcastHelper` de naam zelf als match gebruikt.

### Fixed
- **Een podcastbeslissing bereikte de draaiende tagger pas na een herstart.** `Cache.databaseHelpers`
  laadt `PodcastHelper` één keer bij het importeren, en het beslis-endpoint verversde die niet — zoals
  de artiest- en labelregels dat al wel deden. Een zojuist goedgekeurde show tagde daardoor niets.
- **Samenvoegen verloor de naam van de rij die verdween.** Alleen de aliasrijen verhuisden mee. Zolang
  de naam ook als alias in de tabel stond viel dat niet op, maar na een hernoeming staat hij daar niet
  meer en stopte elk bestand met die schrijfwijze met matchen. De naam wordt nu als schrijfwijze van
  de doelshow bewaard.

## [0.32.1] - 2026-08-24

### Fixed
- **Livesets kregen het evenement als artiest en de artiesten als titel.** `Thunderdome 2025 ｜
  Akimbo vs. Barber` stond in de bibliotheek als artiest "Thunderdome 2025" met titel "Akimbo vs.
  Barber", precies omgekeerd. De oorzaak zat in de laatste gok van `InferArtistFromTitleRule`:
  wanneer geen enkele regel een bekende artiest herkende, nam die blind het eerste segment als
  artiest. Bij een verse bibliotheek — waar Akimbo en Barber nog niet bestonden — leverde dat
  "Thunderdome 2025" op. Die naam belandde vervolgens zelf in `library_artists`, waarna de
  single-dash-regel hem exact matchte en de fout bij elke volgende scan bevestigde in plaats van
  herstelde: ook nadat Akimbo en Barber wél bekend waren, bleef de editie winnen. Een segment dat
  op een jaartal eindigt, of dat de festivaltabel herkent, telt nu nergens meer als artiest — niet
  in de fallback, niet in de single-dash-regel en niet in de multi-dash-regel. In plaats daarvan
  leest een nieuwe regel `<evenement> | <artiesten>` zoals het bedoeld is: de editie wordt de
  titel, de andere kant de artiest. Die kant moet er wel als een artiest uitzien — een bekende
  naam, een fuzzy match, of twee namen met een `vs`/`&` ertussen — zodat een podium of thema
  ("Mainstage", "Tunnel Of Terror") geen nieuwe artiest wordt. Bestaande bestanden herstellen
  vanzelf: de onaangetaste titel staat nog in `original_title`, waar de regels op werken.

## [0.32.0] - 2026-08-24

### Fixed
- **De artiestafbeeldingen-crawl liep bij elke herstart opnieuw langs elke hopeloze naam, en
  bleef daarbij hangen op MusicBrainz.** Twee fouten die elkaar versterkten. De timeout stond op
  `(5, 20)`: ruim voor het lezen, krap voor het verbinden. Gemeten tegen musicbrainz.org op
  24-08-2026 landde élke mislukking op precies 5,0 seconden — de connect-helft — en urllib3 meldt
  dat als `Read timed out. (read timeout=5)`, waarin het woord "read" naar de verkeerde helft
  wijst. Onder belasting doet die host er seconden over om de verbinding te accepteren en
  antwoordt hij daarna in ongeveer zeven; met `(15, 30)` slaagt dezelfde zoekopdracht waar hij
  eerst na twee pogingen en 10 tot 25 seconden opgaf. Daarbovenop selecteerde de crawl bij elke
  boot élke artiest zonder afbeelding, inclusief alle eerder mislukte. Deze bibliotheek bestaat
  voor een groot deel uit festivalrips en bootleg-aliassen die geen enkele provider kent, en die
  namen worden er tussentijds niet vindbaarder op — het opnieuw proberen kostte alleen een derde
  partij seconden per artiest, eindeloos. Een mislukte poging heeft nu een wachttijd van 30 dagen,
  in te stellen met `ARTIST_IMAGE_RETRY_AFTER_DAYS`.
- **`setArtist()` en `setArtistName()` keken in `find_advanced` naar twee verschillende
  koppelingen.** Beide kregen hun eigen `track_artist_link`-join, dus "deze id" en "deze naam"
  mochten twee verschillende artiesten op twee verschillende rijen zijn — een track die de ene
  artiest als id had en een ándere als naam kwam er doorheen. Ze delen nu één link-rij, wat de
  betekenis is die het paar altijd al had.
- **Een diepe ronde die halverwege stopte rekende tracks aan die hij nooit geprobeerd had.** Werd de
  bron geparkeerd of het proces gestopt, dan schreef de afhandeling de hele resterende batch weg als
  mislukte poging. Op 23-08-2026 stonden zo 94 tracks onterecht op een poging, waarvan 79 bij twee
  accounts — het patroon van een afgebroken ronde, niet van mislukte downloads. Na drie van die
  afbrekingen zou zo'n track dertig dagen zijn uitgesloten, precies de tracks waarvoor de diepe ronde
  bestaat. Alleen wat de ronde echt geprobeerd heeft telt nu mee.
- **De hoezen op een Memories-tegel waren weg zodra labelreleases vooraan kwamen.** Dat is precies
  andersom dan je zou denken: een SoundCloud-rip draagt bijna altijd een ingesloten plaatje, een
  echte labelrelease in deze bibliotheek meestal niet. Toen de tegels de labelreleases vooraan
  gingen zetten, keek de mozaïek dus naar juist die nummers en vond niets — vier van de zes jaren
  toonden een grijs vlak. De server stuurt nu per jaar maximaal vier hoezen mee, verzameld uit het
  hele jaar in plaats van uit de handvol nummers op de tegel, zodat een jaar met onbehoesde
  topnummers alsnog een mozaïek krijgt.
- **Zeven kanalen waren stilletjes samengevoegd met een ander kanaal.** `channels.normalized_name`
  stond op `utf8mb4_general_ci`, en die collatie geeft élk teken buiten de Basic Multilingual Plane
  hetzelfde sorteergewicht. Twee namen die volledig uit zulke tekens bestaan zijn voor de database
  dus identiek zodra ze even lang zijn — en juist SoundCloud-accounts met stijl-unicode zijn dat.
  `𝙁𝙍𝘼𝙉𝙏𝙄𝘾` (7 tekens) gold als gelijk aan `𝗕𝗔𝗗𝗞𝗜𝗖𝗞` (7), `𝙎𝙋𝘼𝙍𝙆𝙕` (6) aan `𝐊𝐈𝐑𝐄𝐀𝐋` (6). De unieke
  sleutel hield de eerste, `INSERT IGNORE` slikte de rest zonder foutmelding, en de tracks van de
  verliezer werden aan het winnende kanaal gehangen. Niets crashte; de telling was zeven te laag.
  De kolom is nu `utf8mb4_bin`, wat hier ook inhoudelijk klopt: de waarde wordt al in Python
  gelowercased, dus vergelijken op bytes is precies de vraag die gesteld wordt. Draai
  `migrate_v13_channels_binary_collation.sql`, daarna `scripts/backfill_channels.py` en
  `scripts/prune_channel_links.py` om de verkeerde koppelingen op te ruimen.
- **De channel-backfill haalde het einde niet.** Hij deed drie queries per bestand, wat voor deze
  bibliotheek neerkomt op bijna een miljoen losse round-trips; de server verbrak de verbinding
  halverwege met `Lost connection to MySQL server during query`. Elk kanaal wordt nu één keer
  opgezocht in plaats van één keer per bestand, en de koppelingen gaan er per batch in met
  `executemany`.

### Added
- **De tagger loopt de bibliotheek nu vanzelf opnieuw langs, in plakjes.** Elke ronde sloeg elk
  bestand over waarvan de mtime al bekend was, en dat is precies waarom een nieuwe regel of een
  nieuw festival in `rules_festivals` nooit een bestand bereikte dat er al langs was geweest: die
  bestanden werden simpelweg niet meer gelezen. Alleen een handmatige `POST /api/management/tagger/rescan`
  of een script als `tools/retag_festivals.py` haalde ze terug — en dat gebeurde dus zelden. De
  tagger geeft nu vóór elke ronde het oudste plakje van `tagger_processed_files` aan zichzelf
  terug, waardoor de hele bibliotheek ongeveer eens per `tagger_deep_run_days` (standaard 30, `0`
  zet het uit) langs de huidige regels komt. Gespreid en niet één maandelijkse veeg, omdat de
  tagger één lock heeft: een volledige ronde ineens laat verse downloads uren wachten, een plakje
  kost seconden. `tagger_deep_run_batch` (standaard 200) begrenst dat plakje. De query begrenst
  zichzelf ook: alleen rijen ouder dan het venster komen in aanmerking, dus zodra de bibliotheek
  rond is levert hij niets meer op tot rijen weer verouderen. Opnieuw lezen is goedkoop — een
  regel die dezelfde waarde oplevert schrijft niets, dus een plakje zonder nieuws raakt geen enkel
  bestand aan en geeft LMS niets te herindexeren.
- **`getSongs` filtert nu op een set artiesten en vertelt hoeveel er in totaal zijn.** De parameter
  `artistId` mag meerdere keren mee; een track komt alleen door als hij aan élke genoemde artiest
  hangt — "wat hebben deze mensen samen gemaakt", niet "een van hen". Dezelfde id twee keer noemen
  telt één keer: de ids gaan als set de query in, want anders zou een self-join alsnog "deze ene
  artiest" betekenen. De `songs`-node draagt daarnaast `totalCount`: hoeveel tracks het filter
  oplevert, niet hoeveel er op deze pagina staan, zodat een client kan pagineren zonder tot het
  einde door te bladeren.
- **De song-node draagt nu de labels.** Gelezen uit de PUBLISHER-cluster en niet uit de
  `label`-tabel: labels hangen in het datamodel aan de release, en de cluster is precies waar de
  filterkant op matcht. Browsen op label maakte die keuze al.
- **muma-mobile leest artiesten, moods en labels van de song-respons.** Alle drie met een lege
  lijst als default, zodat een server die ze niet meestuurt gewoon blijft werken.
- **`scripts/prune_channel_links.py`** verwijdert koppelingen tussen track en kanaal die door geen
  enkel bestandspad worden ondersteund — restanten van een verplaatst bestand of een samengevoegd
  kanaal. Verwijdert per exact paar en nooit de hele tabel: er staan zo'n 148.000 juiste rijen in,
  en die opnieuw opbouwen is een veel grotere operatie dan de reparatie zelf. Heeft een
  `--dry-run`.

## [0.31.0] - 2026-08-23

### Changed
- **Memories zet nu labelreleases vooraan als er niets te sorteren valt.** De volgorde binnen een
  jaar keek naar sterren en luisterbeurten, en juist die twee zeggen bij memories bijna nooit iets:
  op 23-08-2026 had geen van de 3.600 nummers in het venster een rating of een luisterbeurt, want
  memories vragen een releasedatum op dagniveau en die hebben vooral de rips. Zonder die signalen
  besliste de datum, en dat leverde tegels vol SoundCloud-materiaal op. Er is nu een derde sleutel:
  hoe bewust de release is, afgelezen aan het label. De scanner slaat de publisher-tag als label op
  en de downloaders zetten het platform in diezelfde tag, dus "welk label" is tegelijk "waar komt
  dit vandaan". Van hoog naar laag: een echt label, geen label (vaak een release waarvan de
  publisher nooit gematcht is), `__Free&None`, `Soundcloud`, `Youtube`, `Telegram`, `__TODO` — de
  importstapel, geen release. Onderstrepingen en hoofdletters doen niet mee, en een release met
  meerdere labels pakt de hoogste. Deze sleutel staat bewust ónder de luisterbeurten: hij vult een
  jaar in waar niemand iets mee gedaan heeft, en begraaft geen nummer dat je wél draait.

## [0.30.0] - 2026-08-23

### Changed
- **Het autoscherm van muma-mobile draait nu om de microfoon.** Bovenin vier snelkoppelingen, in het
  midden een gevulde microfoonknop, onderin compact wat er speelt: hoes, titel, bediening en de
  sterren. De snelkoppelingen werden afgesneden omdat ze als enige blok om restruimte vochten met de
  hoes, de bediening en de sterren; ze staan nu allebei op `wrap_content` en kunnen elkaar geen
  hoogte meer afnemen. De balk onderin waren er twee — de tabbladen en het kleine spelertje — en
  allebei blijven ze weg zolang de autostand aan staat.
- **Het spraakscherm luistert zodra het opengaat.** Alles wat op dat scherm uitkomt is al een besluit
  om iets te zeggen, dus de tik erna bewees dat alleen nog een tweede keer. De knop eronder is nu een
  herhaling, en blijft wel wat de eerste keer om de microfoonrechten vraagt. Na het starten van de
  muziek gaat het scherm na tien seconden terug; elke aanraking annuleert dat definitief.

### Added
- **Het spraakscherm vertelt wat het begreep, in woorden.** `genre Hardstyle`, `jaar 2021`, regel
  voor regel, met het volledige verslag één tik verderop. Waar eerst het filterobject stond dat naar
  de server gaat: `Playing [{"name":"GENRE","value":"hardstyle"}]`. De regels komen uit
  `VoiceExplanation` in `core:voice`, zodat ze een veld dragen in plaats van een label en vertaalbaar
  blijven.
- **Artiesten, labels en genres zijn nu te bewerken vanuit de webui.** Het uitgangspunt van MuMa
  blijft dat je zo min mogelijk zelf edit, maar twee dingen kan geen bestand dragen: een koppeling
  (een MBID, een alias) en een regel. Daar staat nu een potloodknop voor naast de titel op de
  artiest-, label- en genrepagina, zichtbaar voor wie het nieuwe recht `rules.manage` heeft. Bij een
  artiest stel je de MBID en externe ids in, beheer je aliassen en leg je artiest→genre-regels vast;
  bij een label daarnaast het moederlabel en de catalogus-prefixen; bij een genre waar het onder
  valt, zodat `Industrial Hardcore` meetelt als je `Hardcore` zoekt. Curatie en bewerken zijn
  bewust twee dingen: de curatie beslist óf een genre bestaat, deze pagina bewerkt er een die al is
  goedgekeurd — een afgekeurd genre krijgt dus geen potlood. Elke regel laat zien hoeveel tracks hij
  raakt, met een aparte knop die precies die bestanden opnieuw laat taggen; opslaan en toepassen
  zijn los, want het eerste is goedkoop en het tweede niet.
- **Een nieuwe regel werkt nu meteen, in plaats van pas na een herstart.** `Cache.databaseHelpers`
  laadt elke regeltabel één keer in bij het opstarten van het proces, dus een regel die je via de
  API toevoegde was onzichtbaar voor de draaiende tagger tot hij opnieuw startte — de rij stond
  keurig in de database en er gebeurde niets. Dat gold ook voor de bestaande knoppen onder
  Beheer → Tagger. Het proces dat de regel schrijft ververst zijn eigen cache nu direct, en elke
  andere tagger (importer, downloader) loopt binnen een minuut bij.
### Fixed
- **Een deploy nam de downloaders midden in hun ronde mee, en wat ze net geleerd hadden ging
  verloren.** Python beëindigt bij een onafgehandelde SIGTERM het proces meteen, dus geen enkele
  `finally` kwam nog aan de beurt: afschrijvingen en faal-tellingen van de lopende ronde werden niet
  weggeschreven, en een download die in de nabewerking werd afgekapt kon een ongetagd bestand
  achterlaten dat bij elke volgende ronde overgeslagen werd zonder ooit gearchiveerd te raken. De
  workers vangen SIGTERM nu af. Docker geeft tien seconden, veel te weinig om een download af te
  maken, dus breekt een yt-dlp progress hook de lopende download binnen een seconde af; daarna loopt
  de gewone afhandeling af en staat de boekhouding op schijf. Die ene track wordt de volgende ronde
  gewoon opnieuw opgehaald.

## [0.29.0] - 2026-08-23

### Added
- **Eén script dat de verhuizing op productie helemaal doet.**
  `scripts/prod-restructure-music.sh --dry-run` en daarna `--apply`, als root op de prod-host.
  Het zoekt de stack zelf op — de databasecontainer aan zijn image, de te stoppen containers aan
  wie er echt `/mnt/music` gemonteerd heeft, en de `.env` via de compose-labels — stopt die
  containers, hernoemt, herschrijft de opgeslagen paden mét hun hash, past de vier padinstellingen
  aan en start precies terug wat het gestopt heeft, via een `EXIT`-trap zodat de stack ook omhoog
  komt als een stap faalt. Vooraf controleert het of MariaDB's `SHA2()` dezelfde hashes oplevert als
  wat Python ooit heeft weggeschreven; zo niet, dan weigert het — anders zou de kolom vollopen met
  waarden die de scanner niet herkent en zou élk bestand er nieuw uitzien. `--revert --dry-run`
  laat zien wat terugdraaien zou doen. Achteraf nog twee dingen zelf doen: een volledige LMS-rescan,
  en de CI-variabele `PROD_ENV_FILE` bijwerken — prod's `.env` wordt bij elke deploy daaruit
  overschreven.

### Changed
- **Het aantal op een Memories-tegel klopt nu, en de top-3 ook.** Er stond "200 tracks" op elke
  drukke tegel, want dat was de limiet waarmee de webpagina het jaar ophaalde, niet de grootte van
  het jaar: 2025 heeft er in werkelijkheid 450, 2024 er 407, en zeven van de negentien jaren zitten
  boven die limiet. Dezelfde limiet maakte de top-3 een gok, omdat hij koos uit de eerste 200 die de
  query toevallig teruggaf. De server sorteert een jaar nu zelf op wat je ermee hebt — vijf sterren
  eerst, daarna het aantal beluisteringen — vóórdat hij afkapt, en meldt het echte jaartotaal
  ernaast. Daardoor kan het overzicht met twaalf nummers per jaar toe in plaats van tweehonderd:
  de pagina haalt nog een paar honderd kilobyte op in plaats van 2,4 megabyte, en toont toch de
  juiste drie en het juiste aantal. Een jaarpagina vraagt met `year=` alleen dat ene jaar op en
  krijgt het compleet; de afspeelknop op een tegel doet hetzelfde, zodat die het hele jaar in de
  wachtrij zet en niet de handvol nummers die op de tegel pasten.

## [0.28.0] - 2026-08-23

### Added
- **De mapindeling van de bibliotheek, klaar om uit te voeren.** `EPs` bevatte drie verschillende
  dingen door elkaar: releases mét label, releases zónder label (`__Free&None`) en de importstapel
  (`__TODO`). Alleen het eerste is een labelboom, en dat is precies waarom de andere twee steeds in
  je labellijst opdoken. `scripts/restructure_music_folders.py` splitst ze uit elkaar naar
  `labels/`, `songs/`, `import/` en `channels/<platform>/`. Het zijn vijf mapnamen, geen 326.480
  bestandsverplaatsingen — alles blijft binnen dezelfde mount, dus het is een metadata-operatie en
  `--revert` draait het net zo goedkoop terug. Het script weigert het hele plan zodra één stap niet
  kan; half verhuisd is het slechte geval. Draai eerst `--dry-run`. Let op: het is nog **niet**
  uitgevoerd, en dat kan ook niet vanaf een ontwikkelmachine alleen — de padinstellingen bereiken de
  workers via de `.env` op productie, niet via de API-config. De volgorde staat in
  [docs/designs/wrapped/technical.md](docs/designs/wrapped/technical.md), deel 3.
- **SoundCloud is geen platenlabel meer.** `Soundcloud` (132.037 tracks), `Youtube` (30.779) en
  `Telegram` (1.556) stonden bovenaan je labellijst, ver boven het eerste echte label (Dirty Workz,
  2.299). Dat kwam doordat de tagger het platform in de publisher-tag zet en de scanner een
  publisher als label opslaat. `__TODO` en `__Free&none` stonden er om dezelfde reden in: de eerste
  is de naam van de importmap zelf, de tweede is de stapel muziek die juist géén label heeft. Geen
  van de vijf is een label. Er is nu een `channels`-tabel: een account op een platform, waar een
  bestand doorheen binnenkwam. Platforms blijven gesplitst — het SoundCloud- en het YouTube-kanaal
  van hetzelfde label zijn twee rijen — en ze komen samen via het label of de artiest waar een
  kanaal naar wijst. Beide koppelingen mogen tegelijk gevuld zijn, want een artiest met een eigen
  imprint is geen uitzondering, en beide mogen leeg blijven: dat een kanaal bestaat legt een scan
  vast, wát het is bepaal jij. De classificatie komt uit het pad en niet uit de tag, dus alle
  160.000 bestanden kloppen zonder er één opnieuw te taggen. Bestaande rijen zet je om met
  `scripts/backfill_channels.py` — draai hem eerst met `--dry-run`. Er wordt geen bestand
  verplaatst of hernoemd.
- **Een listen weet nu hoe lang je écht geluisterd hebt, en waar.** Tot nu toe legde MuMa alleen
  vast dát er iets gespeeld was. Hoe lang wist de speler wel, maar dat getal werd weggegooid voordat
  het verstuurd werd, en elke listen claimde dezelfde herkomst (`lms`) of je nu op de webspeler, je
  telefoon of in de auto zat. Voor deze collectie is dat geen detail: de gemiddelde track duurt 939
  seconden omdat het grotendeels DJ-sets zijn, dus "keer aantal plays" is geen benadering van
  luistertijd maar een verzinsel. Een listen draagt nu de werkelijk gespeelde seconden (`played_secs`)
  en een echte herkomst: `frontend`, `mobile`, `auto` (telefoon in de auto) of `lms-web`. Beide velden
  zijn optioneel — een client die ze niet stuurt scrobbelt gewoon door, en oude listens blijven
  leesbaar met een lege duur en de oude waarde `lms`. Draai `migrate_v12_listen_played_secs.sql`, of
  laat music-manager de kolommen bij het opstarten zelf bijzetten. Voorwerk voor een MuMa Wrapped
  over 2026; zie [docs/designs/wrapped/](docs/designs/wrapped/).

### Fixed
- **De voortgangsbalk op de tv stond stil.** In de browser van de LG-tv bewoog de balk alleen als je
  op play of pause drukte. De balk hing volledig aan het `timeupdate`-event van het audio-element, en
  die tv stuurt dat alleen bij een toestandswissel — niet op de vier keer per seconde die de standaard
  voorschrijft. De speler leest de positie nu zelf elke 250 ms uit zolang er geluid speelt, op elk
  apparaat, dus hij hangt nergens meer af van hoe gul een browser met dat event is. Hetzelfde
  euvel hield op de tv ook de halverwege-listen tegen, want die telde mee op dezelfde tikken.
- **Een tv-stream zonder lengte liet de balk op nul staan.** Een getranscodeerde stream komt in
  stukjes binnen zonder `Content-Length`, en dan meldt het audio-element `Infinity` als lengte. Elke
  berekening daarmee wordt `NaN`, dus de balk bleef leeg, de tijd rechts bleef `0:00` en klikken om
  te spoelen gooide je positie weg. De speler valt nu terug op de lengte die de server bij de track
  meestuurt, en weigert te spoelen zolang er helemaal geen lengte bekend is.
- **De verhuizing zou een nieuw nep-label hebben opgeleverd.** De tagger leidt een label af uit de
  mappen boven een track. Zet je `__Free&None` op `/mnt/music/songs/`, dan is het naïeve antwoord dat
  al die tracks op een label genaamd `songs` staan — dezelfde fout als `Soundcloud`, alleen met een
  andere naam. Een pad onder een niet-label-map of een platformmap levert nu structureel geen label
  meer op, en beide indelingen blijven tijdens de verhuizing goed werken.
- **Een set die je wegklikt telt eindelijk mee.** De telefoon stuurde alleen een listen als een
  track vanzelf afliep of de wachtrij leeg raakte; drukte je op volgende, dan werd er niets
  vastgelegd. Bij tracks van gemiddeld een kwartier is doorspelen tot het eind juist de
  uitzondering, dus dat wiste stilletjes het grootste deel van je luistergeschiedenis — en het hardst
  in de auto, waar je het vaakst doorklikt. Elke keer dat je een track verlaat telt nu, met de tijd
  die hij daadwerkelijk speelde; korter dan vijf seconden blijft geen listen, want even proeven is
  geen luisteren.
- **De webspeler meldde een lange set als vier minuten.** Hij stuurt zijn listen halverwege, wat
  hem beschermt tegen een tab die dichtgaat, maar daardoor was de gemelde speelduur die van dat
  moment. Hij stuurt nu bij het einde van de track een correctie met dezelfde tijdstempel, zodat
  diezelfde listen wordt bijgewerkt in plaats van dat er een tweede bijkomt.

## [0.27.1] - 2026-08-23

### Fixed
- **Memories op web bleef leeg terwijl de server negentien jaren klaarzette.** De hoezenmozaïek op
  een jaartegel werd geïdentificeerd op het hoes-id, en juist in een echte bibliotheek komen de beste
  nummers van een jaar van hetzelfde album — dertien van de negentien jaren leverden twee keer
  dezelfde hoes. Svelte behandelt een dubbele sleutel als een harde fout, dus één tegel met een
  herhaalde hoes maakte niet die tegel saai maar de hele pagina blanco. De mozaïek telt nu per
  positie in plaats van per hoes, en een tegel gebruikt elke hoes hoogstens één keer, zodat er vier
  verschillende albums op staan in plaats van vier keer hetzelfde.

## [0.27.0] - 2026-08-23

### Fixed
- **0.26.0 heeft productie nooit gehaald; deze release brengt hem er alsnog heen.** De release-branch
  werd naar master gemerged terwijl `muma:deploy` nog in de wachtrij stond, waarna het opruimen van
  die branch de job onder zich vandaan trok: `couldn't find remote ref refs/heads/release/0.26.0`.
  De images waren op dat moment al gebouwd en zijn actueel, dus er is niets verouderds gepubliceerd —
  alleen de deploy bleef liggen, en `release:verify-deployed` weigerde daarop terecht te taggen. Deze
  release bevat geen functionele wijzigingen ten opzichte van 0.26.0.

## [0.26.0] - 2026-08-23

### Added
- **De downloaders halen de staart van een account weer op.** Ze stopten bij de eerste track die
  al binnen was, wat de dagelijkse ronde goedkoop houdt en tegelijk elk gat blijvend maakte: een
  ronde die halverwege een account op een 429 geparkeerd werd, liet de rest van dat kanaal staan, en
  elke volgende ronde stopte boven het gat. Er is nu een diepe ronde die het account plat uitleest —
  alleen ids, 200 per verzoek, niets opgehaald — daar het archief van aftrekt en alleen de echt
  ontbrekende tracks binnenhaalt. Dat is iets anders dan `break_on_existing` uitzetten, wat eerder de
  429's opleverde: zonder die stop haalt yt-dlp elk nummer van het kanaal volledig op om te ontdekken
  dat er zes missen. Een account van 5000 tracks kost zo 25 verzoeken in plaats van 5000. Gebeurt
  vanzelf elke `deep_sweep_days` (standaard 30) op een moment dat het account toch al aan de beurt
  is, of met de hand via `--deep`, eventueel met `--account`. `deep_sweep_max_downloads` (standaard
  50) begrenst wat één ronde ophaalt; wordt een ronde geparkeerd of afgekapt, dan blijft het account
  aan de beurt en gaat de eerstvolgende gewone ronde verder met de staart.
- **Tracks die bewust worden overgeslagen worden nu opgeschreven.** Een afwijzing op lengte liet
  nergens een spoor achter, dus een diepe ronde zou dezelfde veertig fragmenten van dertig seconden
  elke maand opnieuw vinden en het account nooit als klaar kunnen melden. De reden staat er nu bij,
  en bij een lengte-afwijzing ook de gemeten duur — verruim je de grenzen, dan komen die tracks
  vanzelf terug zonder één verzoek om te herontdekken wat ze zijn. Een track die drie rondes achter
  elkaar mislukt wordt afgeschreven in plaats van zijn account eeuwig open te houden.

## [0.25.0] - 2026-08-23

### Added
- **Memories op web is een fotoboek geworden.** In plaats van één lange pagina met alle jaren onder
  elkaar staat er nu een tegel per jaar: een mozaïek van de hoezen van dat jaar, het jaartal groot
  eroverheen, en daaronder de drie nummers die je er het meest mee hebt. Wat "het meest" is leidt de
  app af uit wat er al bekend is — vijf sterren gaat voor, en binnen én buiten die groep bepaalt het
  aantal beluisteringen de volgorde. Klik je op een tegel, dan krijgt dat jaar een eigen pagina op
  `/memories/2025` met de gewone tracklijst, vijftig nummers tegelijk en een knop om er vijftig bij
  te laden. De afspeelknop start het hele jaar, niet alleen wat er op dat moment staat. Zo'n adres
  is te bewaren en werkt na een refresh, met dit voorbehoud dat bij memories hoort: ze hangen aan de
  dag, dus morgen staan er andere nummers onder hetzelfde jaartal — of geen, en dat zegt de pagina
  dan zelf.
### Fixed
- **De label-backfill eindigde er netjes uit terwijl hij bestanden had overgeslagen.** Hij sloot af
  met een regel als `{'written': 412}`, en wat de schijf geweigerd had stond alleen als waarschuwing
  ergens halverwege een log van uren. Hij zegt nu hardop hoeveel bestanden niet geschreven konden
  worden, per label, met een paar paden erbij. Dat is geen fout van de backfill: op een steekproef
  van 22-08-2026 blijkt ongeveer één op de zes bestanden onder de EPs-map prima te lezen en elke
  schrijfpoging te weigeren, verspreid over mappen uit 2019 tot en met dit jaar. Die schade stond er
  al; de backfill is alleen het eerste dat hem hardop telt.

## [0.24.0] - 2026-08-22

### Added
- **De keten-test dekt nu vijf verhalen in plaats van één.** Naast het nummer dat gescand, gevonden,
  afgespeeld en als luisterbeurt vastgelegd wordt, staan er nu ook uitgeschreven: een luisterbeurt
  voor iets dat de bibliotheek niet heeft (die hoort bewaard te blijven en níet als treffer gemeld —
  dat is de tak waar het gros van de ingelezen geschiedenis in terechtkomt), een ster die in de
  speler wordt gezet en bij de bibliotheek moet aankomen aan het júiste nummer, een genre-tag die een
  te cureren genre wordt, en de vraag of de deur eigenlijk wel dicht zit. Dat laatste was een blinde
  vlek: alle andere scenario's melden zich netjes aan, dus als de sleutelcontrole zou wegvallen bleef
  de hele reeks groen.
- **En er staat nu een test op de fout die 887 sterren kostte.** Ratings hangen aan het kenmerk van
  een nummer, niet aan zijn pad, dus alles wat een bestand een nieuw kenmerk geeft maakt stilzwijgend
  los wat eraan hing — de nummers stonden er nog, er ging niets stuk, de sterren waren alleen weg.
  Dezelfde sleutel draagt ook de audiokenmerken. De test zet een ster, laat het bestand daarna
  helemaal opnieuw inlezen, en controleert dat het kenmerk hetzelfde bleef, dat de ster nog steeds
  bij het nummer te vinden is, en dat de bibliotheek er geen tweede kopie bij heeft gekregen.
- **De keten-test staat nu uitgeschreven in gewone zinnen.** De drie stappen — scannen, opvragen via
  Subsonic, een luisterbeurt registreren — staan in `tests/bdd/features/scan_to_listen.feature`, met
  de code eronder. Dat is niet alleen mooier lezen: de plekken waar de test minder dekt dan zijn naam
  belooft staan nu tússen de stappen, in hetzelfde stuk tekst als de beloftes, in plaats van in een
  codecommentaar dat je alleen ziet als je het bestand opent. De oude schrijfwijze is weg — twee
  versies van dezelfde keten betekent ze voor altijd gelijk houden. De taak duurt drie seconden
  langer, omdat de testrunners de benodigde uitbreiding niet hebben en die in een wegwerpcontainer
  wordt geïnstalleerd.
- **De keten-test speelt het nummer nu ook echt af.** Tot nu toe bewees hij dat een bestand
  gevonden kon worden, niet dat het beluisterd kon worden — de laatste schakel waar de test naar
  vernoemd is ontbrak dus. Hij haalt het nummer nu op bij de muziekserver en controleert twee
  dingen. Het bestand komt byte voor byte terug, even groot als de server zelf opgeeft: dat sluit uit
  dat het onderweg is omgezet, want een omgezette stroom is nog steeds geluid en nog steeds een
  geslaagd antwoord, alleen niet meer het bestand dat gescand werd. En er kan een losse byte uit het
  midden opgevraagd worden, wat een speler doet zodra je in een nummer springt; dat loopt via andere
  code dan een heel bestand ophalen, en een server die het stilzwijgend negeert stuurt gewoon alles
  terug en lijkt daarmee in orde.

### Fixed
- **Een release die een kopie van zijn eigen map meelevert kreeg die map als platenlabel.** De tagger
  telde vanaf het bestand twee mappen omhoog om het label te vinden. Bij scene-releases die hun eigen
  map nóg een keer bevatten staat het nummer een niveau dieper, en dan is die twee-omhoog niet
  `ABSLT Records` maar `ABSLT065 - Hartshorn_-_LOSE_CTRL-(ABSLT065)-SINGLE-WEB-2026-SRG`. Dat kwam
  zo in het label, het catalogusnummer én de copyright terecht, en daarmee ook in de bibliotheek: het
  label bestaat dan één keer voor die ene release. De tagger rekent nu vanaf de EPs-map naar beneden
  — de eerste map daaronder is het label, de tweede de release — zodat het niet meer uitmaakt hoe
  diep het bestand eronder staat. Paden buiten de EPs-map, waar de importer mee werkt, blijven de
  oude telling gebruiken. Voor de nummers die al fout getagd zijn is er
  `scripts/backfill_label_from_path.py`, die alleen bijwerkt wat aantoonbaar de eigen releasemap als
  label draagt en een met de hand gezet label met rust laat.
- **De keten-test controleerde niet wat hij leek te controleren.** De stap die opvraagt of de
  muziekserver het nummer terugvindt, keek alleen of er antwoord kwam. Subsonic verpakt fouten in een
  geslaagd antwoord, en de gebruiker waarmee gevraagd werd bestond helemaal niet — dus de test slaagde
  al die tijd op *"Wrong username or password"*. De teststack maakt nu eerst een gebruiker aan, wacht
  tot die bij de muziekserver is aangekomen, meldt de muziekmap aan en laat die scannen. Pas daarna
  loopt de test, en die controleert nu of het nummer echt in het antwoord staat. Dat kost ongeveer
  vier seconden extra en dekt de helft van de keten die tot nu toe alleen op papier gedekt was.

### Changed
- **De keten-test draait nu bij elke wijziging in plaats van op verzoek.** Hij stond op handmatig
  omdat een volledige stack duur leek: images bouwen, drie containers, een database. Gemeten loopt
  hij tussen de 45 en 80 seconden, waarvan bijna alles wachten is tot de containers opgestart zijn;
  de test zelf duurt twee seconden. Een test die de enige is die de hele keten bewijst en die pas
  draait als iemand eraan denkt, bewijst in de praktijk niets, dus hij draait nu overal mee en houdt
  de pipeline tegen als hij rood is. Hij heet ook niet langer `e2e:golden-path` maar
  `muma:e2e`, want dat is wat hij doet. Wat hij nog steeds niet doet is de luisterbeurt uit
  de geschiedenis teruglezen — dat komt uit het antwoord op de registratie zelf — en dat staat er nu
  ook zo bij.

## [0.23.1] - 2026-08-22

### Fixed
- **De app ging uit zodra je in de auto stapte.** MuMa openen terwijl de auto verbonden was sloot
  hem meteen weer af, terwijl dezelfde versie zonder autoverbinding gewoon opende en het scherm in
  de auto ondertussen bleef werken. De autostand vroeg aan de speler of er iets speelde — dat
  bepaalt of hij zelf naar voren komt of alleen een melding achterlaat — en stelde die vraag vanaf
  een plek in de app waar de speler niet bestaat: die hoort bij het hoofdscherm, niet bij de app als
  geheel. De vraag valt alleen op het moment dat de auto voor het eerst wordt gezien, en daarom was
  er niets aan de hand tot je instapte, en bleef het scherm in de auto — dat langs een heel andere
  weg bediend wordt — ongemoeid. Het hoofdscherm levert het antwoord nu zelf aan, dus er valt niets
  meer op te zoeken.

## [0.23.0] - 2026-08-21

### Added
- **Er is een eerste echte keten-test.** Alle bestaande tests bewijzen één onderdeel: dat LMS
  antwoordt in de vorm die de server verwacht, dat de database de query slikt, dat een functie doet
  wat hij belooft. Geen ervan bewijst dat een bestand dat op schijf verschijnt uiteindelijk een
  beluisterd nummer wordt. `e2e:golden-path` doet dat wel: hij zet de teststack op, legt er een
  nummer in, laat het scannen, zoekt het op via dezelfde Subsonic-route die de telefoon gebruikt,
  registreert een luisterbeurt en leest die weer terug. Handmatig te starten en dat blijft zo — hij
  bouwt images en houdt een stack minutenlang bezig, en niets wacht op zijn uitkomst.
- **De zoekbalk in de Android-app begrijpt nu ook een verzoek.** Wat je hardop kunt vragen —
  "speel willekeurig uptempo hardcore uit 2021 af" — leverde getypt een letterlijke zoektocht naar
  die hele zin op, en dus niets. Dezelfde ontleding die de auto en de microfoon gebruiken staat nu
  ook achter de zoekbalk, met dezelfde uitkomst. Eén woord wordt nooit ontleed: dat is verreweg de
  meeste zoekopdrachten en het minst waarschijnlijk een verzoek, en een zoektocht naar de band
  Editors hoort geen "alles met edit" op te leveren. Wordt er wél iets als verzoek gelezen, dan zegt
  de app dat, met een knop ernaast om alsnog op tekst te zoeken. En er is een tegel voor de snelle
  instellingen die het spraakscherm opent: twee vegen vanaf waar je ook bent, in plaats van
  ontgrendelen, app zoeken en wachten. Vanaf een vergrendeld scherm vraagt hij eerst om ontgrendelen.

### Changed
- **De statische analyse van de Android-code draaide nergens.** detekt zat al in de build, maar
  alleen achter een vlag die geen enkele taak meezond — dus faalde er nooit iets en merkte niemand
  het. Hij draait nu mee in de Android-controle. De vierenzeventig bevindingen die er al stonden
  zijn per module vastgelegd in een baseline in plaats van in één ruk gerepareerd: een controle die
  rood is op de dag dat je hem aanzet leert iedereen hem te negeren. Nieuwe bevindingen laten de
  taak wel vallen. De enige bevinding in code van vandaag is verholpen in plaats van vastgelegd.
- **De API accepteert niet langer verzoeken vanaf elke website.** Hij stond open voor iedere
  herkomst, met elke methode en elke header. Dat is op zichzelf geen manier om langs de
  authenticatie te komen — een browser stuurt niets mee en een aanroeper heeft de sleutel al nodig
  — maar het liet wel elke pagina die je opent de onbeveiligde eindpunten binnen dit netwerk
  uitlezen. Voortaan geldt een lijst, in te stellen met `MUMA_CORS_ORIGINS`; staat die niet
  ingesteld, dan blijven alleen de ontwikkelaanroepen over. De webinterface wordt door de
  LMS-server uitgeserveerd en praat dus met dezelfde herkomst, en de Android-app is geen browser,
  dus die merken er niets van. Blijkt er tóch een browserclient te zijn die het nodig heeft, dan
  zet `MUMA_CORS_ORIGINS=*` het oude gedrag terug zonder nieuwe uitrol.
- **Containers kunnen zichzelf geen extra rechten meer geven.** Alle zesenveertig services in de
  compose-bestanden draaien nu met `no-new-privileges`, wat een proces binnen een container belet
  via een setuid-programma meer te mogen dan het kreeg. Het kan niets breken dat nu werkt. Dat de
  containers als root en met een schrijfbaar bestandssysteem draaien blijft staan als vastgelegd
  openstaand punt: dat valt pas bij een uitrol om, en niet te testen zonder productie.
- **Afhankelijkheden wachten voortaan drie dagen voor ze worden voorgesteld.** Een versie die
  minuten geleden is gepubliceerd kan alsnog worden ingetrokken of besmet blijken, en dit project
  voegt een aantal ervan automatisch samen. Beveiligingswaarschuwingen wachten niet, en `yt-dlp`
  ook niet: achterlopen op dat pakket is precies wat downloaden stukmaakt. Tegelijk zijn de
  GitHub-workflows van de Android-app verwijderd — die kwamen mee uit het Ultrasonic-verleden,
  draaiden nergens, want dit is een GitLab-repo zonder GitHub-remote.
- **De pijplijn scant de code nu ook op bekende kwetsbare patronen.** `security:sast` draait
  semgrep over de hele boom. De tweehonderdtweeëndertig meldingen die er vandaag al staan zijn
  stuk voor stuk beoordeeld en vastgelegd in `security/accepted-sast-findings.txt`, met per regel
  de reden waarom ze blijven staan — de taak is daardoor groen vandaag en wordt alleen rood van
  iets nieuws, wat de enige manier is waarop een scanner gelezen blijft worden. Een tweede
  identieke regel op dezelfde plek telt als nieuw: "dat doen we elders ook al" dekt geen nieuwe
  code. Onder de beoordeelde meldingen zitten geen gelekte sleutels; wel drie punten die blijven
  staan als openstaand werk, namelijk dat de API elke herkomst toelaat (`allow_origins=['*']`),
  dat de containers als root en met een schrijfbaar bestandssysteem draaien, en dat de
  Android-app nog dode GitHub-CI-bestanden uit het Ultrasonic-verleden meedraagt.
- **De pijplijn controleert nu ook de shellscripts.** Drieënzestig scripts sturen het uitrollen,
  het taggen en elke testronde aan, en geen enkele taak keek er ooit naar — een fout erin bleek pas
  op het moment dat een uitrol hem uitvoerde. `muma:shellcheck` draait er shellcheck overheen bij
  elke wijziging aan een `.sh`-bestand. De lat ligt voorlopig op fouten, niet op waarschuwingen: er
  staan er tweeëndertig van de tweede soort open, en een controle die rood is op de dag dat je hem
  toevoegt leert iedereen hem te negeren. De ene echte fout die er stond is meteen verholpen — het
  installatiescript van de Android-app vergeleek een lijst met apps als één samengeplakte tekst,
  waardoor een naam die toevallig in een andere naam zat als geldig doorging.

## [0.22.1] - 2026-08-21

### Fixed
- **De Android-app startte niet meer op.** Versie 6.21.0 crashte meteen bij het openen, zodra het
  startscherm de eerste bewaarde kaart wilde tekenen. De nieuwe opslag van die kaarten liet de
  omzetter het type van de lijst uit de veldbeschrijving afleiden, en juist die beschrijving haalt
  de verkleiner uit een uitgavebouw weg — waardoor er losse gegevensbrokken terugkwamen in plaats
  van kaarten. In een ontwikkelbouw en in alle tests gebeurde dat niet, want daar wordt niet
  verkleind. De opslag geeft het type nu expliciet mee, precies zoals de al jaren werkende
  snelkoppelingenlijst dat doet, en een bewaarde regel die niet als kaart te lezen is telt als
  ontbrekend. Wie 6.21.0 draaide hoeft niets te wissen: de oude regels worden vanzelf overschreven.
- **Twee derde van je luistergeschiedenis was onvindbaar voor de rest van MuMa.** Een beluisterd
  nummer werd aan een track gekoppeld door de artiestnaam en de titel letterlijk te vergelijken.
  Op 16.830 gekoppelde luisterbeurten stonden er 35.761 in een tabel die niemand meer las, en het
  verlies zit vrijwel helemaal in geïmporteerde geschiedenis: wat live uit LMS binnenkomt verliest
  zes procent, de ListenBrainz-import drieënzeventig. Dezelfde muziek, andere spelling. Er is nu
  een ladder van vier stappen — letterlijk, genormaliseerd, zonder remix-achtervoegsel, en als
  laatste een gelijkenisdrempel — en per koppeling wordt vastgelegd welke stap hem maakte en hoe
  zeker die was. Elke stap is los uit te zetten en wat een stap koppelde is met één opdracht terug
  te draaien, want de laatste twee kunnen een luisterbeurt aan de verkeerde track hangen. Een
  achtergrondtaak probeert de overgebleven rijen periodiek opnieuw, met een oplopend wachtvenster,
  zodat een nieuwe download een luisterbeurt uit 2019 alsnog kan koppelen zonder dat de taak elke
  ronde dezelfde kansloze rijen doorploegt.
- **De geanalyseerde audiokenmerken hoorden bij niets wat je ooit gedraaid hebt.** Er staan
  90.107 rijen met tempo en klankkenmerken in de database, en elke functie die erop leunt las nul
  procent dekking — het zag eruit alsof de analyzer nooit gelopen had. De sleutel bleek iets anders
  te zijn dan waarvoor hij werd aangezien: de kenmerkentabel is gesleuteld op een hash van het
  bestandspad, terwijl de lezers hem vergeleken met de track-identificatie van de scanner. Dat matcht
  vrijwel nooit. Dat sommige rijen tóch aansloten hield het verborgen: de analyzer maakt zelf
  tracks aan waarvan de identificatie wél die pad-hash is, en juist díe tracks speelt niemand af.
  De lezers gebruiken nu de echte verwijzing, en een migratie herstelt die verwijzing voor de
  bestaande rijen langs beide routes die nog oplossen — ook waar er een verkeerde waarde stond, wat
  het oude migratiescript liet liggen omdat het alleen lege waarden vulde.



## [0.22.0] - 2026-08-21

### Added
- **De Android-app heeft een rijstand.** Alles wat de telefoon in een houder moet kunnen — wat er
  speelt, spoelen, waarderen, drie plekken waar je vaak heen gaat, en de microfoon — staat op één
  scherm met knoppen op armlengte. De app merkt de auto zelf op: een head unit, een
  bluetooth-apparaat dat jij als auto hebt aangevinkt, of een schakelaar in de instellingen.
  Speelt er al muziek, dan komt het scherm naar voren; anders krijg je een melding die je aantikt.
  Dat onderscheid is er omdat Android sinds versie 14 alleen bel- en wekker-apps ongevraagd een
  scherm laat openen — waar dat recht ontbreekt wordt het vanzelf een melding, en één regel in de
  instellingen brengt je naar de systeempagina als je het toch wilt. Wegdrukken is definitief
  zolang de auto verbonden blijft, en zodra die verbinding wegvalt sluit de rijstand zichzelf.
  Oordopjes tellen nooit mee: welke apparaten je auto zijn kies je zelf, want de apparaatklasse
  liegt beide kanten op.
- **De Android-app opent op wat er de vorige keer stond, in plaats van op skeletten.** Elke koude
  start liet het startscherm en de bladerschermen (genres, jaren, labels, festivals, line-ups)
  pulserende plaatshouders tonen terwijl de server opnieuw werd bevraagd om gegevens die sinds de
  vorige keer bijna nooit veranderd waren. De caches die er al waren leefden alleen in het geheugen
  en gingen dus met het proces mee dood. De kaarten die een sectie of een bladerscherm laat zien
  worden nu op schijf bewaard en meteen weer neergezet, met een dunne voortgangsbalk onder de kop
  zolang de verse kopie onderweg is; de kaarten zelf zijn direct aantikbaar. Mislukt het verversen,
  dan blijven de kaarten staan en stopt de balk. Een lege sectie wist zijn eigen bewaarde kopie, en
  een andere server of de Sets-schakelaar is een misser in plaats van een verkeerd antwoord.

### Fixed
- **Een dynamische afspeellijst kwam bijna leeg terug.** Een lijst als "Hardstyle" die om 500
  nummers vroeg leverde er een handvol, wat eruitzag alsof de bibliotheek gewoon weinig hardstyle
  bevatte. De waarderingsfilter stond echter altijd in de query, ook op zijn standaardwaarde 0 tot
  100 — bedoeld als "geen filter". Waarderingen komen binnen via een LEFT JOIN, dus een nummer
  zonder waardering heeft er geen, en niets is nooit groter dan nul: daarmee viel elk ongewaardeerd
  nummer af. Dat zijn er 301.340 van de 302.561. Een bereik dat de hele schaal beslaat bouwt nu geen
  filter meer op; vraag je wel om vier sterren en hoger, dan blijven ongewaardeerde nummers er
  gewoon buiten.
- **Sterren geven vanuit de auto werkt weer op een nummer dat al sterren had.** Een waardering die
  op het spelende item werd gezet, ging naar de cache van de track en naar de extras van het
  media-item, maar datzelfde item draagt de waardering nog een tweede keer als `StarRating`. Die
  wordt bij het bouwen van het item vastgelegd en is daarna onbereikbaar, want `MediaMetadata` is
  onveranderlijk. De trackcache bewaart een item tien minuten, korter in een wachtrij voorbij de 250
  items, en elke herbouw daarna liet de bevroren kopie winnen. De knop werd dan getekend met de
  waardering van het moment waarop de wachtrij werd gebouwd, waardoor de volgende tik uitkwam op de
  waardering die net gezet was en `RatingManager` die als dubbel weggooide: de knop reageerde niet
  meer, en een nummer dat op vijf sterren stond sprong terug naar geen in plaats van door te tellen.
  Een herbouw leest nu de extras; de `StarRating` is alleen nog de terugval voor items die zelf geen
  extras-waarde hebben.
- **Een waardering bereikt nu elke bewaarde kopie van het nummer, niet alleen de server.**
  `setRating` stuurde de nieuwe waardering door en verder niets, dus de kopieën waaruit de app
  antwoordt — het album waarin gerate werd, de lijsten op het startscherm, de bladerboom in de auto
  — hielden de waardering waarmee ze waren opgehaald tot hun cache verliep. Terugkomen bij een
  nummer liet het oude getal zien, wat leest als een waardering die is gewist. Die kopieën worden nu
  ter plekke bijgewerkt, en het bewaarde media-item, waarvan de metadata niet bij te werken is,
  wordt weggegooid zodat het bij de volgende leesbeurt met de nieuwe waardering wordt herbouwd.

## [0.21.1] - 2026-08-21

### Changed
- **Android-builds worden gepubliceerd onder de eigen naam van de app.** Elke APK ging nog steeds
  omhoog als `ultrasonic-*`: apk-hoster groepeert builds op het voorvoegsel van de bestandsnaam, en
  precies dat voorvoegsel vraagt een geïnstalleerde app op bij het controleren op updates — het
  hernoemen op zichzelf zou elke telefoon voorgoed "je bent bij" hebben verteld. Uploads heten nu
  `muma-mobile-*` en de updatecontrole vraagt om die reeks; oudere installaties die nog om
  `ultrasonic` vragen worden er door apk-hoster naartoe gewezen via de nieuwe instelling
  `APK_ALIASES`, die daar is ingesteld. Ook het account waarmee een build bij apk-hoster inlogt is
  meeverhuisd, van `ultrasonic` naar `muma-mobile`; het oude account blijft staan voor builds die
  al geïnstalleerd zijn.

## [0.21.0] - 2026-08-21

### Added
- **Een instelwizard in de Android-app die na een update laat zien wat er veranderd is.**
  Tweeënzestig instellingen staan op één doorlopend scherm, en niets daarop zegt welke er vorige
  week bij kwamen. De wizard loopt er negen één voor één langs — server, stijl, app-icoon,
  interfacegrootte, herinneringen op het startscherm, offline opslag, alleen downloaden op wifi,
  de balk met wat er speelt, en MuMa-synchronisatie — elk met uitleg én de knop zelf, zodat een
  instelling te wijzigen is op de plek waar hij wordt uitgelegd. Instellingen die nieuw zijn sinds
  de versie waar je vandaan komt krijgen het label Nieuw en komen vooraan, waardoor een update-ronde
  kort blijft. De wizard staat ook altijd in het overloopmenu, en een update die geen instellingen
  toevoegt toont gewoon de changelog zoals voorheen.
- **De Android-app heeft nu een handleiding aan boord, onder Help in het overloopmenu.** Alles
  wat MuMa kan was tot nu toe alleen te ontdekken door overal op te drukken: de Sets-schakelaar,
  waar de twaalf bibliotheektabbladen voor zijn, dat één gesproken zin tegelijk een genre, een
  jaar en een waardering mag dragen, en dat de app zichzelf buiten de Play Store om bijwerkt.
  Help is twaalf hoofdstukken in leesvolgorde, dichtgeklapt tot je er één opent, elk met een
  schermafbeelding die je kunt vergroten en, waar lezen de langzaamste manier is om het te
  leren, een knop rechtstreeks naar het scherm dat beschreven wordt. De schermafbeeldingen zijn
  voorlopig plaatshouders: een echte zet je erin door een PNG over het gelijknamige bestand in
  `app/src/main/res/drawable-nodpi` te zetten, en `docs/manual-screenshots.md` vertelt welke
  opname waar hoort.

### Changed
- **Het Over-scherm verwijst niet meer naar sites die er niet meer bij horen.** "Website openen"
  en "Bug melden" stuurden je de app uit naar adressen die niets met deze installatie te maken
  hebben; beide knoppen zijn weg, zodat alleen bijwerken, de wijzigingslijst en het logboek
  overblijven. Dezelfde opruiming liep door de rest van de tekst: de vertaalde Over-tekst
  beschreef in negen talen nog het oude Ultrasonic-product en de bijbehorende Subsonic-servers,
  en is vervangen door de Nederlandse en Engelse MuMa-tekst die er al stond. Waar de oude
  productnaam nog in een vertaling stond — het welkomstscherm, de crashmelding, de
  versiewaarschuwing — staat nu MuMa. In het beheerscherm heet de app bij de sleuteluitleg
  voortaan MuMa Mobile, en het bijdragedocument van de app wijst naar de eigen issuetracker in
  plaats van naar het opgeheven Ultrasonic-project.
- **Een wijziging aan een Dockerfile draaide geen enkele taak.** Zes van de zeven images werden
  pas voor het eerst gebouwd op een release-tak, minuten voor de uitrol — de duurste plek om
  te ontdekken dat er iets niet compileert. Een merge request die een Dockerfile raakt bouwt ze
  nu allemaal, zonder ze te publiceren, en start daarnaast de teststack op om te zien of hij
  gezond bovenkomt.
- **De pijplijn wacht niet meer op werk waar niets van afhangt.** De integratie- en
  browsertaken stonden achter de Android-controle omdat ze toevallig in een latere fase zaten;
  op de 0.19.0-pijplijn was dat zevenendertig minuten wachten op een uitkomst die geen van
  drieën gebruikt. Ze noemen nu zelf waar ze op wachten. Het taggen op master wacht om dezelfde
  reden niet langer op een testronde die de release-tak al gedraaid heeft.
- **Kleiner onderhoud aan de pijplijn.** De Android-controle mag nog twintig minuten duren in
  plaats van vijfenveertig, nu gelijktijdige Android-taken elkaar niet meer uithongeren; de
  dekkingsrapporten van de frontend- en servertests worden ook bewaard als die test faalt,
  precies de keer dat je ze wil lezen; en de foutopsporingsregels die elke Python-testronde
  begonnen met hostnaam, IP-adres en gebruikersnaam zijn weg.

### Fixed
- **Een uitgerolde release-tak wordt nu altijd opgeruimd, ook als er iets misging.** Het
  verwijderen van de zojuist samengevoegde `release/*`-tak hing achteraan het terugsamenvoegen
  naar develop, en erfde daarmee twee voorwaarden die er niets mee te maken hebben: dat script
  stopt er vroegtijdig mee zodra develop de commit al bevat — zo hield `release/0.8.3` zijn tak —
  en sinds de nieuwe versiecontrole hing het er ook van af of productie wel draait wat master
  zegt. Juist het geval dat die controle moet vangen liet dus een samengevoegde release-tak op
  de server achter, en dat is precies de opzet waarin een later opnieuw gestarte pijplijn oude
  images als `latest` publiceert en terugrolt (bugrapport 016). Het opruimen is nu een eigen taak
  die nergens op wacht: een tak die al in master zit weggooien is veilig, wat de tag of de uitrol
  ook deden.
- **Een uitrol die stukliep meldde zichzelf als geslaagd.** De laatste stap van de uitrol
  vroeg de productieserver netjes welke containers er draaiden, drukte dat af, en keek er
  vervolgens niet naar: `docker ps` eindigt succesvol, ook als het een container laat zien die
  elke seconde opnieuw crasht, en ook als het helemaal niets laat zien. Elke storing van het
  afgelopen halfjaar zag er daardoor uit als een groene uitrol. Die stap controleert nu echt:
  geen container in een herstartlus of met een falende gezondheidscontrole, en `/health` moet
  binnen drie minuten antwoorden met status ok én met de versie die zojuist is uitgerold. De
  container die één keer draait en daarna bewust stopt wordt herkend aan zijn herstartbeleid en
  niet langer als storing geteld.
- **Een release kon een merkteken krijgen zonder ooit uitgerold te zijn.** 0.19.0 stond een dag
  lang getagd op master terwijl productie op 0.18.2 bleef staan: de uitrol was *overgeslagen*,
  en een overgeslagen taak houdt niets tegen. Voor het taggen wordt nu aan productie zelf
  gevraagd welke versie er draait, en komt die niet overeen, dan gebeurt er niets.

## [0.20.0] - 2026-08-21

### Added
- **Het nieuws van het uur, ook onderweg.** MuMa neemt het bulletin nu zelf op van de live
  stream van NPO Radio 1 — geen enkele feed publiceert het NOS-radiobulletin op afroep, dus
  meeluisteren en bewaren is de enige route. Elk heel uur wordt tien minuten getapt, de laatste
  twaalf opnames blijven staan, en een opname die korter is dan een minuut wordt weggegooid in
  plaats van bewaard: een afgekapt bulletin in de auto is erger dan geen bulletin. In Android
  Auto staat er een Nieuws-map naast Radio en een nieuwsknop bij de bediening: één tik legt de
  wachtrij vast, speelt het bulletin, en zet daarna de muziek terug op de seconde waar je was.
  Radio is de uitzondering, want die tijdlijn is van de server: dat kanaal wordt na het nieuws
  opnieuw afgestemd. De webspeler doet hetzelfde, en het beheerscherm kreeg een Nieuws-tab met
  bron, schema, bewaartermijn en een knop om meteen op te nemen.

### Changed
- **De Android-app bouwt nu in seconden in plaats van soms een uur.** De pijplijn gaf elke
  gelijktijdige taak zijn eigen Gradle-map, dus de eerste bouw op een verse plek haalde alle
  afhankelijkheden opnieuw op en begon zonder cache: dezelfde controle die warm drie minuten
  duurde liep dan vijftig tot negentig minuten en sloeg tegen de tijdslimiet aan. De
  mobiele taken draaien nu gegarandeerd één voor één en delen daardoor veilig één warme
  Gradle-map. Daar bovenop verdwenen twee dingen die de app nooit gebruikte maar wel elke bouw
  betaalde: de kapt-annotatieverwerker, waarvoor geen enkele verwerker meer bestond sinds Room
  op KSP overging, en DataBinding, dat in geen van de 78 layouts voorkwam. Zonder DataBinding
  kon ook de configuratiecache aan. Een verse checkout met warme cache doet de testronde nu in
  twaalf seconden.

## [0.19.0] - 2026-08-20

### Fixed
- **Een genre hardop vragen vindt het nu ook als de telefoon er één woord van verkeerd verstaat.**
  "Uptempo hardcore" leverde het brede genre Hardcore op, of helemaal niets, vaak genoeg om spraak
  niet de moeite waard te maken. Er waren drie dingen tegelijk mis. De spraakherkenning had nooit
  te horen gekregen welke genres deze bibliotheek bevat, dus die antwoordde met het gewone
  Nederlands dat er het dichtst bij lag — hij krijgt nu de genres met de meeste muziek mee voordat
  hij begint te luisteren. Een naam die net verkeerd terugkwam was daarna niet te redden: een
  genre waarvan alle woorden op één na kloppen kwam nergens exact overeen en viel dan terug op het
  genre dat er toevallig in zat. "Temple hardcore" bevat "hardcore", dus een verzoek om het ene
  genre antwoordde met alles wat onder het andere valt. Zo'n naam wordt nu gelezen als het genre
  waar hij op lijkt, mits de rest exact overeenkomt en het om een van de grote genres gaat. En
  waar de bibliotheek één genre op meerdere manieren spelt wint nu de spelling waar de muziek in
  zit, in plaats van degene die de server toevallig het eerst noemde.

### Added
- **Android Auto toont nu een zoekknop binnen MuMa.** De app gaf nooit aan dat er gezocht kon
  worden, dus verborg de auto zijn eigen zoekknop en was de globale zoekbalk van de auto de enige
  ingang. Zoeken vanuit MuMa gebruikt dezelfde spraakparser als al het andere.

## [0.18.2] - 2026-08-20

### Fixed
- **Een uitgesproken genre vindt nu al zijn muziek, niet toevallig de spelling die de server het
  eerst noemt.** Om hardstyle vragen leverde helemaal niets op, terwijl de zin correct begrepen
  was en de bibliotheek twintigduizend hardstyle-nummers bevat. De bibliotheek bewaart een genre
  onder elke schrijfwijze die ooit in een tag stond — "Hardstyle", "HARDSTYLE" en "hardstyle"
  zijn drie losse ingangen — en MuMa hield degene die als eerste terugkwam. Dat bleek een
  restant met vier lange mixen, dus een verzoek om nummers vond er daar geen één van. Een
  uitgesproken genre draagt nu élke schrijfwijze die de bibliotheek ervan heeft. Een genre dat
  het uitgesproken genre alleen maar bevat, zoals "Mainstream Hardstyle", blijft er buiten.

## [0.18.1] - 2026-08-20

### Fixed
- **MuMa Voice sluit de app niet langer af zodra hij iets gevonden heeft om te spelen.** Het
  scherm las de zin, doorzocht de bibliotheek en klapte er dan op de allerlaatste stap uit — wat
  eruitzag alsof de zoekopdracht mislukt was terwijl die juist geslaagd was. De speler hoort bij
  het scherm dat hem draagt en dit scherm vroeg hem op de verkeerde plek op; omdat die vraag pas
  gesteld wordt als er echt muziek te starten valt, leek alles daarvoor in orde.

## [0.18.0] - 2026-08-20

### Added
- **MuMa Voice: een microfoonknop in de mobiele app, op dezelfde pijplijn als de auto.** Tik op
  de microfoon in de werkbalk en zeg wat er moet spelen. De tekst gaat door precies dezelfde
  parser en zoekmachine die Android Auto gebruikt, dus een zin die daar werkt werkt hier ook.
  De spraakherkenner geeft meerdere lezingen van dezelfde zin terug en MuMa probeert ze op
  volgorde — dat is wat "hard style" alsnog op "hardstyle" laat uitkomen. Op hetzelfde scherm
  staat een tekstveld om een formulering uit te proberen zonder te praten.
- **Een vraag in plaats van een gok, als een naam meer dan één ding kan zijn.** "Speel
  Thunderdome" kan het label, het album of de playlist zijn. MuMa Voice laat de mogelijkheden
  zien en vraagt welke je bedoelde; het antwoord kun je aantikken of inspreken ("het label").
  Android Auto kan niets vragen — een mediasessie heeft geen weg terug — dus daar wordt de
  sterkste lezing gekozen en worden de afgewezen lezingen vastgelegd.
- **Albums, playlists, titels en sterren kunnen nu uitgesproken worden.** "Speel album
  Thunderdome af", "speel de afspeellijst zomer af", "speel het nummer dragonborn af", "speel
  hardstyle met minstens 4 sterren af". Twee waarden van dezelfde soort kan ook: "speel
  hardstyle en hardcore af" is één zoekopdracht, terwijl "drum and bass" één genre blijft.
- **Voice diagnostics, onder Over.** Elke spraakopdracht laat nu een volledig spoor achter: via
  welke callback hij binnenkwam, de zoekopdracht precies zoals ontvangen, élke extra die Android
  meestuurde, de tokens, welke parserregel welk woord opeiste, wat de bibliotheek over elke term
  zei, en het verzoek dat er uiteindelijk uitging. De laatste vijftig worden bewaard en zijn als
  tekst te delen. Hiermee is te achterhalen wat Google herschrijft vóór MuMa iets ziet.

### Fixed
- **Een uitgesproken titel wordt op de titel gezocht, niet op de hele zin.** Als geen enkel
  filter matchte kreeg de terugvalzoekopdracht de hele uiting mee, dus "speel het nummer
  dragonborn af" zocht letterlijk daarnaar en vond niets. Hij zoekt nu op "dragonborn".
- **Een uitgesproken sterrenfilter sleept niet langer elke ongewaardeerde track mee.** De server
  verbreedt een losse minimumwaardering tot alles wat niemand ooit beoordeeld heeft, dus er gaat
  nu altijd een bovengrens mee.

## [0.17.1] - 2026-08-20

### Fixed
- **De hele site gaf 504 zodra er genoeg artiestafbeeldingen tegelijk werden opgevraagd.** LMS heeft
  net zoveel HTTP-threads als de machine cores heeft, en elke aanvraag die een plaatje bij MuMa
  ophaalde hield er daar één van bezet zolang hij op antwoord wachtte. Genoeg tegels op één scherm
  en er was geen thread meer vrij: de server bleef draaien, hield zijn poort open en beantwoordde
  niets meer — een scrobble niet, een gewone ping ook niet — tot iemand hem herstartte. Die
  aanvragen wachten nu naast de threads in plaats van erop. Voor de overige MuMa-calls, die de
  statuscode van MuMa letterlijk moeten doorgeven en dus niet op dezelfde manier opzij kunnen, geldt
  een harde limiet: hooguit de helft van de threads mag tegelijk staan wachten.
- **Een ongeldige API-sleutel greep bij elke poging de exclusieve databaselock.** Een client die na
  een herstart met een dode sleutel bleef proberen — muma-radio doet dat elke vijf seconden — zette
  daarmee elke keer een schrijftransactie op, ook al bestond de sleutel niet. Tijdens een scan stond
  die achter de scanner in de rij. Onbekende sleutels worden nu zonder lock afgehandeld en kort
  onthouden.
- **Subsonic-sleutels overleven een herstart.** Ze stonden in een database die alleen in het
  geheugen bestond, dus elke herstart van LMS gooide ze weg. Voor een client was dat niet te
  onderscheiden van een verkeerde sleutel: die bleef eindeloos proberen met iets dat nooit meer zou
  werken. Daardoor was het herstarten van LMS ook precies wat het volgende probleem opzette.
- **Eén mislukte aanvraag legde niet langer de hele wachtrij stil.** Ging er één call naar MuMa mis,
  dan pauzeerde LMS dertig seconden lang al het uitgaande verkeer — scrobbles en ratings incluis.
  Dat gebeurt nu pas als MuMa meerdere keren achter elkaar niet reageert.
- **`getCoverArt` meldt weer de echte status.** "Geen afbeelding voor deze artiest" is een 404, maar
  kwam in het log terecht als een 502. Dat is waarom het log vol stond met gateway-fouten die nooit
  een gatewayprobleem waren.
- Een vastgelopen LMS herstart nu zichzelf in plaats van te wachten tot iemand merkt dat de site
  eruit ligt.

## [0.17.0] - 2026-08-20

### Added
- **Releases die de importer niet kan wegzetten staan nu als voorstel in het beheerscherm.** Een
  release werd overgeslagen zodra het catalogusnummer niet in de labeltabel stond, of zodra er
  helemaal geen catalogusnummer in de mapnaam zat. Die bleef dan liggen in de importmap en werd
  elke ronde opnieuw als waarschuwing gelogd, zonder dat er iets anders mee gebeurde dan een
  handmatige ingreep in de database. De importer leest nu het label uit de bestanden zelf — uit de
  labelvelden van een FLAC, het publisher-frame van een MP3, en anders uit de `.nfo` — en zet het
  als voorstel klaar onder Labelvoorstellen.
- **Eén bevestiging ruimt een heel label op.** De lijst staat gegroepeerd op voorgesteld label, dus
  je bevestigt in één keer alle releases van bijvoorbeeld Brutal Kuts in plaats van vijftien keer
  hetzelfde. Bevestig je een voorstel met catalogusnummer, dan wordt die koppeling onthouden en
  lopen alle volgende releases van dat label vanzelf door. Zit er geen catalogusnummer in, dan valt
  er niets te onthouden en wordt alleen die ene map weggezet. Het labelveld kiest uit labels die al
  bestaan, zodat een andere schrijfwijze geen tweede labelmap aanmaakt. Een voorstel dat je afwijst
  komt niet meer terug, hoe vaak de importer die map daarna ook nog tegenkomt.

## [0.16.0] - 2026-08-19

### Added
- **De uiterlijk-instelling in de mobiele app kiest nu een hele stijl in plaats van alleen een
  accentkleur.** Er stond Groen en Blauw, wat één kleurtje verwisselde en verder alles hetzelfde
  liet. Er staat nu **Spotify** en **MuMa**. Spotify is de app precies zoals hij was. MuMa houdt
  hetzelfde groen voor nummers en blauw voor sets, maar staat op een warmere, diepere
  achtergrond, scheidt rijen met een haarlijn in plaats van ze als kaartjes te laten zweven,
  dimt derde- en vierderangs tekst echt in plaats van alles hetzelfde grijs te geven, rondt
  hoeken strakker af, dimt de veldlabels in plaats van ze groen te kleuren en kleurt een
  ingevulde ster goud. Spotify blijft de standaard, dus er verandert niets tot je zelf wisselt,
  en wisselen werkt meteen. Het blauwe accent vervalt; het blauwe app-icoon is een aparte
  instelling en blijft gewoon staan.

### Fixed
- **Een geselecteerde regel in de mobiele app verspringt niet meer van vorm.** De geselecteerde
  achtergrond was op 8dp afgerond en de gewone op 16dp, dus een regel klapte zichtbaar om zodra
  je hem aantikte.
- **Het uitklapvak in de mobiele app is geen witte balk met onleesbare tekst meer.** Het was nog
  geschilderd voor een lichte modus die de app al sinds ver voor de rebrand niet meer heeft:
  witte vulling, grijze rand en zwarte tekst, op een zwart scherm.

## [0.15.0] - 2026-08-19

### Added
- **Weekpakketten met meerdere releases worden nu vanzelf uitgepakt tot op de release.** Zet je
  een weekpakket zoals `HHC-2026-WEEK-33.rar` in de importmap, dan blijft na het uitpakken de
  map van het pakket zelf staan met alle releases daarin. De importer keek alleen naar de
  bovenste laag, zag daar geen catalogusnummer in en logde "No valid CAT ID found", waarna geen
  van de releases eronder ooit is opgepakt. Er zit nu een stap tussen die de releases uit de
  pakketmap omhoog haalt, zodat ze precies zo verwerkt worden als een losse download. De pakketmap
  verdwijnt daarna, met de losse `.nfo`- en `.sfv`-bestanden erin. Bestaat een release al in de
  importmap, dan blijft die staan en wordt er niets overschreven. Een album waarvan de nummers in
  één submap staan, zoals `CD1`, wordt met rust gelaten.

## [0.14.0] - 2026-08-19

### Added
- **De stemzoekopdracht begrijpt nu een heel verzoek in plaats van alleen een genre.** "Speel
  willekeurige favorieten uit 2023 af" kwam bij de vrije-tekstzoekopdracht terecht, die alleen
  artiest-, album- en titelnamen kent, en antwoordde met stilte. De zin wordt nu uit elkaar
  gehaald in de onderdelen waar de bibliotheek op kan filteren -- een genre, een artiest ("van
  headhunterz"), een label ("label art of creation"), een jaar ("uit 2021"), je favorieten, en
  nummers of livesets -- plus een volgorde: "willekeurig" schudt, "recent" speelt op releasedatum,
  "recent toegevoegd" op de datum dat de bibliotheek bijkwam. Alles is combineerbaar en alles is
  optioneel, in het Nederlands en in het Engels; "speel recent af" speelt de hele bibliotheek op
  releasedatum.

  Elke uitgesproken naam wordt eerst tegen de bibliotheek gelegd, want de server antwoordt op een
  filterwaarde die hij niet kent met een fout in plaats van met een lege lijst -- één verkeerd
  verstaan woord zou anders het hele verzoek kosten. Wat niet geplaatst kan worden valt weg en de
  rest speelt gewoon, dus "speel zwabberkore uit 2021 af" speelt 2021. Kan er niets geplaatst
  worden, dan neemt de gewone zoekfunctie het over en zoekt op titel -- daarom vindt "speel
  headhunterz af" nog steeds het nummer met die naam en niet alles wat de artiest ooit uitbracht.
- **Een pagina met alle spraakcommando's**, te vinden via Over. Niets van bovenstaande formulering
  is te ontdekken door tegen de auto te praten en te hopen.
- **Een tracklijst in de app is nu zelf te sorteren.** Open je een genre, een label, een
  festival, een jaar, een podcast, een line-up of een sterrenfilter, dan kwam die lijst altijd
  terug op releasedatum, zonder manier om dat te wijzigen. Boven de lijst staat nu dezelfde
  keuzelijst als in de webinterface: recent uitgebracht, recent toegevoegd, meest gespeeld,
  recent gespeeld, op waardering, op naam en willekeurig. De lijst opent op de sortering
  waarmee je binnenkwam, dus zonder een keuze te maken verandert er niets. Albums, afspeellijsten
  en podcastafleveringen houden hun eigen volgorde en krijgen de keuzelijst niet, en in
  offlinemodus blijft hij verborgen omdat de sortering daar bij de server vandaan zou moeten komen.

### Fixed
- **In de Android Auto-bibliotheek stond "Favorieten" twee keer.** De nummers met een ster en de map
  met favoriete genres en tegels hadden in het Nederlands allebei dezelfde naam, dus in de auto was
  niet te zien welke welke was. Er is nu één map Favorieten, met daarin "Favoriete nummers" naast de
  favoriete genres en playlists.

## [0.13.3] - 2026-08-19

### Changed
- **Een genre dat je met je stem opvraagt speelt nu op releasedatum, niet op datum
  toegevoegd.** "Speel genre hardstyle af" gaf de nummers die het laatst in de bibliotheek
  waren beland, en bij een importronde is dat honderd nummers uit twintig jaargangen die op
  één middag binnenkwamen. De stemzoekopdracht gebruikt nu dezelfde sortering als het blok
  "Recent uitgebracht" op de startpagina. Nummers zonder releasedatum vallen terug op hun
  bestandsdatum en sluiten de rij, dus er verdwijnt niets uit het resultaat. De bladerboom
  onder Genres sorteert ongewijzigd op datum toegevoegd.

## [0.13.2] - 2026-08-19

### Changed
- SoundCloud accounts are now checked at a rate that follows how recently they
  uploaded, across five tiers: six-hourly for accounts that posted this week, then
  daily, every three days, weekly, and monthly for accounts dormant over a year. The
  four new tier cooldowns are configurable under Systeembeheer → Downloaders → Timing;
  the dormant one doubles as the longest a returning account can go unnoticed.
- A SoundCloud check now begins with a single-request probe for the account's newest
  track, and skips the account entirely when that track is already archived.
- A sweep now visits the accounts that are furthest past their own cooldown first,
  instead of working alphabetically.

### Fixed
- **De beheerpagina herkent je weer als beheerder.** De gedeelde systeemsleutel stond in de
  productie-`.env` als `MUMA_API_KEY`, maar de compose-stack gaf alleen `API_KEY` door -- en die
  regel was leeg. Zolang de code nog een hardgecodeerde sleutel als terugval had, viel dat niet op;
  sinds die terugval weg is, weigert de server elke aanroep met de systeemsleutel. Dat waren niet
  alleen `/api/auth/verify` (403) en `/api/config` (401) van de beheerpagina, maar ook de
  scrobble- en waarderingswebhooks van LMS, die stilzwijgend werden weggegooid. Beide spellingen
  worden nu doorgegeven, en de pijplijn weigert voortaan te deployen als geen van beide is gezet.
- **Een sleutel die de server niet meer accepteert blokkeert de beheerpagina niet langer.** De
  automatische login liep alleen als er helemaal geen sleutel was, dus een verouderde sleutel in de
  browseropslag bleef eeuwig hangen: elk bezoek toonde "kan niet verbinden" en `isAdmin` viel terug
  op alleen de Subsonic-rol, waardoor je beheerstatus willekeurig leek te verdwijnen. Een 401 of 403
  gooit de sleutel nu weg en logt opnieuw in met je spelerwachtwoord. Een 5xx of een mislukt verzoek
  doet dat expres niet -- een haperend netwerk is geen bewijs dat je sleutel fout is.
- SoundCloud checks paged an account's entire catalogue before downloading anything,
  because `lazy_playlist` was off and `break_on_existing` could therefore only stop the
  download loop. A large account cost 28 API requests per check whether or not it had
  anything new.
- **"File saved" betekent voortaan dat het bestand ook echt geschreven is.** De tagger logde die
  regel één statement vóór de schrijfactie, dus een write die het bestandssysteem weigerde kwam er
  alsnog als succes uit -- de backfill over de bibliotheek logde 17356 keer "File saved" voor 8885
  daadwerkelijk geschreven bestanden, met de waarheid alleen in een WARNING twee regels verderop.

## [0.13.1] - 2026-08-18

### Fixed
- **"Speel mainstream hardstyle af" speelt nu dat genre.** Het woord "genre" was het enige signaal
  waar de spraakzoekactie op afging, en juist dat woord haalt Google Assistent uit de zin zodra hij
  begrijpt dat er een genre bedoeld wordt -- dus kwam er "mainstream hardstyle" binnen, ging dat
  naar de vrije-tekstzoekactie, en landde je op een album. Een zin zonder genre-bewoording wordt nu
  ook als genrenaam aangeboden, en speelt dat genre zodra hij exact overeenkomt met een genre uit de
  bibliotheek. Minder dan exact blijft bij de vrije-tekstzoekactie, zodat een titel die alleen maar
  op een genre lijkt niets merkt. Het aanspreken van de app ("... af op MuMa") wordt voortaan van de
  zin afgehaald, wat eerder niet gebeurde.

## [0.13.0] - 2026-08-18

### Added
- **"Speel genre hardstyle af" speelt dat genre.** De spraakzoekopdracht in de auto draaide altijd de
  vrije-tekstzoekactie, en die kijkt naar artiest, album en titel -- een genre komt daar in geen van
  drieën voor, dus bleef de auto stil of landde je op een willekeurig album dat toevallig een woord
  deelde. Een uitgesproken genre draait nu dezelfde query als het bladermenu: de laatst toegevoegde
  nummers van dat genre, tot het maximum uit de instellingen, ongeacht waardering. Zeg je "sets" of
  "livesets", dan krijg je de lange opnames in plaats van de nummers. Spraakherkenning knipt en plakt
  namen, dus "hard style" en "tech house music" vinden hun genre alsnog; een genre dat de bibliotheek
  niet kent valt terug op de oude vrije-tekstzoekactie.
- **"Speel X hierna af op MuMa" zet dat nummer achter wat er speelt.** Google Assistent kent geen
  wachtrij-werkwoord voor externe muziekapps: "voeg X toe aan MuMa" wordt binnen Assistent zelf
  geweigerd en bereikt de app nooit. De enige deur die wel opengaat is een speelverzoek met vrije
  tekst, dus reist de wachtrij-instructie mee in die zin als markeerwoord ("speel X hierna af op
  MuMa", "play X next on MuMa") en wordt er in de app weer uitgehaald. Markeerwoorden tellen alleen
  aan het eind van de zin, zodat een titel als "The Next Level" heel blijft, en een zin die uit niets
  anders dan een markeerwoord bestaat valt terug op gewoon afspelen.
- **Een LMS-scan kan voortaan per batch worden aangezet.** `LmsScanTrigger` roept `startScan.view`
  aan op elke ingestelde LMS-host, bedoeld voor één keer per download-, import- of tagronde. LMS'
  incrementele scan verwerkt alleen nieuwe of gewijzigde bestanden, dus dat is goedkoop, en het laat
  LMS' eigen schema omlaag -- van uurlijks naar dagelijks -- zonder dat de bibliotheek achterloopt.
  De helper draait nog nergens mee; hij wordt aangesloten bij de uitvoering van het
  retag-invalidatie- en BPM-plan dat in deze release is vastgelegd.

### Fixed
- **De backfill-scripts vinden de database weer.** `backfill_release_dates.py` en
  `seed_scene_group_date_formats.py` lezen hun databaseparameters rechtstreeks uit de omgeving. De
  compose-stack injecteert die, maar vanuit een checkout staan ze alleen in de `.env` van de
  repository -- het seeding-script liep dus eerst de hele bibliotheek af en faalde pas daarna op het
  wegschrijven, wat de volledige run kostte. Allebei laden nu die `.env`, net als
  `scripts/library_stats.py` al deed. Een override op de commandoregel wint nog steeds.

## [0.12.2] - 2026-08-18

### Fixed
- **"Speel alles" in de auto speelt weer op volgorde.** Shuffle is plakkerige spelerstand: zette je
  hem ooit aan op de telefoon, dan bleef hij aan tot je hem zelf uitzette, en het bladermenu van
  Android Auto raakte die stand nooit aan. Een wachtrij die je in de auto startte erfde hem dus --
  precies op de ritten na een geshuffelde luisterbeurt op de telefoon, wat het willekeurig deed
  lijken. Een wachtrij die in de auto begint zet shuffle nu uit. De shuffle-knop in de auto blijft
  gewoon werken; die hutselt de wachtrij zelf door elkaar.

## [0.12.1] - 2026-08-18

### Changed
- **Het raster onthoudt de plek, nooit het album eronder.** Een wachtrij zonder lijst erachter --
  gestart vanuit Android Auto, vanuit de notificatie, of hersteld bij het opstarten -- legde het
  album vast van wat er speelde. Dat is geen plek waar je heen ging, en uit een genrelijst was het
  ronduit fout: een nummer uit Raw Hardstyle schreef de compilatie weg waarop het is uitgebracht.
  Zo'n wachtrij schrijft nu niets weg. Een albumscherm legt nog wel zijn album vast, want daar begon
  het afspelen.

### Fixed
- **Een genre-, label-, festival-, podcast- of jaarlijst wordt eindelijk als zichzelf herkend.** Elk
  bladerscherm draagt zijn tag in de filters in plaats van in een eigen argument, en de historie las
  alleen die argumenten -- dus die schermen leken bronloos en vielen door naar het album. Spelen uit
  Raw Hardstyle legt nu Raw Hardstyle vast, en spelen uit Art of Creation het label.
- **"Speel nu" op één nummer onthoudt de lijst waaruit je het speelde.** Alleen de play-knop van een
  lijst meldde het scherm erachter aan, dus één nummer uit Raw Hardstyle via het nummermenu legde de
  compilatie vast waar dat nummer toevallig op staat -- Dirty Workz in plaats van het genre.
  "Speel hierna" en "Achteraan" laten de bron van de lopende wachtrij met rust.
- **Een snelkoppeling verschijnt nu zodra je op play drukt.** Hij werd pas weggeschreven als een
  nummer scrobbelde, en dat gebeurt alleen als het uitspeelt -- dus een lijst starten en doorskippen,
  of half luisteren, liet het raster onaangeroerd. Het vullen van de wachtrij schrijft hem nu weg.
- **"Onlangs beluisterd" in de Android-app bewoog niet meer.** De lijst waar een wachtrij vandaan kwam
  werd blijvend onthouden in plaats van per wachtrij, dus het laatste bladerscherm waaruit je speelde
  bleef de bron van alles daarna -- van het beginscherm, uit zoeken, uit de notificatie, uit de auto.
  Het raster schreef steeds dezelfde snelkoppeling weg en veranderde daardoor nooit. Een bron hoort nu
  bij precies één wachtrij, en een wachtrij zonder lijst erachter legt niets vast.
- **Snelkoppelingen waren hun hoes kwijt.** Een album of afspeellijst werd opgeslagen zonder het id
  waarop de hoes hangt, dus het raster tekende een placeholder waar eerst de hoes stond. Een genre,
  festival, label of podcast heeft zelf geen hoes en leent er nu één van een nummer met die tag,
  net zoals een artiest zijn foto al leende -- één keer opzoeken per snelkoppeling, daarna bewaard.

## [0.12.0] - 2026-08-17

### Added
- **De Festivals-tab kent nu 63 festivals in plaats van 15.** Qlimax, Reverze, Ground Zero, Q-BASE,
  X-Qlusive, Thunderdome, Masters of Hardcore, Pussy Lounge en de rest zijn toegevoegd, elk met de
  schrijfwijzen waaronder ze in titels en mapnamen voorkomen. Een festival hoeft nog maar één keer
  ingevoerd te worden: waar vroeger een rij per editie nodig was voordat er überhaupt iets herkend werd,
  voegt een editie nu alleen de datum toe.
- **Livesets, warm-up mixes en podcasts worden eindelijk gelabeld.** De festivalherkenning hing alleen aan
  YouTube-downloads, waardoor juist de map met je livesets er nooit langs kwam. Hij draait nu ook op de
  generieke mappen en op SoundCloud, en kijkt naast de titel ook naar de map waarin een set staat --
  `Livesets/Qlimax 2022/` zegt vaak meer dan de tag in het bestand.
- **Radioshows en podcasts worden gelabeld, net als festivals.** Isaac's Hardstyle Sessions, Hard With
  Style, The Uptempo Tribe Podcast, Hardcore Italia: een aflevering was tot nu toe niet van een gewone
  lange mix te onderscheiden. De tagger schrijft nu een PODCAST- en PODCAST_EPISODE-tag op elke mix van
  tien minuten of langer die bij een goedgekeurde show hoort, en herkent de show ook aan de map, want
  `Podcasts/The Magic Show/2011/Podcast week 023.mp3` noemt zichzelf nergens in de bestandsnaam.
- **De showlijst wordt gevonden, niet ingetypt.** `tools/detect_podcasts.py` groepeert alles met een
  afleveringsnummer op wat er overblijft als je het nummer, de gast en de maand weglaat, en zet elke serie
  klaar ter beoordeling. Op de huidige bibliotheek vindt hij 208 series met acht of meer afleveringen.
- **Beheer > Podcasts keurt shows goed of af**, met dezelfde wit/zwart/onbekend-logica als genrecuratie.
  Eén show met meerdere namen voeg je samen: de schrijfwijzen verhuizen naar de show die je houdt, zodat
  "DJ ISAAC - HARDSTYLE SESSIONS" blijft matchen maar "Isaac's Hardstyle Sessions" in je bibliotheek staat.
  Niets wordt getagd zolang een show niet is goedgekeurd.
- **Een Podcasts-pagina in de webplayer en in de Android-app**, met per show zijn afleveringen. Beide
  lijsten komen van de PODCAST-tag, dus ze vullen zich zodra de tagger langs is geweest.
- **Het beginscherm van MuMa Mobile eindigt in twee leesbare nummerlijsten**, "Onlangs uitgebracht" en
  "Onlangs toegevoegd", elk met een "Toon meer" die de volledige lijst in dezelfde sortering opent. Een
  carrousel herken je aan de hoes, en juist het SoundCloud- en YouTube-deel van de bibliotheek heeft er
  geen: een rij blanco vierkantjes zei niets waar een regel met titel en artiest dat altijd doet.
- **Twee nieuwe instellingen onder Home**: hoeveel snelkoppelingen het raster toont (2 tot 10, standaard
  8) en hoeveel regels elke nummerlijst toont voor "Toon meer" (1 tot 10, standaard 5).

### Changed
- **"Onlangs afgespeeld" onthoudt nu waar je vandaan speelde.** De lijst vulde zich met alles wat je
  opende, dus bladeren vervuilde hem en het album van één aangetikt nummer duwde de rest eruit. Een
  snelkoppeling wordt nu pas geschreven als je op afspelen drukt, en wijst naar de lijst waar de
  wachtrij uit kwam: speel je één track uit Raw Hardstyle, dan is de snelkoppeling Raw Hardstyle.
  Aantikken draait die zoekopdracht opnieuw, dus je krijgt andere nummers uit dezelfde hoek van je
  bibliotheek in plaats van een herhaling. Shuffle-all, favorietenlijsten en gedeelde links leggen
  niets vast — daar zit geen zoekopdracht achter om opnieuw te draaien.
- **Memories is één balk in plaats van een carrousel van jaren**, met het dichtstbijzijnde jaar
  samengevat, en verdwijnt volledig op een dag waar niets in zit. Alle jaren staan nog steeds compleet
  op het Memories-scherm, één tik verderop.

### Removed
- **De sectie "Onlangs bijgewerkt" in MuMa Mobile.** Herschreven metadata is iets wat de scanner doet,
  niet iets om naar te luisteren.

### Fixed
- **Bestanden die los in Warm Up Mixes stonden werden helemaal overgeslagen.** De tagger liep alleen over
  de submappen van de generieke mappen, en in die map staat vrijwel alles los. Ze kregen dus ook geen
  genre of artiest.
- **Een nieuw label is meteen zichtbaar in plaats van pas de volgende dag.** Na een tagronde vraagt MuMa
  de muziekserver zelf om te scannen, in plaats van te wachten tot die er uit zichzelf aan toe is.
- **Een festivalnaam met een spatie te veel matchte niet meer.** Herkenning gaat nu op genormaliseerde
  tekst, dus accenten, leestekens en spaties maken niet meer uit -- en 'Rise' matcht niet langer op
  'Sunrise'.

## [0.11.0] - 2026-08-17

### Added
- **Nummers van een label krijgen nu een echte releasedatum, niet alleen een jaartal.** Bij een import
  las MuMa alleen het jaar uit de tags, waardoor alles van 2026 als één hoop door elkaar stond en niets
  van dit jaar bovenaan "recent uitgebracht" kwam. De exacte datum staat meestal al in de NFO die met de
  release meekomt, en die wordt nu uitgelezen en als originele releasedatum weggeschreven. Je kunt in de
  bibliotheek op releasedatum sorteren, en Memories kan er verjaardagen op matchen.
- **De trackkolommen in de bibliotheek zijn sorteerbaar.** Titel, BPM en releasedatum; een klik sorteert
  aflopend, nog een klik draait het om. Nummers zonder bekende datum staan altijd onderaan, in beide
  richtingen — onbekend is niet ouder dan 1970, het is er niet.

### Fixed
- **Een ripdatum maakt oude muziek niet meer jong.** De datum uit een NFO wordt alleen geaccepteerd als
  het jaar overeenkomt met het jaartal van de release zelf, dus een vinylrip uit 1995 die in 2024 is
  gerippt blijft uit 1995 staan.

## [0.10.0] - 2026-08-17

### Added
- **The address bar now describes where you are in the web player.** Screens that had no address of their
  own — listening history, favourites, an open playlist, and every tab inside Settings and Management —
  now each have one, so `/management/scanner` and `/playlist/1234` can be bookmarked, refreshed and shared.
  Visiting `/settings` or `/management` without naming a tab still reopens the tab you last used, and an
  address naming a tab that no longer exists opens that screen's first tab instead of a blank page. Back
  and forward move through the screens you visited, tab switches included. Genre and label addresses keep
  using the name, so links made before this change still work.

### Fixed
- **Refreshing on a genre or search term containing a dot no longer shows "File not found".** LMS treated
  any dot in the address as a request for a file, so a genre named `nu.jazz` returned a 404 on reload
  instead of the app. It now only treats known asset extensions that way.

- **Ratings given in the app now survive in music-management again.** The webhook that mirrors a rating
  matches the track by file path, but only knew the `/mnt/music` spelling of it. Since the media library
  was re-rooted at `/music` no lookup matched, and 202 of the 336 mirrored ratings were filed under a
  track id that no longer exists. Both roots are now recognised, in either direction.

### Security
- **LMS no longer serves files from outside its web root.** A crafted address containing `..` resolved to a
  real path on disk and was returned verbatim; such requests are now rejected with a 404.

## [0.9.3] - 2026-08-15

### Fixed

- **Every genre reported "0 nummers".** On production all 38284 rows of the `cluster` table carried
  `track_count` 0 while `track_cluster` held 1.7M links, so `getGenres` answered `songCount="0"` for
  a library that actually has 67653 Hardstyle tracks. That column is cached, and only
  `ScanStepComputeClusterStats` fills it — a step that ran solely when a scan saw changes. A scan
  that aborts after the clusters are created therefore leaves every count at zero, and each later
  scan, having nothing to do, skips the step and keeps it that way. The step now also runs when a
  cluster has tracks but still reports zero, so an interrupted scan heals itself on the next run.
- **The management tabs are reachable on a phone again.** The sidebar column is hidden below `md`
  and the mobile bottom bar has no entry for the tabs inside the management view, so the screen
  opened on whatever tab was last used with no way to leave it; settings had the same problem. Both
  sidebars are now also offered as a drawer, opened from a menu button in the top bar.

## [0.9.2] - 2026-08-15

### Fixed

- **The library scan no longer takes LMS down with it.** Every hourly scan aborted the process with
  `Sqlite3: commit transaction: FOREIGN KEY constraint failed` — 835 restarts in a day, and no scan
  ever finished: the `tracklist` table held 3 rows against 48266 playlist files. A tracklist the
  scanner builds for a playlist file has no owning user, and that was stored as the internal
  "invalid id" sentinel (-1) instead of NULL, against a foreign key that older databases still
  carry. Because the constraint is deferred, the insert passed and the commit killed the process.
- **The workers no longer leak a database connection per lookup.** Ten call sites opened a
  connection and never closed it; the importer's catalogue-ID lookup alone accounted for 841k of
  the 843k `Aborted connection` warnings MariaDB logged in 24 hours. `DatabaseConnector` now offers
  a context manager that always closes.
- **The radio's Subsonic key is passed through correctly.** The compose file used a nested default
  (`${A:-${B}}`), which the docker-compose version running in production renders as a literal
  string rather than expanding it, so the player received the text `${LMS_SUBSONIC_API_KEY}` as its
  API key. Note that radio is not fully restored by this: LMS keeps Subsonic tokens in memory only,
  so a key configured in a file cannot survive a restart. That remains open.
- **SoundCloud downloads can impersonate a browser again.** The downloader image installed yt-dlp
  without the curl-cffi extra, so every impersonation target reported as unavailable and SoundCloud
  answered with 403s.
- **A slow MusicBrainz no longer floods the log.** Lookups used a flat 5-second timeout with no
  retry, producing ~2.3k error lines a day. They now allow longer to read, retry once, and record a
  timeout as a warning.

## [0.9.1] - 2026-08-14

### Changed
- **Design documents only; no runtime code changed.** This release records two designs that were
  written but never merged: origin metadata sidecars for the downloaders and the importer, and
  navigation out of the track info modal in MuMa Mobile. The published images are identical in
  content to 0.9.0 — nothing under `services/` differs — so a deployment of this version changes
  the version string and nothing else.

## [0.9.0] - 2026-08-14

### Added
- **Failed player actions now say so.** A scrobble that never reached the server, a rating the
  server rejected, playback that would not start and a stream that failed to load all ended in the
  browser console, where nobody looks. They now appear as notifications in the top-right corner of
  the web player: errors stay until you dismiss them or reload the page, while warnings and
  confirmations clear themselves. Repeats of the same message count up instead of stacking. Only
  player errors and actions you took yourself are reported — background loads stay quiet, and the
  management tabs keep their inline status panels.

### Changed

- **The blocking alert boxes are gone from the web player.** Refreshing a track and saving the
  queue as a playlist used browser `alert()` popups, which halt the page and look nothing like the
  rest of the interface. Both now report through the notification stack.

### Fixed
- A rating the server refused is now reported as a notification rather than only being put back
  silently, and the same Subsonic status check now guards scrobbling, which was losing plays the
  way ratings were lost before 0.8.3.

## [0.8.3] - 2026-08-14

### Security

- The system API key is no longer hardcoded as a fallback in the music_manager
  routers. Resolution moved to `services/music_manager/api_key.py`, which fails
  closed when no key is configured. The key's own value still has to be rotated:
  removing it from the working tree does not unpublish the copy in git history.

### Changed

- The browse views are grouped under a collapsible Library section in the
  frontend navigation.

### Fixed
- **YouTube downloads are tagged the way SoundCloud downloads are.** `YoutubeSong` had no artist
  inference; in its place sat a hand-written title split that only fired while the artist tag still
  equalled the channel folder. YouTube's music-credit panel makes yt-dlp supply an artist of its
  own, and from that moment the split stopped happening and the artists stayed in the title. It
  also appended to the artist tag rather than replacing it, so the channel name stayed behind next
  to the real artist. YouTube now runs the same rule stack as SoundCloud, keeping only its own
  album, publisher, festival inference and channel-to-genre lookup.
- **A YouTube download is no longer tagged with the genre `Music`.** yt-dlp resolves the genre tag
  as `genre -> genres -> categories -> tags`, and the YouTube extractor sets neither of the first
  two but always sets `categories` — so ffmpeg wrote the video's YouTube category, or its keyword
  list where there was no category, and every one of them landed in the genre curation queue.
  `migrate_v7_youtube_category_genres.sql` marks the categories black and flags the YouTube tree
  for rescan, so tracks already on disk are corrected too.
- **A rating the server refused no longer looks like it was stored.** Subsonic reports its own
  errors (a throttled login, an id it cannot parse, a failed write) in the response body with HTTP
  200, and the web UI only looked at the HTTP status: the stars lit up and stayed lit while nothing
  reached `rated_track`, so the same track was still unrated in the listening history, in Favorites
  and in the file tags. The track list and the player now read the Subsonic status, put the stars
  back the way they were when the rating did not land, and log why.
- **The stars now repaint on the click that sets them.** They were painted from `track.userRating`
  on an object that is not reactive state in most views (and is rebuilt from scratch on every radio
  update), so the click stored a rating that only became visible after the list was fetched
  again — and in the player during radio, never.

## [0.8.2] - 2026-08-12

### Fixed
- **A genre in `rules_genres` is now recognised whatever its casing.** SoundCloud hands out the
  genre exactly as the uploader typed it, and the rules lookup matched on the stored spelling only:
  `uptempo` was accepted while `Uptempo`, `UPTEMPO`, `techno`, `hardcore` and `frenchcore` were all
  rejected as unknown genres, even though the row was there under a different casing. Both the
  preloaded and the database lookup now compare case-insensitively and answer with the spelling the
  table stores, or with its correction, so a single genre no longer enters the library as
  `Uptempo Hardcore` next to `uptempo`.
- **The SoundCloud genre fetcher no longer pays a full minute for a track that does not exist.** It
  paused 60 seconds after every yt-dlp call, so a deleted track (HTTP 404) and a DRM-only track cost
  as much as a real fetch, while a 403 was skipped as if nothing had happened and the next thousand
  tracks ran into the same refusal. Failures are now told apart: a permanent one waits 5 seconds, a
  refusal backs off from 5 minutes and doubles to at most an hour, and five refusals in a row end
  the pass. The end-of-run summary reports the failures per kind, and yt-dlp's multi-line complaint
  is logged as its single ERROR line.

## [0.8.1] - 2026-08-08

### Fixed
- **A track with more than one genre now offers a link per genre.** The genre column in the track
  list rendered the whole genre string as a single link, so a track tagged `hardstyle, hardcore`
  linked to a genre by that literal name — a genre that does not exist — instead of to either of
  the two. The column now links each genre on its own and keeps the separators as plain text, so it
  still reads exactly as the server sent it.

## [0.8.0] - 2026-08-07

### Added
- **MuMa Mobile gets two accent colours and a launcher icon you pick separately.** Settings →
  Appearance now offers an accent colour, MuMa green or Ultrasonic indigo, and an app icon in those
  same two colours, as two independent settings. The theme preference it replaces offered Day &
  Night, Dark and Black, all three of which resolved to the same black theme and so did nothing. The
  accent lives in the theme now rather than in 34 hardcoded resource references and 8 Kotlin call
  sites, which is what makes a second colour possible at all. Sets mode turns out to carry a second
  brand colour of its own, so that one is a theme attribute too and the pair swaps roles rather than
  leaving two near-identical blues next to each other. The launcher icon is switched by enabling one
  of two `activity-alias` entries, which is the only mechanism Android offers.

### Changed
- **The last two Ultrasonic headphones are gone.** The download and playback notification icons show
  the five-bar MuMa mark. All icon geometry is now emitted by `tools/render_branding_icons.py` from
  one description of the mark, so the green and indigo variants cannot drift apart.

## [0.7.0] - 2026-08-07

### Added
- **A severity-tagged event log replaces the flat notifications list.** Every service now writes
  `INFO`/`WARNING`/`ERROR`/`CRITICAL` events straight to a new `events` table, which is the source of
  truth; `ntfy.sh` becomes a downstream sink instead of the only place an event ever existed. The
  frontend's Notifications tab is now Logboek, with level chips, a service filter, a time window and
  search. A new `notify_topic_alerts` topic gets every `WARNING` and higher automatically, with a
  priority and tag per severity and de-duplication for repeats within five minutes, so a single
  flapping connection can't flood the phone. `GET /health` reports real database and background-thread
  status and returns 503 when degraded, instead of a hard-coded `ok`.
- **Tapping the playing track opens a track info sheet.** The MuMa Mobile player's options menu
  carried seven entries that all acted on the one playing track — go to artist, go to album, show
  metadata, lyrics, share song, refresh track and the two bookmark items — buried behind an overflow
  menu that is otherwise about the queue. Tapping the title block now opens a sheet with the cover on
  a blurred backdrop of itself, the five star rating, artist and album as rows that navigate, the
  remaining actions as buttons, and genre, track number, release date and duration underneath, with
  the technical details folded away. Rows the track cannot fill hide instead of rendering `Year: `
  with nothing after it, which the old metadata screen did.
- **The genres, labels and playlists views can be sorted and filtered.** The three collection grids
  had no controls at all: genres arrived alphabetically with everything under ten tracks silently
  dropped, labels arrived alphabetically without counts, and playlists in whatever order the server
  listed them. They now share a search box, a sort key with a direction toggle, a favourites chip and
  a live "shown of total". Genres and labels get "minimaal 10/50/100" chips in place of the hardcoded
  threshold, playlists get a visibility chip and sort on length and last change, and labels and
  playlists can be favourited the way genres already could. `getRecordLabels` answers with
  `songCount`/`albumCount`, without which labels could not be sorted or filtered by size at all.

### Fixed
- **Clicking a label filtered on the wrong thing.** `label:Kompakt: Total` was split on every colon
  and filtered on `Kompakt`, which no track carries; names are now taken whole. The genre, year and
  search filters are shared by every track list, so a genre picked on the Songs screen — or a
  leftover search term — silently narrowed the label just tapped; they are reset when a different
  track list opens. Genre and label names now go into the URL percent-encoded, so a name with a slash
  no longer parses back as a different view.
- The management screen kept polling artist-image progress after it was gone, so the requests and
  their logging outlived the screen.
- The event log tab no longer crashes on a `200` whose body is not the log payload; it shows nothing
  instead.

## [0.6.0] - 2026-08-06

### Added
- **A radio channel is a stored library filter.** Channels could only be "the whole library" or one
  genre, which is too coarse to give a station an identity — Q-dance Records and Dirty Workz both
  collapse into "hardstyle". A channel now stores any combination of label, genre, artist, length,
  year and rating, served by a new `/rest/getSongsByFilter` endpoint in LMS that exposes filtering
  the database layer already had.
- **Radio channels are managed from the management page**, behind a new `radio.manage` permission:
  create, edit, take on and off air, and preview what a filter matches — how many tracks plus a
  sample — before saving. Previewing is also what catches a label name LMS does not know.
- **The player offers a channel picker** when more than one channel is on air, labelled by what each
  one plays, and still tunes straight in when there is only one.

### Fixed
- The tagger, scanner and radio loops no longer start when `MUMA_DISABLE_BACKGROUND_WORKERS` is set,
  which keeps the radio scheduler out of the integration database it was deadlocking with.

## [0.5.5] - 2026-08-06

### Changed
- **The MuMa wordmark appears once per screen again.** The top bar carried its own mark and wordmark
  next to the profile button, right above the one the sidebar header already shows, so the branding
  read twice on every screen. The top-right copy is gone and the sidebar owns the brand.

## [0.5.4] - 2026-08-06

### Fixed
- **A broken .m4a on a read-only volume no longer fails in a confusing way.** When the tagger cannot
  read an m4a it deletes the file and moves on, but if the delete itself fails — a read-only mount, a
  permission error — the load continued into code that reads a field the failed load never set, so
  the real problem surfaced as an `AttributeError` about an internal attribute. Both outcomes now
  stop at the same place.
- **"Zie meer" in the search results opens again.** The link handed its category on without an item,
  and the code behind it read an id off that missing item, so clicking it threw and the full result
  list never appeared.
- **`BoundedTreeSet` built from an existing collection is no longer empty.** Its two element-taking
  constructors handed their contents to `TreeSet`, which adds them through the very method that
  enforces the bound — before the bound has a value. Every element was trimmed away immediately. The
  bound is now set first. Nothing in the app used those constructors, so no behaviour changed with
  it, but the class no longer contains a trap.

- **The management screen stops polling when you leave it.** It asks the server every second how far
  the artist-image fetch has got, and nothing cancelled that when the screen was torn down, so the
  requests — and the logging when they stopped being answerable — carried on for the rest of the
  session.

### Removed
- Two management components that nothing imported (`components/Sidebar.svelte` and
  `components/Login.svelte` — the app uses `ManagementSidebar.svelte`), and an unreachable
  `openArtist()` in the album view. Dropping them puts the frontend coverage figure at 82.0%, where
  it was measuring code that could never run.

## [0.5.3] - 2026-08-05

### Changed
- **The test suites now cover the parts of the product people actually touch.** The frontend went
  from 24.8% to 80.8% of statements and the Python services from 77.8% to 87.9% of production code,
  with both ratchets moved up to match (frontend 80/60/78/79, Python 92%). The frontend gained
  coverage of the login screen including the Google access-request flow, the dashboard and every
  view it routes to, the player transport, the artist and album screens, dynamic playlists, tagger
  rules, genre curation, the ListenBrainz import, access-request review, the library browser and its
  facets, and the queue actions. On the Python side `services/ml-analyzer` had no tests at all — 766
  lines at 0% — and now covers the analyzer, its maintenance scripts and the predictor.
  `trainer.py` is deliberately left uncovered: it is pandas and scikit-learn end to end, and with
  those libraries stubbed a test would assert on mocks rather than on behaviour.
- **Coverage figures no longer count generated code.** Jacoco was measuring Room's generated
  `*_Impl` classes for MuMa Mobile — 4534 of the 25331 lines it reported, about 18% of the app — so
  the figure looked worse than the hand-written code actually is. No unit test should ever target
  KSP output.

### Fixed
- **The music server's coverage report was measuring under 1% of it.** `CMAKE_UNITY_BUILD=ON` merges
  many `.cpp` files into a single translation unit, and gcov then reports against that merged file
  instead of the real sources: gcovr resolved 18 files and 453 lines of a 76 000-line codebase, so
  the reported 36.9% was a figure about almost nothing. The unity build stays on for the images that
  are shipped and is turned off for the run that measures coverage. The report now covers 686 files
  and 44 034 lines, at 38.6% — the suite was always doing more than the badge showed.

## [0.5.2] - 2026-08-05

### Changed
- **MuMa is one name carrying one mark.** The web app and the Android app are the same product on
  two screens, but they carried two names and no mark of their own: the browser tab said "MuMa
  Spotify", the app was "MuMa Mobile", and the sidebar rendered Spotify's actual logo. The name is
  now MuMa everywhere — launcher, notification channels, browser tab and user-facing strings — and
  the mark is five bars in a green disc whose top edge traces an M. A single generator derives the
  favicon, the adaptive icon layers, the round variant and all five mipmap densities from one
  source, so they cannot drift apart; the adaptive foreground scales the disc to 83% so a round or
  square mask cannot clip it, and the monochrome layer carries only the bars, since themed icons
  get one colour. `applicationId` deliberately stays `nl.teunschriks.mumamobile`, so updates keep
  landing on the existing install. Written up in
  `docs/superpowers/specs/2026-08-05-muma-brand-design.md`.

### Fixed
- **"Recently played" remembers what was played, not only what was opened.** The home grid recorded
  items opened on a browse screen, on the assumption that playing something implies having opened it
  first. That does not hold for a session driven from Android Auto, the notification or the play
  queue, so an evening of listening in the car left the grid showing whatever was last tapped by
  hand. The same rebuild had also deleted the only writer of the "Last played genres" lists while
  leaving the Android Auto browser reading them, so those two lists were permanently empty. Both are
  written again from one place: every scrobble records the played album into the home grid and its
  genres into the per-mode genre lists.

## [0.5.1] - 2026-08-05

### Fixed
- **The app can find its own updates again.** The rename to MuMa Mobile also renamed the uploaded
  APK, from `ultrasonic-vX.Y.Z-<code>.apk` to `muma-mobile-*`, but apk-hoster has no field for an
  app name — the upload carries the file and its release notes and nothing else — so it reads the
  filename prefix to decide which series a build belongs to. Installed apps ask for the series by
  name (`/api/version?apk=ultrasonic`), so 0.4.0 landed in a series nothing queries: every phone
  would have stayed on 6.8.0 and been told it was up to date. The filename prefix now lives in its
  own `APK_SERIES` setting, pinned to `ultrasonic` and independent of the app's name. Moving it
  needs two releases — first a build that asks for the new series and falls back to the old one,
  then the flip — and is written up in `docs/deployment.md`.

## [0.5.0] - 2026-08-05

The YouTube downloader finally reads the `download_type` column that has been sitting in the
database unused, so channels marked as video are fetched as video -- in the best quality YouTube
offers, not the 360p a failed merge leaves behind.

### Added
- **YouTube channels marked as video are downloaded as video, in the best quality that exists.**
  `downloads_youtube_accounts.download_type` had been in the database for years without a single
  line of code reading it, so the eight channels set to `video` were fetched as audio instead.
  A sweep now runs the audio channels first and the video channels after, asks yt-dlp for
  `bestvideo*+bestaudio` merged into mkv, and writes to `youtube_video_folder`
  (`/mnt/music/Youtube_Video`) so the library scanner never meets a video file.
- `tools/list_youtube_video_residue.py` reports the stray video files and unmerged `.fNNN`
  fragments sitting in the audio tree, with their resolution. It only reports.

### Fixed
- **A channel listed as both audio and video is no longer swept twice as audio.** The table's key
  is `(name, download_type)` but the downloader selected only `name`, so seven channels came back
  as duplicates and both copies were treated as audio.
- **The 360p downloads.** yt-dlp falls back to YouTube's one remaining progressive stream, which is
  640x360, whenever it cannot merge separate video and audio. The video pass now refuses to run
  when ffmpeg is missing rather than silently producing that, and logs the resolution of every
  video it does fetch.
- **`downloads_youtube_archive` can hold the same video twice**, once as audio and once as video.
  Its key was `video_id` alone, so whichever pass ran first would have blocked the other forever.
- `active` and `min_duration` on a YouTube account row are read at last: an inactive channel is
  skipped, and the duration floor comes from the row instead of a hardcoded 60 seconds.

## [0.4.0] - 2026-08-05

Rating 5 now means "favorite" everywhere, and the separate favorite flag is gone. This cycle also
completes the Android app's rename to MuMa Mobile.

### Added
- **Albums can be rated.** The app only ever stored a favorite flag for an album, which synced
  nowhere; albums now carry a 0-5 rating like tracks do, and the star on an album row writes
  rating 5 instead of that flag.
- `scripts/migrate_stars_to_ratings.py` turns the existing `starred_*` rows in the LMS database
  into ratings, so favorites set before this release stay visible. An explicit rating always wins
  over a star, nothing is deleted, every row is written to a JSON export, and re-running is a
  no-op.

### Changed
- **There is no separate "favorite" any more: rating 5 is what favorite means.** Two ways to say
  "I like this" could contradict each other -- a four star track that was also starred, a starred
  track with no rating -- and only the rating travelled on to the file tags. `getStarred`,
  `getAlbumList type=starred` and the `starred` attribute in Subsonic responses now read the
  ratings. The Favorites screens keep their place and simply list what is rated five stars.
- **`star`/`unstar` still work, and now reach the file tags.** They stay in the Subsonic API for
  third party clients, but set rating 5 / clear the rating. A star from such a client used to be
  dropped on the way to the tags; it no longer is.
- The favorite toggles are gone from the interfaces: the star buttons in the LMS web UI, and in
  the app the heart/star toggle in track rows, the dedicated button in the player and its overflow
  menu entry. The five star display is the only rating control left.
- **The Android app is now MuMa Mobile.** The name it shows on the launcher, in its notifications
  and in its own screens changed from "Ultrasonic" to "MuMa Mobile", the Kotlin package moved from
  `org.moire.ultrasonic` to `nl.teunschriks.mumamobile`, and the module from `services/ultrasonic`
  to `services/muma-mobile` — completing the split from the deprecated upstream Ultrasonic project.
  The app's install identity (`applicationId`) is unchanged, so the update installs in place and
  keeps all servers, settings and downloads. **Home-screen widgets must be removed and re-added
  once** — launchers store the widget's old class name, which no longer exists. Media-button
  broadcast actions, media-session custom commands and notification channel IDs deliberately keep
  their historical `org.moire.ultrasonic` identifiers, pinned by `RuntimeContractTest`, so existing
  notification settings and pending intents keep working. The Subsonic client id sent to the server
  is unchanged for the same reason.
- **The built-in server entry is now called "MuMa" instead of "LMS".** Installs that already store
  the old name keep matching it, so nobody has to re-add the server.
- CI jobs, scripts and coverage artifacts followed the module rename: `ultrasonic:check` is now
  `mobile:unit`, `ultrasonic:build-debug`/`build-release` are now `mobile:build-debug`/
  `build-release`, and the app release tag prefix changed from `ultrasonic-v*` to `muma-mobile-v*`.
  Existing tags are immutable and keep their old prefix; the version line continues unbroken.

### Fixed
- A change under `services/tests/` or `scripts/` did not run the Python test job, so a test added
  there was never executed by CI.

## [0.3.0] - 2026-08-05

An app-only cycle; the backend is unchanged. Ultrasonic moves to 6.8.0 / versionCode 259, and its
own [CHANGELOG](services/muma-mobile/CHANGELOG.md) carries the full detail.

### Added
- **The number of tracks a genre opens with is picked from the genre screen**, through a dropdown
  on the genre grid — 10, 25, 50, 100 or 500 — instead of a preference several screens away.

### Fixed
- **The rating button in Android Auto always gave one star**, whatever the track was rated before.
  Each button carries the rating it was drawn with in its `SessionCommand` extras, but a tap made
  in the car comes in over the legacy session, where media3 builds a fresh
  `SessionCommand(action, Bundle.EMPTY)` and hands the received bundle to a separate parameter — so
  the rating read as its default of 0 and every tap cycled to 1. The playing track now decides.
  See `docs/bug-reports/024-android-auto-rating-button-always-sets-one-star.md`.
- **The genre track limit in Settings did nothing**: it was stored under one preference key and
  read from another, so every genre opened with the built-in 100.

## [0.2.1] - 2026-08-03

### Fixed
- **A restart of music-manager no longer logs everybody out of the music server.** LMS sent its
  password checks through the HTTP client built for polite calls to third-party APIs like
  ListenBrainz: one request in flight at a time, retries on failure, and a 30-second freeze of the
  entire queue whenever anything went wrong. On an authentication check that combination is
  ruinous. A single connection error — which every deploy produces, because music-manager is
  recreated and gets a new address — stopped *all* authentication for thirty seconds. Every waiting
  request ran into its own ten-second timeout, and a timeout was reported to clients as "wrong
  username or password", so Ultrasonic and the web player discarded working credentials and logged
  themselves out. Their retries then kept the queue full, so each new batch of errors bought another
  thirty seconds and it never recovered on its own; only restarting the server cleared it. Password
  checks now go out directly, each independent of the others, with a two-second timeout instead of
  ten. A healthy check answers in well under a tenth of a second.
- **An unreachable login service is no longer reported as a wrong password.** It was impossible to
  tell the two apart: both came back as a plain "no". Clients take "wrong password" as final and
  wipe what they have stored, which is why a few seconds of downtime cost everyone their session.
  The two are now distinct all the way out — Subsonic clients get "authentication backend
  unavailable" rather than error 40, the Muma API answers 503 rather than 401, and the web login
  says the service cannot be reached. Nothing throws credentials away over it.
- **A rate-limited login is no longer counted as a failed one.** Being told "too many attempts" says
  nothing about whether the password was right, but it was recorded as a failed attempt anyway, so
  a throttle fed a second throttle on top of itself. LMS also ran its own login throttler in front
  of a music-manager that already limits per account — and it counted per client address, which for
  Subsonic traffic is the internal proxy hop that every user shares, so one person's typo could
  throttle everyone. That second throttler is now off for this backend; music-manager remains the
  single place where login rate limiting happens.

## [0.2.0] - 2026-08-03

### Added
- **The track list can show three lines instead of two.** Album and artist shared a single line, so
  a slightly longer title pushed both of them into an ellipsis and neither could be read.
  Settings > Appearance now offers a three-line row — title, album and artist stacked, with the
  stars, release date and duration on the right — alongside the compact two-line row, which stays
  the default and is unchanged.

### Fixed
- **The Beheer tab was hidden from admins.** The admin check calls `api/auth/verify`, which sits
  under the `/api/auth/` prefix the Muma interceptor treats as "needs no key", so the request went
  out unauthenticated: 401, an empty body, and `isAdmin` read as false for everyone. The
  interceptor now names the four credential endpoints explicitly rather than matching a prefix, and
  the visibility check re-runs on resume and after the auto-login has fetched a key, since the
  original check ran before either had happened.
- **Rotating the phone doubled the playlist.** A hundred tracks became two hundred, two hundred
  became four hundred. A configuration change closes the Koin activity scope, so the player's
  lifecycle support is rebuilt and restores the serialized session — but the playback service
  survives the rotation with the playlist still loaded, and restoring appends. The restore now
  returns early when the player already holds tracks: the serialized state exists to repopulate an
  empty player, and a live service is already the source of truth.

- **A pruned image no longer strands a production deploy half-applied.** A container whose image
  had since been removed from the host could not be recreated in place, so compose stopped and
  asked "Continue with the new image? [yN]" — a question nothing can answer over a non-interactive
  SSH session. The deploy died having already recreated most of the stack. Such containers are now
  removed before `up -d` runs, and rebuilt from the image the deploy just pulled.

### Documentation
- The README carries a functional overview of the CI/CD pipeline: which jobs run on which branch,
  and what each one gates.
- A design document for a release-candidate acceptance stack — an environment where a release
  branch can be exercised against production-like data before `muma:deploy` runs.

## [0.1.3] - 2026-08-02

### Fixed
- **Everyone was logged out again seconds after logging in.** The rate limit added to the
  authentication endpoints this cycle assumed `/api/auth/login` is a login form. It is also the
  password oracle the music server calls on *every* Subsonic request, over an internal hop that
  carries no client address — so all users shared one budget of ten calls a minute, and opening a
  home screen spent it in a second or two. Past that, the server read the refusal as "wrong
  password" and each client dutifully logged itself out. Only rejected attempts are counted now,
  and a login is counted per account instead of per caller, so browsing a library costs nothing and
  one account being guessed at cannot lock anyone else out. Guessing a password is still capped.

## [0.1.2] - 2026-08-02

### Changed
- **A track SoundCloud will not hand over no longer stops the whole downloader.** yt-dlp reports a
  subscriber-only, geo-blocked or since-deleted track as a 403, and the downloader read every one of
  those as SoundCloud pushing back: it parked the source, abandoned the remaining accounts of a
  1110-account sweep, and never marked the account as checked, so the next sweep met the same track
  and took the same 403. The counter behind that only returned to zero after a sweep that touched
  every account without a single 403 — which one permanently unavailable track makes impossible — so
  the backoff climbed to its ceiling and stayed there. Downloads stopped for two days while
  SoundCloud itself was still answering normally. A 403 is now read as what it is: individual tracks
  are written down and skipped on later sweeps, and the source is only parked on an explicit 429 or
  after several accounts in a row come back empty-handed. The backoff also decays on its own with
  time, and its ceiling drops from a day to an hour.
- **The downloader presents one consistent client to SoundCloud.** It sent a Chrome 120 user agent
  while offering cookies issued to Firefox, which is precisely the mismatch the anti-bot layer in
  front of SoundCloud looks for. It now says Firefox, matching the container the cookies come from,
  and the value is a setting rather than a constant frozen in code.
- **yt-dlp no longer ages between releases.** Its fixes for SoundCloud and YouTube changes land within
  days, but the images were only ever built during a release, so the downloader could run a yt-dlp
  older than the problem it was hitting. A weekly scheduled pipeline now rebuilds and republishes the
  downloader image from master, and the version floor no longer pins it to a single month.

### Fixed
- **Cookies are read complete rather than as of the last checkpoint.** yt-dlp copies Firefox's cookie
  database and nothing else, while Firefox writes through a log that can hold the most recent cookies
  — including the rotating one the anti-bot layer issues. The profile is now snapshotted and folded
  together before it is read, so what the downloader presents is what the browser actually holds.

## [0.1.1] - 2026-08-02

### Fixed
- **The library scanner failed on every single file.** Genre indexing, added in the previous
  cycle, read a song's genres through a method that does not exist on `BaseSong`, so each file
  raised an `AttributeError` that the scanner caught, logged and moved past. On production 1427
  of 1429 scanner log lines were this one error. The damage went further than missing genres:
  the failure happened before the media-file row was written, and the database connection
  commits as it goes, so tracks and their artists were stored while file modification times
  never were — which left every scan re-reading the entire library from scratch and the genre
  table empty. The scanner now reads genres through the method songs really have. The tests
  missed this because they described a song with a mock that answers to any method name at all;
  they now use a stub limited to the real interface, so an invented method fails in the test
  suite instead of in production.
- **A downloader container respawned every minute, forever.** The SoundCloud full-sweep worker is
  built to do one pass and exit, but was configured to be restarted whenever it stopped — which
  is exactly what it does by design. It had restarted 21 times when this was found. It is now
  left alone once its sweep is done.
- **YouTube downloads had no way to solve the site's JavaScript challenges.** The downloader image
  shipped without a JavaScript runtime, so every video logged that signature solving had failed
  and only the formats needing no challenge stayed reachable. The image now carries the solver
  scripts and Deno to run them. This clears the warnings; it does not by itself lift the
  rate-limiting YouTube is currently applying.

## [0.1.0] - 2026-08-02

### Added
- **Memories: what was released on this day, in earlier years.** The library holds release dates
  it never showed you anything with; the web interface and the Android app now open on a short row
  of them — "Today, 8 years ago" — with a full screen behind it that lists one section per year,
  each playable in one tap. Only tags carrying a complete date can say what happened on a given
  day, so a tag with just a year, or just a year and a month, never appears. A day with no exact
  match widens to three days either side rather than showing nothing, and says "this week" instead
  of "today" when it does, so the heading never claims a precision the tags do not have. The row on
  the home screen can be switched off in settings; the Memories screen itself stays where it is,
  in the web sidebar and in the Android Library tab. Served by one new LMS endpoint,
  `/rest/getMemories`, which both clients read; the device sends its own date, so a phone in
  another time zone gets its own today. Filling in the release dates that are still missing, from
  MusicBrainz or Discogs, is a separate piece of work and is not part of this.
- **Diagnostics can be sent without waiting for a crash.** Crash reporting only fired on the next
  app start, and only after the app had actually died, so the failures that leave the app running
  — a call that returns an error, a screen that stays empty — never reached the server. Settings
  now has "Send diagnostics now" under the Muma section, which uploads the current session's log
  and writes a copy to Downloads/UltrasonicLogs. It sits outside the debug category on purpose,
  because that category is hidden in release builds. Unlike the automatic report it ignores the
  "Crash detection" toggle — pressing the button is consent — and it never deletes a crash file
  that hasn't been reported yet. Manual reports are marked as such in `crash_reports`, so they
  are distinguishable from real crashes and from silent kills.

### Changed
- **The Ratings tab no longer offers a search field.** Every Library tab got the same filter bar,
  but Ratings is not a list the library grows: it is the same five cards ("4 stars and up" down to
  "1 star and up"), all of them on screen at once. Searching five visible cards is busywork, so the
  field is hidden there and stays on the tabs that do grow — genres, labels, years, festivals and
  lineups.

### Removed
- **The "MuMa Sync" screen in Ultrasonic** and its six buttons (log on, load/write tiles,
  clear tiles, load/write settings). Tiles already sync themselves through the tile editor,
  the log-on step already happens when a server is saved, and the settings backup/restore pair was a
  blunt dump of every shared preference that needed an app restart to take effect and could
  overwrite a working install with another device's state. The MuMa user ID and API key
  settings stay — they are what the rest of the app authenticates with. Along with the screen
  went the unused `POST /api/users/{id}/dynamic-playlists/sync` endpoint on the manager, which
  no client had called since the tile editor started writing playlists directly.

### Fixed
- **An artist shortcut on the home screen keeps the blank it was saved with.** The shortcuts grid
  stores whole cards, written once, at the moment the user opens something. An artist saved while
  the server had no picture for them holds an empty cover art id, and an empty id means the card
  never asks for a picture at all — so it stays grey however many pictures have arrived since.
  Such a card now has its artwork looked up and the stored copy repaired, which is one lookup per
  artist, ever. The index conversion also stored an empty string where the artist conversion
  already stored nothing, so a missing id looked like a usable one downstream; both now agree.
- **A cover art the server does not have is not re-requested on every bind.** 0.0.60 made the
  server answer with the artist's own release artwork instead of a 404, so this is now only the
  artists who have no artwork anywhere — but for those, scrolling the home screen back into view
  cost one failed request per card, every time, and the placeholder appeared only after the round
  trip. Their ids are remembered for twelve hours, per app run, and only when the server actually
  answered "not found": a timeout, a 5xx or being offline says nothing about whether the picture
  exists, and caching those would blank out artwork that is perfectly fine.

## [0.0.61] - 2026-08-02

### Added
- **The star button in Android Auto now sets a rating instead of a favourite.** It used to toggle
  the Subsonic favourite flag on and off, which left the five-point rating — the thing the rest of
  the app sorts by, filters on, and shows a five-star widget for — unreachable from the car. The
  button now cycles through six states: an empty star for no rating, then a star carrying the
  digit 1 through 5, wrapping back to empty. Favourites are unchanged on the phone; they lose only
  their car button, which keeps shuffle and repeat out of the overflow menu where they are harder
  to hit while driving.

## [0.0.60] - 2026-08-02

### Added
- **The artist page opens with the artist rather than with a list.** Tapping an artist used to
  land straight on their albums, with the name in the app bar the only thing distinguishing one
  artist from the next — even though the app already downloads and caches artist images and
  already shows the album and track counts one screen earlier, in the artist list. The page now
  starts with a header: the artist image, the name, "12 albums · 143 tracks", the years the
  discography spans, and the genres. The play-all button moved into it and queues the artist's
  tracks the same way the long-press menu's "play now" does. Artists reached through search or
  from a home screen card never went through the cache that holds the counts, so the header
  derives them from the discography on screen instead of showing nothing.
- **Labels are browsable on Android.** The filter modal could already narrow songs down to a
  record label, but nothing showed which labels the library holds — you had to know the name
  before you could filter on it. Labels now sit in the Library tabs next to Genres, fed by the
  same PUBLISHER tag the filter chip uses, and a tap opens that label's tracks.
- **The Android app speaks Sallaands and Brabants**, the same two dialects the web interface
  picked up in 0.0.59, chosen from the language menu that was already in Settings. Neither
  dialect has a language code, so they ride along on Dutch with a region no Dutch speaker has
  set: nl-BQ and nl-CW. Three other shapes were tried first and none of them survive Android's
  resource matching — a three letter code (nds-NL) and a BCP 47 variant (nl-NL-brabant) both
  fall back to the default, and any locale missing from `resourceConfigurations` is stripped
  from the APK before it ever reaches a device.

### Fixed
- **The folder selector no longer sits squeezed into one column** when an album list is switched
  to the grid layout. It was laid out as a single album-sized cell with the first two albums
  beside it; headers now span the full width of the grid.
- **Dutch is complete on Android, and English is actually English.** The Dutch resources were
  163 strings short of the English ones, and 28 strings this fork added were written in Dutch in
  the default resources — so an English-language phone showed "Artiesten", "Jaren" and
  "Goedkeuren". Both are filled in now, which the dialects depend on: Android treats nl-BQ and
  nl-CW as Dutch, so a gap in Dutch falls through to a dialect rather than to English.
- **Artists show a picture on the phone, whether or not one has been fetched for them.** An artist
  without artwork of their own is served from the artist image fetcher, and only 11762 of the
  library's 51378 artists have a picture there so far, so for the rest that request 404s and every
  client — the Ultrasonic home screen, the artist list, the web player — drew its grey placeholder.
  The server now answers such a request with artwork the artist already has: their scanned artist
  image if there is one, otherwise the cover of their earliest release. The cover art id still
  points at the fetcher, so a real artist picture takes over the moment it lands, without any
  client cache holding on to the release cover.

## [0.0.59] - 2026-08-02

### Added
- **The web interface is translated, and speaks Sallands and Brabants.** The translation layer
  landed in an earlier release but had nothing in it: two locale files holding four strings between
  them, and one of 54 components resolving its text through them. Every screen now does — 640 keys
  across the player and the management console, in English and Dutch. The interface was a mix of the
  two languages rather than one of them (the mobile navigation bar rendered "Home", "Nummers",
  "Sets", "Bieb" and "Beheer" side by side), so both files needed new text written for the strings
  that existed in only one language.
- **Sallands and Brabants**, picked from the same language menu. Lookup now walks a per-locale
  fallback chain instead of resolving a missing key straight to English, so both dialects reach
  Dutch first and their files can stay partial: 131 keys each, covering the player side, with the
  management console reading as ordinary Dutch instead of half-English. Neither dialect has a BCP 47
  tag, so both report `nl` to the browser, which is what screen readers and spell-check need.
- **Plural forms**, chosen with `Intl.PluralRules`, so counts no longer read "1 nummers". The form
  is decided by the language the text is written in rather than the active one, so Dutch reached by
  falling out of a dialect still pluralises as Dutch.

### Changed
- Sentences that were assembled from fragments are single translatable strings now, because where a
  noun sits in a sentence differs per language. Labels that lived in plain module state — sort
  options, tab lists, artist roles, scanner step names — hold translation keys, since as data they
  could not follow a language change.
- Text that originates in the backend (worker statuses, health output) is unchanged and stays
  English; translating it would mean changing what the Python services emit.

## [0.0.58] - 2026-08-01

### Added
- **Interface language setting in the web frontend.** The frontend now has a translation mechanism —
  JSON translation files per language (`services/frontend/src/lib/i18n/locales/`), a `t()` store with
  English fallback and `{name}` interpolation — plus a language picker (English/Dutch) in General
  Settings. The chosen language is stored in the per-user `frontend` app-settings blob
  (`/api/users/{id}/settings/frontend`, alongside `favoriteGenres`), so it follows the user across
  devices; a language applied from the account is not written to `localStorage`, so logging out falls
  back to this browser's own preference instead of keeping the previous user's. No backend or database
  change. Only the picker itself is translated so far — converting the remaining screens is a
  follow-up. See `docs/designs/i18n/`.
- **Android: search and sort on the Library tabs.** The Artists and Albums tabs gained a search
  field and a sort selector; artist search runs server-side over the whole library through new
  `query`/`sortBy` parameters on `getArtists.view`, which also reports `songCount` per artist.
  Albums reuse the `query` parameter `getAlbumList2.view` already accepted and gained a
  `byTrackCount` order. The genre, year, festival, lineup and rating tabs filter and sort in
  memory.

### Changed
- **Server administration moved out of the player's settings screen and into the management view.**
  The scanner (status, schedule, tag handling) and the media libraries are now management tabs of
  their own, so everything that requires an administrator lives in one place. The player's settings
  are personal settings only: general, advanced and about. The two separate scanner screens that
  both polled `getScanStatus` on their own timer are merged into a single tab that only polls while
  a scan is actually running.
- **Subsonic API tokens are issued by an administrator**, from the user detail panel in the
  management view, instead of every user minting their own in two different places. The music
  server exposes them at `/muma/api/admin/subsonic-token`, which requires Subsonic admin
  credentials.
- **The about page is written for listeners**: the running version and the release notes, without
  the developer-oriented links.
- Scrobbling to the central MuMa database is on for every user. It was a per-user toggle that the
  player's settings screen could set, which is not something individual users should opt out of.
- `store.js`'s account sync was generalised into `loadFrontendSettings`/`saveFrontendSetting`, which
  read-merge-write a single key of the `frontend` app-settings blob; `favoriteGenres` now goes through
  them and both settings are loaded in one request on login. No behaviour change for favorite genres.

### Removed
- **The "Audio (Web Player)" settings block.** Transcoding mode/format/bitrate and the ReplayGain
  settings were never read back by `getUser`, never written by `updateUser`, and never consulted by
  the player (which hardcodes its own stream parameters), so saving them silently did nothing.
- **The user administration screen in the player's settings.** It wrote straight into the music
  server's own user table, which the MuMa user sync then overwrote; the management view's user tab
  is the single place where users are managed. Its non-functional "Scrobbling enabled" checkbox
  (never read by `createUser`/`updateUser`) is gone with it.
- **The ListenBrainz import button in the player's settings.** Importing listening history is an
  administrative job and already exists, per user, in the management view's scrobble tab.

### Fixed
- An unset album sort method no longer makes the settings screen fall back to `107`, which is not a
  valid `ReleaseSortMethod` and was written back to the database on the next save.
- **`Track::getCount`/`Release::getCount` returned one row per matching entity instead of a
  single total.** Both classes' private query builders (`createQuery` in `Track.cpp` and
  `Release.cpp`) applied `GROUP BY` unconditionally, including on the aggregate `COUNT` select
  `getCount` builds, which turned its single-row result into one row per entity and made
  `fetchQuerySingleResult` throw whenever the query also needed to deduplicate joined rows (e.g. a
  keyword filter, or `Release`'s new `TrackCountDesc` sort). Both now take an explicit `aggregate`
  flag and only apply `GROUP BY` when it is false.
- **`Dockerfile-build-alpine` could produce a "passing" image with a failing test suite.** It ran
  `make test && ...;` where the trailing semicolon broke the `&&` chain, so a failing CTest suite
  no longer failed the build, and `scripts/test/lms-unit.sh` reported green regardless.
- **Android: tapping an artist opened a blank screen.** The artist list and the home screen's
  artist cards navigated to a stub fragment that had no layout and loaded no data. Both now open
  the artist's album list, the destination search and the player's "show artist" already used.


## [0.0.57] - 2026-08-01

### Fixed
- **The Android About page still linked to upstream Ultrasonic.** "Visit webpage" opened
  `ultrasonic.gitlab.io` and "Report a bug" opened `gitlab.com/ultrasonic/ultrasonic/issues`,
  neither of which has anything to do with this fork. They now point at `https://muma.example.com`
  and the project's own issue tracker at
  `https://gitlab.example.com/muma/music-management/-/issues`.

## [0.0.56] - 2026-08-01

### Fixed
- **Ultrasonic crashed as soon as Settings was opened.** `SettingsFragment` sets every list
  setting's summary to its selected entry, and `ListPreference.getSummary()` runs that summary
  through `String.format()` to substitute the entry into it. The interface size options shipped in
  0.0.55 are the first entries in the app containing a literal `%` ("100%", "90%", ... "70%"), so
  the summary became an invalid format string and binding that row threw
  `UnknownFormatConversionException: Conversion = '%'`, killing the process. The `%` is now
  escaped. It affected every install rather than only upgrades: the preference persists its default
  while the screen inflates, so the summary is applied the first time Settings is opened.
- **Robolectric could not see the app's own resources**, because `includeAndroidResources` was
  never enabled, so any test touching a real screen failed with `Resources$NotFoundException` and
  none existed. Enabling it is what made the Settings crash reproducible in a test.

## [0.0.55] - 2026-08-01

### Added
- **Radio mode (beta): one server-owned programme, any number of listeners in sync.** The server
  publishes a timeline of tracks with absolute `started_at` timestamps and a scheduler keeps it
  filled ten minutes ahead, so a channel plays with nobody listening and a late joiner lands mid-track
  at the right spot. Clients never push state: they measure their clock offset against a DB-free
  `/api/radio/time`, derive `position = serverNow - started_at`, and close drift with a hard seek
  above 3 seconds or an inaudible `playbackRate` nudge below it. Available in the web player and as a
  "Radio" entry in Android Auto, where skip and seek are removed from the player commands so the car
  greys them out. One channel (`main`, whole library) ships enabled; the schema already carries a
  `genre` per channel, so genre channels need a row rather than a migration. See `docs/radio-mode.md`.

### Fixed
- **Jam followers wiped the host's play position.** The reactive push effect ran for followers too,
  and a follower's `savePlayQueue` call omits `position`, which the server stores as `0`
  (`handleSavePlayQueueCommon` reads it as `value_or(0)`). Every follower echo therefore reset the
  host's progress to the start of the track and its `playing` flag to false — the "jumping" that made
  the old sync modes unusable. Only the host writes state now; followers still send explicit
  play/pause/next/previous commands.

- **Library Browser, replacing the Library, Advanced Library and Statistics tabs.** One view over the
  collection with facet filters for genre, label, artist, BPM range and release year that intersect,
  distributions that follow the active filter, and a header reporting how much of the current selection
  actually has BPM, genre and artist data — so a thin histogram is not mistaken for a thin collection.
- **`/api/analytics` endpoints for filtered aggregations:** summary with data coverage, genre
  distribution, BPM and release-year histograms, top artists, top labels, and artist type-ahead. The
  path names the metric and the query parameters name the scope, so an artist's BPM spread is
  `bpm-histogram?artist=X` rather than a new endpoint. A later player page can reuse them unchanged.
- **The scanner now indexes genres from file tags into `library_track_genres`.** It already read every
  file's tags for artist, label, title and duration and simply skipped genre, although
  `BaseSong.genres()` returns it — which is why LMS knew genres the management UI did not. Resolution
  goes through `GenreRulesHelper`, so approved genres index under their curated name, rejected ones are
  dropped, and genres awaiting curation index under their raw name and are grouped separately in the
  sidebar.

### Fixed
- **`/api/library/advanced` returned HTTP 500 for every request.** It selected `musical_key`, `energy`,
  `danceability`, `valence` and `popularity`, none of which exist in the database: `db_init.py` lists
  them in a `CREATE TABLE IF NOT EXISTS` that is a no-op against an existing table, and no `ALTER TABLE`
  exists anywhere. The frontend never checked `res.ok`, so that failure rendered as "no tracks found" —
  which is how a completely broken page stayed invisible. The columns are removed rather than added,
  since nothing writes them.
- **`/api/library/genres` always returned an empty list**, because it joined `rules_genres` against
  `library_track_genres`, a table with no rows. The genre sidebar was therefore always empty and the
  genre filter always matched nothing.
- **`library_track_genres` was never created on a fresh database.** Its `CREATE` names a foreign key to
  `rules_genres` but ran before that table existed, and the failure was swallowed by a debug-level
  `except`. It survived in production only because an older migration had created it.
- **The duration column in the track list always showed `-`.** The frontend rendered
  `track.duration_secs`, which the query never selected.

### Changed
- **Popular genres now count curated genres instead of machine-learning predictions**, so the figures on
  Overview change. `top_genres` previously unioned `library_track_genres` with `ml_genre`, which was
  harmless only while the first table was empty; once it has rows, a track carrying the same genre in
  its tag and its prediction would be counted twice.
- **Dynamic playlist previews match more tracks**, since their genre rules no longer fall back to
  machine-learning predictions alone. This affects the preview in the web UI only; Ultrasonic resolves
  its playlists elsewhere.

### Migration
- Run `POST /api/scanner/scan/all?force=true` once after deploying, to populate `library_track_genres`
  for the existing library. The scanner skips files whose size and modification time are unchanged, so
  without the forced run only files touched later get genres. Genre coverage in the browser header
  shows the progress; before the scan it reads 0%.

- **Android: an "Interface size" setting, defaulting to 75%.** Ultrasonic's rows and type were about
  a quarter larger than Spotify's, so noticeably less fit on screen. The layouts hardcode dp values,
  so the scale is applied by wrapping the activity's context with a reduced `densityDpi` instead of
  touching ~60 layout files. See `services/ultrasonic/ultrasonic/src/main/assets/CHANGELOG.md`.

- **The Artist Images tab is now a real image manager.** Per artist you can let it search
  automatically, upload a file, paste an image URL, remove the current image, or promote one of the
  previously fetched images to primary. Results can be filtered on all / with image / without image
  and are paged, and a new `/api/artists/manage/search` endpoint returns every matching artist —
  with or without an image — in a single call.

### Fixed
- **Searching in the Artist Images tab no longer shows an empty page.** The tab assigned any
  response body straight into its result list, so an error response (or a name containing `&` or
  `#`, which was never URL-encoded) produced a page with neither results nor a message. It now
  checks the response, reports the backend's error with a retry button, and debounces typing.
  See `docs/bug-reports/022-artist-images-tab-search-shows-nothing.md`.

- **Ultrasonic: favorite genres, shared with the web player.** Long-press a genre in Library →
  Genres to add or remove it; favorites get a star and sort above everything else. It is the same
  list the web UI keeps (`favoriteGenres` in the per-user `frontend` settings blob), so both clients
  agree, and a local copy keeps it working offline.
- **Ultrasonic: a Favorites folder in Android Auto**, holding favorite genres and the dynamic
  playlists you starred. A genre plays straight from the folder instead of asking for a year and a
  sort order first. The folder is hidden when there is nothing in it.

### Changed
- **Ultrasonic: the default tiles on Songs/Livesets are era tiles now.** The eight tiles that
  filtered on a single genre added nothing next to the genre list, which gets you the same result on
  its own. In their place three combinations the genre list cannot express in one go: Hardstyle
  Classics (Mainstream Hardstyle, 2009-2017), Millennium Hardcore (Mainstream Hardcore, 2010-2015)
  and Early Uptempo (Uptempo Hardcore, 2012-2017), each in random order. Existing installs keep the
  tiles they already have.

## [0.0.54] - 2026-08-01

### Fixed
- **`migrate_v2.sql` fought `migrate_v3` on every deploy.** It re-created the unique key on
  `rules_genres.name` that v3 deliberately drops in favour of one on `normalized_name`, so a deploy
  failed with `Duplicate entry ... for key 'name'` on rows v3 had legitimately created. It also
  shrank `name` back to `VARCHAR(100)` each time, truncating long genre names. Both statements are
  removed; v3 now owns that schema. Every migration re-runs on every deploy, so an older file is not
  history — it keeps being re-asserted.

### Added
- **A genre can now be corrected to more than one genre.** Contractions expand instead of being thrown
  away: `Upterror` becomes `Uptempo Hardcore` plus `Terror`. Targets live in the new
  `rules_genre_expansions` table and the curation page offers a multiple choice; `canonical_id` stays
  as a legacy column that the tagger no longer reads, so one place decides a rewrite instead of two.

### Fixed
- **`Hardstyle/Hardcore` was treated as a single genre.** `Tag.resplit` claims to split on `/`, but it
  only runs when `Tag.regex` changed something and `ARTIST_REGEX` never matches a slash, so composites
  arrived whole and filled the curation queue with combinations that never repeat. Genres are now split
  on `/` and each part is judged on its own. The split is genre-only — artists keep their slashes
  (`AC/DC`) — and a genre that has been decided on is never split, so approving a name that genuinely
  contains a slash protects it permanently.
- **Slash genres that only the migration approved are split automatically.** `migrate_v3` whitened every
  pre-existing row, which would otherwise have protected exactly the composites worth splitting.
  `migrate_v4_genre_expansions.sql` turns those into a rejected genre expanding into its parts, and
  leaves anything a human decided untouched.

### Added
- **Artist name analysis, as a dry run.** `ArtistNameAnalyzer` turns a raw artist string into a
  proposal — keep, rewrite, split, reject, or no answer — with the reasoning attached, and
  `tools/artist_curation_report.py` runs it over the whole artist list and prints what would happen
  without changing anything. Handles noise around a real name (`**FREE DOWNLOAD** DJ KURT`), names
  glued together (`AngerfistHeadhunter`), misspellings, and sentences a tagger rule mistook for an
  artist. An unrecognised name is never removed: real artists exist that no streaming service lists.
  Every threshold is configurable, because what counts as good enough can only be judged from a report
  over the real library. No schema, tagger or UI change yet.

### Changed
- **Artist analysis defaults, corrected by the first run over the real library.** Names are no longer
  removed for looking like a sentence: `Boaz Van De Beatz`, `We Are Loud` and `The Beholder
  (Neophyte)` are real artists that score exactly like a stray quote, so the signals are reported and
  the name is flagged instead. Splitting glued names is off by default after it took `Technotronic`
  apart into `Techno` + `Tonic`. Matching is blocked by first character and length, without which a
  51k-name run did not finish in twenty minutes.

### Fixed
- **Artists in non-Latin scripts are no longer proposed for deletion.** The letter check was
  `[A-Za-z]` and the normalisation key was `a-z0-9`, so every Cyrillic name counted as having no
  letters and collapsed to an empty key.

## [0.0.53] - 2026-08-01

### Fixed
- **The genre curation migration never reached production.** `.gitignore` ignores `*.sql`, so
  `migrate_genre_states.sql` was silently never committed and 0.0.52 ran against the old
  `rules_genres` schema: the curation page errored and the tagger quietly stopped writing genres.
  Root-level migrations are now exempt from the ignore rule, the file is committed as
  `migrate_v3_genre_states.sql`, and `scripts/deploy.sh` globs `migrate_*.sql` so its naming rule
  matches `.gitignore`'s exactly. See `docs/bug-reports/021-genre-migration-never-shipped.md`.
- **The migration no longer aborts on genres that differ only in punctuation.** Production had the
  same genre stored three times, which cannot coexist under the new unique key. It now merges them
  itself — lowest id survives, artist, label, track and correction references are repointed — and
  reports the count into the deploy log, instead of requiring a manual pre-check before an
  unattended deploy.
- **A failed database migration no longer reports a successful deploy.** The remote command ended
  with `rm`, so its exit status masked the one from `mysql`.

## [0.0.52] - 2026-08-01

### Added
- **A curation state per genre.** `rules_genres` now records whether a genre is kept (`white`),
  dropped (`black`) or still awaiting a decision (`unknown`), plus an optional correction target, so
  `uptempo` can be rewritten to `Uptempo Hardcore` while `Arts` is simply removed. Genres nobody has
  judged are counted and listed for review instead of being applied.
- **Curation API.** `GET /api/rules/genres` returns genres by state, most frequently seen first
  (`state=unknown` is the review queue), and `POST /api/rules/genres/{id}/decide` records a decision
  together with who made it, so the tagger never reverses it later.
- **Genre Curation page in the management UI.** A new tab that opens on the unjudged queue, most
  frequent genre first, and approves, rejects or corrects a genre per row. Every row states in words
  what the genre currently does to a tag, corrections can only point at an approved genre, and
  decisions on already-judged genres can be reversed from the same screen.

### Changed
- **One rule decides a genre instead of two.** `AddMissingGenreToDatabaseRule` and
  `CleanAndFilterGenreRule` are replaced by `ResolveGenreRule`, which performs a single lookup and a
  single decision per genre. Unknown genres are left on the file untouched rather than written into
  the library.

### Fixed
- **Unknown genres are no longer approved the moment they are detected.** The two rules above ran back
  to back: the first added an unknown genre to the backlog, the second accepted any genre found in
  that backlog. Every genre the tagger had ever seen therefore became valid, and the backlog only ever
  grew. Existing whitelist, ignore list and backlog entries are migrated to their equivalent state by
  `migrate_v3_genre_states.sql`.

## [0.0.51] - 2026-07-31

### Added
- **Ultrasonic: a "Log out" entry in the toolbar overflow menu.** Signing out previously meant
  clearing the app data or reinstalling. It confirms first, stops playback, clears the password,
  the MuMa API key and the stored MuMa tokens, and returns to the login screen with the username
  prefilled. Downloads stay on the device.
- **Ultrasonic: skeleton placeholders on the home screen.** Each section shows pulsing grey cards in
  the shape of the content that is loading, and swaps them for real cards on its own, so a slow
  section no longer holds up the ones that are ready. Returning to the home screen refreshes it
  without flashing skeletons over content that is already there.

### Changed
- **Ultrasonic: the home screen loads its sections concurrently.** Both library carousels fetched
  artists, albums and labels/festivals one after another, and the screen waited for every section
  before drawing anything — six sequential round trips before the first pixel. The sources now run
  in parallel and each section publishes as soon as it is ready.

### Fixed
- **Ultrasonic: a password rejected mid-session now returns to the login screen.** When the password
  was changed on the server (or an API key revoked) while the app was running, every screen failed
  with an error the user could not act on and the app never asked for credentials again. Subsonic
  error 40 now ends the session and shows the login screen with an explanation. Permission ("not
  authorized") and "not found" errors deliberately do not log anyone out.

## [0.0.50] - 2026-07-31

### Security
- **The tagger, scanner and ListenBrainz-import endpoints now require an API key.** `POST
  /api/tagger/tag/all`, `/tag/file`, `/tag/stop`, `POST /api/scanner/scan/all`, `/scan/file`,
  `POST /api/scrobbler/import/listenbrainz` and `GET /api/scrobbler/import/latest` had no
  authentication at all — anyone who could reach the API could start a full re-tag of the library,
  which rewrites tags in the actual music files. This went unnoticed because Cloudflare Access sat
  in front of `muma.example.com` externally; the moment that had to be bypassed so the mobile
  app could log in from outside the LAN, they became publicly reachable. The `/health` endpoints
  stay open for monitoring. See `docs/bug-reports/020-new-user-cannot-log-in-android.md`.

### Fixed
- **Ultrasonic login screen no longer blames the connection for a rejected password.** The welcome
  dialog already probes the server to tell an outage apart from bad credentials, but then showed
  "Could not connect to LMS" on the branch where the server *had* answered — so a wrong (or
  non-existent) account looked like a server outage. That case now says "Wrong username or password
  ... or ask the administrator for an account".
- **Ultrasonic Google Sign-In failures now name their cause on screen**, not only in logcat: the
  concrete exception class or HTTP status is shown in the error text, so a remote user's screenshot
  is enough to tell a Play Services refusal apart from an unregistered signing certificate or an
  OAuth client misconfiguration.
- **CI debug APKs are signed with the real keystore when it is available.** Previously only release
  builds got `SIGNING_STORE_FILE`, leaving debug builds signed by a throwaway keystore generated
  inside the ephemeral build container — a different certificate every build, so their SHA-1 could
  never be registered as an Android OAuth client and "Sign in with Google" could never work on a
  debug APK from apk-hoster. See `docs/bug-reports/020-new-user-cannot-log-in-android.md`.
- **Batch pacing settings were never applied**: `DownloaderService` never passed its keyword
  arguments, so `max_workers`, `burst_size`, `min_pause` and `max_pause` always sat on their
  defaults — a pause of one to five seconds between batches.
- **SoundCloud never throttled between batches**: `_throttle()` existed but was only called by the
  YouTube downloader.
- **YouTube did not recognise a 429 at all**: it fell through to the generic branch and slept
  `5 * attempt` seconds.
- **Backoff state was lost on restart**: the 403 counter lived in a module global and 429 had no
  counter at all, so a container restart resumed at full speed.
- **`POST /api/config` always failed**: it called `config_store.update_many()`, which does not exist
  on `ConfigStore`. The resulting `AttributeError` was swallowed by a broad `except` and returned as
  a 400, so saving a setting over the API could never work.
- **Ultrasonic release builds crashed on nearly every playback start.** `Converters.toStringList`,
  `MediaItem.toTrack()` and `TileStorage` built their Gson type from an anonymous Guava `TypeToken`
  subclass. Guava ships no consumer ProGuard rules, so with `android.enableR8.fullMode=true` R8
  merged away the parameterized superclass those tokens read at runtime and the constructor threw
  `IllegalArgumentException: class com.google.common.reflect.TypeCapture isn't parameterized`. It
  fired from `onTimelineChanged`/`onMediaItemTransition` and accounts for 15 of the 16 crash reports
  collected on 6.5.14 through 6.5.18. All three now deserialize through `Array<T>::class.java`,
  which needs no runtime generic signature, with keep rules for the Guava `TypeToken` hierarchy as
  a second line of defence.
- **An Ultrasonic error raised while no Activity was available took the app down.** `InfoDialog`/
  `ErrorDialog` built their `MaterialAlertDialogBuilder` in the constructor, outside the existing
  try/catch, so a context without an AppCompat theme threw instead of failing to show a dialog. The
  builder is now created lazily against a themed context, with a toast fallback. A global
  `RxJavaPlugins` error handler also stops a throw inside an RxBus subscriber from killing the
  process.
- **Android Auto kept a dead or offline `MusicService`.** The media session resolved it once at
  construction and held that instance for the process lifetime, so a server switch, a credential
  edit, or `getMusicService()` returning the offline service left Auto browsing empty lists forever
  while the phone UI worked. Auto now resolves the service per call.

### Added
- **Downloader timing is configurable from the UI**: a new *Timing* tab under
  Systeembeheer → Downloaders exposes the sweep interval, per-account cooldown, batch size,
  pauses, yt-dlp sleeps, rate limit and backoff ladders for SoundCloud, YouTube and Telegram.
  The settings live in the new `downloads_settings` table rather than in `ConfigStore`, because
  the manager and the worker containers mount different host directories for `/app/data` and so
  do not share `config.json`.
- **Self-regulating backoff that survives a restart**: a 429 now doubles a per-source multiplier
  and parks that source until a cooldown expires, both stored in `downloads_rate_state`. The
  multiplier stretches every wait time, and halves again after enough clean sweeps. The Timing tab
  shows the current multiplier, when the source wakes up and when the last 429 was, with a reset
  button. Exposed over `GET /api/downloaders/rate-state`.
- **Per-account check schedule**: `downloads_account_checks` records when each account was last
  visited, so a sweep only touches accounts past their cooldown instead of all of them every time.

### Changed
- **SoundCloud is swept far less aggressively by default**: the workers used to run
  `--repeat --sleeptime 300`, so every SoundCloud account was queried every five minutes. The
  interval now comes from the settings (default 15 minutes) and each account has its own six-hour
  cooldown on top, which is roughly 72 times less traffic before the self-regulation even starts.
  `--sleeptime` remains as an explicit override for manual runs.
- **The 403 ladder is now configurable**: the hardcoded 240 / 1800 / 10800 / 21600 / 43200 / 86400
  sequence is replaced by a geometric one with a configurable base, factor and cap
  (240 / 960 / 3840 / … by default).
- **A rate limit no longer blocks a worker thread**: SoundCloud used to `time.sleep()` for up to two
  hours inside the thread pool. The wait is now recorded in the database and the sweep ends instead.
- **Telegram reads ConfigStore** instead of `os.getenv`, and takes its concurrency and flood
  threshold from the timing settings. A Telethon flood wait is treated like a 429.

## [0.0.49] - 2026-07-31

### Added
- **Ultrasonic Beheer tab**: a fourth bottom-bar tab mirroring the web UI's management section
  (`services/frontend/src/lib/management/`), starting with Downloaders (SoundCloud accounts and
  YouTube channels), Gebruikers (list, enable, disable) and Verzoeken (approve, unapprove, reject,
  filtered by status). Like Library it is a pager, so the web UI's remaining management tabs can
  follow as pages rather than screens.
  The tab is hidden unless `/api/auth/verify` says the stored API key belongs to an admin, and stays
  hidden while that answer is pending or the check fails. That is presentation only — every endpoint
  behind it is already guarded by `require_admin()` server-side.

### Added
- **Ultrasonic Library gains four tabs**: Jaren, Festivals, Lineups and Ratings, alongside the
  existing Playlists, Genres, Artiesten, Albums and Opgeslagen. Every source already existed and was
  already used by the filter modal, so this adds no API surface. Lineup browsing in particular
  returns a capability that had been lost.

### Changed
- **Ultrasonic: in sets mode the home carousels show festivals instead of labels.** Livesets are
  festival recordings, so a record label says nothing about them.
- **Ultrasonic: the five list-shaped Library pages now share one `FilterBrowseFragment`** driven by
  a `BrowseCategory` enum, replacing `GenreListFragment`. Adding a browse dimension is now an enum
  value and a loader branch rather than a fragment.

## [0.0.48] - 2026-07-31

### Fixed
- **Ultrasonic: opening an artist from the home screen showed nothing.** `getArtistList` defaults its
  `role` parameter to `all`, so the carousels listed every artist link in the library — remixers,
  featured artists, composers — most of which have no albums of their own and therefore an empty
  detail screen. The client now asks for `role=release`.
- **Ultrasonic: opening a label from the home screen showed nothing.** `getLabelList` returned
  `db::Label` names, which come from `release_label`, while song filtering matches the PUBLISHER
  cluster — a different table fed by a different tag. The endpoint now reads the PUBLISHER cluster,
  so the names it returns are the ones filtering understands. `ClusterSortMethod` gains `AddedDesc`
  and `LastWrittenDesc`; the `LabelSortMethod` additions from 0.0.46 are removed again.
- **Ultrasonic: artist pictures on the home screen.** Artist art is keyed with
  `FileUtil.getArtistArtKey` again and requested at the large size, so it is shared with the rest of
  the app instead of being refetched under a key nothing reads. Missing artist cover art now becomes
  null at the converter instead of an empty string that looked like a usable id.

## [0.0.47] - 2026-07-31

### Added
- **Ultrasonic Library tab**: one bottom-bar tab holding every browse-by-type screen — dynamic
  playlists, genres, artists, saved playlists and albums — as swipeable pages under a tab strip.
  Adds `GenreListFragment`, the only new screen; the other four pages are the existing fragments,
  now hosted instead of navigated to.

### Fixed
- **Browsing was unreachable in 0.0.46**: the home screen rebuild removed the filter chip row, which
  was the only entry point to dynamic playlists, genres, the album list and the artist list. Since
  dynamic playlists are also created from that screen, there was no way to make one at all. The
  Library tab restores every one of them.
- **The Favorites tab showed a copy of the home screen**: it was the home screen with the favorites
  filter chip pre-selected, so removing the chips left it identical to Home. It is now its own
  screen with starred albums, starred artists and tracks rated four stars or better.

### Changed
- **Ultrasonic bottom navigation is now Home, Library and Favorieten.** Search left the bottom bar
  because the toolbar already carries a search field; playlists moved into Library.

## [0.0.46] - 2026-07-31

### Added
- **Rebuilt Ultrasonic home screen**: the Android home screen is now a Spotify-style shortcuts grid
  of the eight items you most recently opened (albums, artists, labels, static playlists and
  dynamic playlists), followed by a "Recently updated" and a "Recently added" carousel covering
  artists, labels and albums. All sections render from one generic card model and one reusable card
  component, so future sections need no new UI. Shortcuts are stored whole, so the grid renders
  instantly and offline instead of refetching every item on each visit. Adds a "Separate home
  history per mode" setting that controls whether songs and livesets keep separate histories.
- **LMS: `getLabelList` endpoint and label recency sorting**: labels can now be ordered by how
  recently their music was added to or rewritten in the library (`Label::findIds` with the new
  `AddedDesc`/`LastWrittenDesc` sort methods). `getAlbumList`/`getAlbumList2` gained a matching
  `type=updated`.

### Removed
- **Ultrasonic home screen filter chips** (Recent / Favorites / New / Genres / Playlists) and the
  old per-type "recently played" lists they drove. Genres remain browsable elsewhere in the app.

## [0.0.45] - 2026-07-30

### Added
- **Label tab and label search in the web UI**: labels are now a first-class way to browse the
  library, alongside artists and genres. Adds a Label entry to the sidebar and dashboard, lets the
  search bar match labels, and renders label hits in the search results. Backed by new Subsonic
  endpoints in the LMS server (`Browsing.cpp`/`Spotify.cpp`) so the mobile clients can use the same
  data.
- **Android crash log reporting for background playback crashes**: the app now keeps an always-on,
  disk-backed ring buffer of recent log output, marks clean playback-service shutdowns so a
  silent kill by the OS can be told apart from a normal stop, and on the next start detects a
  pending crash, combines the stacktrace and ring buffer into a single report, and uploads it. Adds
  the backend upload endpoint and the matching Muma API client call. This exists because
  background-playback crashes leave no trace the user can hand over.
- **`scripts/vw.sh`**: wrapper for on-demand password manager CLI access.

### Changed
- **Simplified Android navigation**: the nav drawer is gone; its items moved into the toolbar
  overflow menu. The bottom navigation now carries a Favorieten tab and no longer carries Downloads,
  and Bookmarks got an entry point on the Playlists screen.
- **AGENTS.md now requires asking which environment to use before querying live data**, so a
  read-only question can't silently end up pointed at production.

### Fixed
- **CI browser tests killed each other when two pipelines shared a runner**:
  `scripts/test/frontend-browser.sh` already picked free ports for the manager and LMS containers,
  but the Playwright dev server stayed hardcoded on 5174 with `--strictPort` and
  `reuseExistingServer: false`, so concurrent jobs failed with
  `Error: http://localhost:5174 is already used`. This took out the label-tab and crash-log merge
  requests and the 0.0.43 tag pipeline as false failures. The script now picks a third free port and
  exports it as `MUMA_TEST_PORT_FRONTEND`, which `playwright.config.js` uses for the base URL, the
  dev server command and the readiness URL, falling back to 5174 for local runs.
- **Ultrasonic failed to compile once crash reporting landed**: `MusicService` gained
  `uploadCrashReport()`, implemented in `RESTMusicService` and `OfflineMusicService` but not in the
  `CachedMusicService` decorator. Crash reports aren't cacheable, so it now delegates straight
  through to the wrapped service, matching `scrobble`/`star`/`saveMumaSettings`.

## [0.0.44] - 2026-07-30

### Fixed
- **`ultrasonic:build-release` was silently skippable on `release/*`**: the job had a
  `changes: - services/ultrasonic/**/*` filter, so a release branch that didn't happen to touch
  `services/ultrasonic/` would skip the official, signed Ultrasonic build+upload entirely — contrary
  to `docs/release-management.md`'s job-to-branch mapping, where `ultrasonic:build-release` is meant
  to run unconditionally on `release/*` (same as `release:build-images` and `muma:deploy`, neither of
  which has a `changes` filter). The optional, manual debug build on merge requests
  (`ultrasonic:build-debug`) was already correct and is unchanged. Removed the `changes` filter so
  the official build+upload always runs on `release/*` when the required secrets are present.

## [0.0.43] - 2026-07-30

### Added
- **Ultrasonic welcome dialog is now full-page, with a secondary "skip login" action**: previously,
  if both Google Sign-In and manual username/password login failed (e.g. server down, misconfigured
  Google OAuth client), the welcome dialog (`NavigationActivity.showWelcomeDialog()`) had no way to
  dismiss without a successful login (`setCancelable(false)`, no close affordance) - a hard lockout.
  Added a small, de-emphasized, confirmation-gated close ("X") button that switches to the app's
  existing offline mode (`ActiveServerProvider.OFFLINE_DB_ID`) instead of writing any credentials,
  so the same dialog naturally reappears on the next app start to try again. Also added an
  always-visible connectivity status line at the bottom of the dialog (reachable/unreachable/
  checking, via the existing unauthenticated `isServerReachable()` probe from `0.0.40`) so it's
  clear before even submitting anything whether a problem would be the server or the login itself.
- **App-wide offline-mode banner**: whenever the active server is the offline pseudo-server -
  whether reached via the new skip button or the existing manual "Offline" entry in the server
  selector - a banner now appears below the toolbar ("Offline mode — limited functionality. Tap to
  log in.") so degraded functionality is never silent. Tapping it reopens the welcome dialog.

### Fixed
- **Google Sign-In failures were hard to diagnose remotely**: `performWelcomeGoogleSignIn()` now
  logs the concrete exception class for Credential Manager failures and the HTTP status/body for a
  failed `/api/auth/google` call, instead of only a generic message. Investigated a report of
  Google Sign-In failing again on the release APK after previously working
  (`docs/bug-reports/019-google-signin-release-regression-external.md`) - no application code
  regression was found (every Google Sign-In code path is unchanged since `0.0.40`, and every prior
  Google Sign-In bug, 009-013, remains fixed); the likely cause is external (Google Cloud Console
  OAuth client registration or a Google Play Services behavior change on the affected device),
  which this release cannot fix directly but is now easier to confirm from device logs.
- **Ultrasonic 5-star rating hidden behind the album art on the Now Playing screen**: `current_playing.xml`
  gave the album art `ShapeableImageView` `a:elevation="12dp"` (for its Material shadow) while the sibling
  `song_rating` star row stayed at the default elevation. Android's view elevation controls Z-order
  independent of XML declaration order, so the album art always rendered on top of the rating row,
  making it impossible to tap a star. Gave the `album_art_inside` container a higher elevation (`13dp`)
  so the rating row draws above the art again. Also added a manual (opt-in) `ultrasonic:build-debug`
  pipeline rule for non-default branches, so a debug APK for a specific MR can be built and installed
  to verify a fix like this one against prod before merging.
- **Web player: mobile mini player had no rating control at all**: the 5-star rating in
  `services/frontend/src/lib/Player.svelte` only existed in the desktop layout branch; the mobile
  mini-player rendered no rating UI whatsoever. Added a compact 5-star row next to the track title/artist
  for parity with desktop.

## [0.0.42] - 2026-07-30

### Fixed
- **Re-deploy 0.0.41 after its own `muma:deploy` job failed (`bug 018`)**: `release/0.0.41`'s MR
  merged into `master` while its own, still-running full pipeline's `release:build-images` job was
  still going — because GitLab associated the MR's mergeability with a smaller, faster duplicate
  pipeline for the same commit rather than the full one. `release:back-merge-develop` then deleted
  the (already-merged) `release/0.0.41` branch as usual, so by the time the full pipeline reached
  `muma:deploy`, `git fetch`/checkout for that branch failed outright (`fatal: couldn't find remote
  ref refs/heads/release/0.0.41`) — production was never actually redeployed with 0.0.41's artist-
  images fix, even though `master`/`develop` and the `release-v0.0.41` tag were correct. No
  functional code change in this release — this is purely the automated re-deploy of 0.0.41's
  already-merged fix. See
  [docs/bug-reports/018-release-branch-deleted-before-own-deploy-prod-ran.md](docs/bug-reports/018-release-branch-deleted-before-own-deploy-prod-ran.md).

## [0.0.41] - 2026-07-30

### Fixed
- **Artist images (profile photo, similar artists, ...) rendered as a black square**: `/rest/getCoverArt`'s
  MuMa-artwork proxy (`handleGetCoverArt` in `services/music-management-server/src/libs/subsonic/impl/endpoints/MediaRetrieval.cpp`)
  only stripped a `/api` suffix from the `music-management-api-url` *fallback* config key, not from
  the primary `music-management-url` key — which is documented/used *with* a `/api` suffix. Whenever
  the primary key was set (the normal case), the resulting base URL kept its `/api` suffix, and the
  outgoing request became `.../api/api/artists/.../image` — a double-prefixed URL that failed at the
  connection level (a `502` from the proxy itself, not a `404` from MuMa). Applied the same stripping
  `MumaResource.cpp`'s constructor already does correctly, for either config key. Affects every artist
  whose artwork only exists via MuMa's cache (no native LMS artwork) — the common case. See
  [docs/bug-reports/017-getcoverart-muma-url-double-api-prefix.md](docs/bug-reports/017-getcoverart-muma-url-double-api-prefix.md).

## [0.0.40] - 2026-07-30

### Added
- **Ultrasonic welcome dialog now distinguishes "server unreachable" from "login failed"**:
  both the manual username/password submit and "Sign in with Google" previously collapsed every
  failure (a real network/server outage, wrong credentials, an expired Google OAuth client, an
  unexpected response shape, ...) into the same generic message. Added an unauthenticated
  reachability probe (`NavigationActivity.isServerReachable()`, a `/rest/ping.view` request with
  its own short 5s timeouts) that runs whenever a login attempt fails, so the dialog can now show
  a distinct "kan de server niet bereiken" message when the server truly isn't reachable, versus
  a "login mislukt" message when the server responded but the login itself didn't succeed.
- **Favorite genres now saved per user in the web player**: previously `favoriteGenres`
  (`services/frontend/src/lib/store.js`) only lived in the browser's `localStorage`, so it was lost when
  switching devices/browsers or reinstalling. Now synced to the user's account via the existing generic
  `GET/POST /api/users/{id}/settings/{app_id}` endpoints (`app_id = 'frontend'`, already used by
  Ultrasonic for its own settings backup) — no backend changes needed. Loaded automatically on login;
  a user's pre-existing local-only favorites are uploaded on first login after the update so nothing is
  lost. Logging out clears the locally-shown favorites so they aren't shown to the next browser user.
  See [docs/designs/favorite-genres/](docs/designs/favorite-genres/).

### Fixed
- **Ultrasonic's welcome-dialog login test could silently "succeed" without ever contacting the
  server**: `MusicServiceFactory.getMusicService()` falls back to `OfflineMusicService` - whose
  `ping()` is a no-op that always returns without error - whenever "Auto-switch server
  online/offline" is enabled and a `ConnectivityManager` capability check transiently/incorrectly
  reports no network. That setting defaulted to enabled before version 0.0.34, so any install from
  before that update carried it forward as `true`. The welcome dialog's login test now calls the
  new `MusicServiceFactory.getOnlineMusicService()`, which always uses the real, network-backed
  service - a first-time login/setup check's entire purpose is proving the server is reachable and
  the credentials are valid, so it must never be satisfiable by a no-op.

## [0.0.39] - 2026-07-29

### Fixed
- **`release:back-merge-develop` intermittently failed with "Branch cannot be merged"**: right
  after opening (or reusing) the automated `master` -> `develop` MR, `scripts/ci/back-merge-
  develop.sh` attempted the merge immediately, but GitLab computes an MR's `merge_status`
  asynchronously, so the merge could be rejected purely because that computation hadn't finished
  yet — not because of a real conflict. Observed on `release/0.0.38`'s `master` pipeline: MR !65
  became mergeable within a second of the failed attempt. Added a short poll loop (up to 10 x 3s)
  waiting for `detailed_merge_status == "mergeable"` before merging, plus up to 3 retries on the
  merge call itself, before falling back to leaving the MR open for manual resolution.

## [0.0.38] - 2026-07-29

### Fixed
- **A stale, already-merged-but-never-deleted `release/0.0.35` branch's delayed pipeline
  re-pushed old code as `muma/muma-tools:latest` and redeployed it to production right after
  `bug 015`'s fix went live (`bug 016`)**: `release:build-images`/`muma:deploy` trigger on any
  `release/*` branch push or pipeline run, and the repository had accumulated many old, merged
  `release/*` branches; one of them (`release/0.0.35`) had a job stuck queued on the shared
  runner that finally executed *after* the `0.0.37` fix's pipeline, overwriting `latest` with its
  stale, pre-fix checkout. Deleted `release/0.0.35` and all other already-merged stale branches,
  and made `release:back-merge-develop` (`scripts/ci/back-merge-develop.sh`) automatically delete
  the `release/*`/`hotfix/*` branch it just merged into `master`, so merged release branches can no
  longer accumulate and race a later release's build/deploy. No functional application code
  change in this release — this is purely the automated re-deploy of `bug 015`'s already-merged
  fix plus the branch-cleanup safeguard.

## [0.0.37] - 2026-07-29

### Fixed
- **`genre-processor` and `muma-soundcloud-fetcher` production containers crashed on start with
  `ModuleNotFoundError` (`bug 015`)**: an earlier refactor (commit `cb345cf79`) removed
  `services/common/settings.py` (replaced by `services.common.config_store.ConfigStore`) and moved
  `services/common/api/db_init.py` to `services/common/db_init.py`, updating all call sites under
  `services/`, but missed `tools/soundcloud_fetcher.py` and `tools/process_genres.py` — these
  `tools/` scripts aren't covered by the regular unit test suite, so the stale imports only
  surfaced as a container-runtime crash, not a CI failure. Fixed both imports and added
  `tools/test_tools_imports.py` (wired into `scripts/test/music-management-unit.sh`) to catch this
  class of regression going forward.

## [0.0.36] - 2026-07-29

### Fixed
- **Manager "Overview" tab crashed on load**: the recent-activity list's `{#each}` block was keyed
  on `item.file_path`, but `/api/system/activity` never returns that field (only `title`, `artist`,
  `timestamp`). Every row therefore shared the identical `undefined` key, and Svelte 5 throws a
  runtime error on duplicate keyed-each keys — crashing the whole Overview tab as soon as there
  were 2+ recent items (the normal case). Keyed the loop on array index instead, and guarded the
  filename fallback so it can't throw even if `file_path` is ever absent.

## [0.0.34] - 2026-07-29

### Added
- **Automated `master` -> `develop` back-merge**: previously, after a `release/*` branch was merged
  into `master`, keeping `develop` in sync required manually opening and merging a second MR from
  the release branch (or `master`) into `develop`. Added `release:back-merge-develop`
  (`scripts/ci/back-merge-develop.sh`), a new CI job that runs on `master` right after
  `release:tag` and automatically opens+merges a `master` -> `develop` MR via the GitLab API,
  reusing the existing `TAG_CREATION_TOKEN`. It's a no-op if `develop` already contains `master`'s
  tip, and leaves the MR open for manual conflict resolution if the merge can't be done
  automatically.

### Changed
- **Ultrasonic UI**: Restyled the login/welcome dialog, edit-server screen, and Google
  access-request screen to match the web frontend's `LoginPage.svelte` and
  `docs/styleguide.md`: filled pill-shaped inputs, a real "Sign in with Google" button with the
  brand G logo, a proper divider, a red error banner, and colored info/success/error status
  banners for pending/rejected/approved access requests. Also replaced a stray non-brand color
  in the filter dialog/search FAB with the app's `spotify_green` token, and aligned the nav
  drawer's item tinting with the bottom nav's existing brand colors.
- **Ultrasonic settings**: `autoSwitchOffline` now defaults to `false` instead of `true`.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`240`/`6.5.10` -> `241`/`6.5.11`).

## [0.0.33] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In selected an account in the picker but then silently returned to the
  login dialog, with no error shown (`bug 013`)**: both `NavigationActivity.performWelcomeGoogleSignIn()`
  and `EditServerFragment.handleGoogleSignInResult()` checked the credential returned by
  `CredentialManager.getCredential()` with a naive `is GoogleIdTokenCredential`. Android's Credential
  Manager never delivers third-party credential types (like Google's) as their concrete subclass
  across the IPC boundary — they always arrive as a generic `CustomCredential` (a `type` string plus
  a raw `data: Bundle`), even though `GoogleIdTokenCredential` extends `CustomCredential` in the
  `googleid` library's own class hierarchy. The cast always failed, silently discarding a
  successful account selection before the ID token was extracted and before `/api/auth/google` was
  ever called. Replaced both checks with the documented pattern
  (`credential is CustomCredential && credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL`,
  then `GoogleIdTokenCredential.createFrom(credential.data)`), with an explicit logged/user-visible
  error path for any unexpected credential type or parse failure.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`239`/`6.5.9` -> `240`/`6.5.10`).

## [0.0.32] - 2026-07-29

### Added
- **Artist face images in the web player bar**: `Player.svelte` previously rendered only track
  cover art and plain artist-name text — no artist photo, unlike `ArtistView`, `Dashboard`,
  `SearchResults`, and `StarredView`, which already fetch artist images from `music_manager` via
  the shared `getArtistImageUrl()` helper. Reused that same helper to show a small circular
  avatar next to the artist name in both the mobile mini player and the desktop player bar, using
  the primary (first) artist of the currently playing track. No backend changes were needed — the
  manager's image-fetching/caching pipeline was already working, it just wasn't wired into the
  player UI.

## [0.0.30] - 2026-07-29

### Fixed
- **Ultrasonic welcome-screen Google Sign-In succeeded but the dialog never closed, leaving the
  app stuck requiring login (`bug 012`)**: `NavigationActivity.performWelcomeGoogleSignIn()`'s
  `"ok"` branch had been copied from the manual username/password submit handler just above it,
  including a `MusicServiceFactory.getMusicService().ping()` connectivity check gating whether the
  dialog was allowed to dismiss. That gate makes sense for manual credential entry (verifying
  arbitrary user-typed input), but not for Google Sign-In, where a `status: "ok"` response from
  `/api/auth/google` is already a server-verified, guaranteed-valid credential — the same trust
  model already used by `EditServerFragment.performMumaGoogleAuth()` and the web frontend's
  `handleGoogleResponse()`, neither of which re-verifies with a ping. A transient/unrelated
  connectivity hiccup on that extra ping call could silently discard an already-successful Google
  sign-in. Removed the ping-gating; the dialog now always closes on `"ok"`, exactly like the other
  two flows.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`238`/`6.5.8` -> `239`/`6.5.9`).

## [0.0.29] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In still failed with "No Google accounts found" on a real device with
  a real Google account already signed in, even with a correct (non-placeholder)
  `GOOGLE_WEB_CLIENT_ID` (`bug 011`)**: two combined causes. First, `GetGoogleIdOption` (used by
  both `NavigationActivity.performWelcomeGoogleSignIn()` and
  `EditServerFragment.startGoogleSignIn()`), even with `setFilterByAuthorizedAccounts(false)`, only
  reliably returns a credential for an account that has already authorized this app before —
  switched both call sites to `GetSignInWithGoogleOption`, Google's dedicated option for
  not-yet-authorized/first-time sign-ins. Second, and more fundamentally, Google's Credential
  Manager backend refuses to issue any credential to a native Android app unless a separate
  **Android**-type OAuth client (package name + signing certificate SHA-1) is registered in the
  same Google Cloud project as the Web client ID — this is a manual, one-time Google Cloud Console
  step (not fixable purely in code/CI), documented in `docs/deployment.md` and
  `docs/bug-reports/011-google-signin-no-credential-real-device.md`, along with the two client
  registrations needed (one for the release keystore, one for the debug keystore).
- Corrected `docs/deployment.md` and `docs/designs/authentication/technical.md`, which previously
  (incorrectly) stated no separate Android OAuth client/SHA-1 registration was needed for
  Ultrasonic's Google Sign-In.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`237`/`6.5.7` -> `238`/`6.5.8`).

## [0.0.28] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In showed a generic network error when no Google account exists on
  the device (`bug 010`)**: `CredentialManager.getCredential()` throws typed exceptions for
  distinct failure modes, but `NavigationActivity.performWelcomeGoogleSignIn()` and
  `EditServerFragment.startGoogleSignIn()` only had a catch-all `catch (e: Exception)`, so a
  device with no Google account (e.g. an emulator used for testing) always showed the same
  "network error" message as a real backend outage. Added explicit `catch` branches for
  `GetCredentialCancellationException` (silently ignored — user-initiated cancellation) and
  `NoCredentialException` (new, specific `google_signin_no_accounts` string: "No Google accounts
  found on this device."), both ordered before the generic fallback. Also logs a `Timber.e`
  warning in both call sites whenever `BuildConfig.GOOGLE_WEB_CLIENT_ID` is still the
  `"placeholder-id"` default, making a misconfigured build immediately visible in the logs.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`236`/`6.5.6` -> `237`/`6.5.7`).

## [0.0.27] - 2026-07-29

### Fixed
- **Ultrasonic welcome-screen "Sign in with Google" always failed with a network error
  (`bug 009`)**: the button added in `0.0.25` reused the app's shared, Koin-injected
  `SubsonicAPIClient.mumaApi`, which on a fresh install (before any server had been configured)
  was still built against the offline/`localhost` fallback server, so the Google auth request
  never reached the real backend. `NavigationActivity.performWelcomeGoogleSignIn()` now builds a
  dedicated Muma API client targeting the fixed production server address directly; extracted the
  Muma base-URL derivation into a reusable `SubsonicAPIClient.mumaBaseUrlFor()` so both call sites
  stay consistent.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`235`/`6.5.5` -> `236`/`6.5.6`).

## [0.0.25] - 2026-07-28

> **Two Ultrasonic (Android) fixes, requested together: the default server was still pointing at
> the retired "alpha" test instance, and the "Sign in with Google" option was missing from the
> very first login screen users see on a fresh install.**

### Changed
- **Default server is now `music.example.com`**: the separate "alpha" server entry (already
  retired at the infrastructure level, see `docs/deployment.md`'s "production-lms-consolidation")
  has been removed from Ultrasonic's static server list; there is now exactly one, fixed
  production server. Adjusted the (previously hard-coded) debug-build server selection, the
  "offline" pseudo-server's list index, and updated `docs/architecture.md`/`docs/OVERVIEW.md`
  which still described a live Alpha instance.
- **"Sign in with Google" is now available on the very first login screen** (the welcome dialog
  shown on a fresh install / after a full logout), not just from deep inside the server-edit
  screen — this was the actual requirement: a first-time user must be able to choose Google login
  immediately, without first setting up a username/password server entry. The new button reuses
  the exact same Credential Manager flow, response handling (nested `user`/`api_key` fields,
  access-request navigation for not-yet-linked accounts) and Subsonic-credential-population logic
  already fixed for the in-app flow in `0.0.23`.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`234`/`6.5.4` -> `235`/`6.5.5`).

## [0.0.23] - 2026-07-28

> **Ultrasonic (Android) now supports "Sign in with Google", functionally equivalent to the web frontend.**
> A native Credential Manager-based Google Sign-In flow already existed in the Ultrasonic codebase (button,
> access-request UX, token handling), but had two bugs that meant it could never actually work end-to-end.

### Fixed
- **Ultrasonic's `MumaAuthResponse` used a stale, flat response shape**: `/api/auth/google`/`/api/auth/refresh`
  return account fields nested under `user` (per the `0.0.4` fix to `/api/auth/login`/`/api/auth/google`), but
  the Android DTO still declared `id`/`username`/`display_name`/etc. as top-level fields, so they always
  deserialized as `null` after a successful Google sign-in. Added a `MumaAuthUser` nested type matching the
  real backend contract.
- **Ultrasonic never populated Subsonic/LMS credentials after a Google sign-in** (the exact same class of bug
  fixed for the web frontend in `0.0.6`): `EditServerFragment.performMumaGoogleAuth()`'s `"ok"` branch stored
  the MuMa access/refresh token but never wrote a username/password into the server's Subsonic fields, so
  streaming/library calls (and every other Subsonic request) stayed unauthenticated after a Google login. Now
  mirrors the web frontend exactly: writes `result.user.username`/`api_key` into `userNameEditText`/
  `passwordEditText`/`ServerSetting.userName`/`.password`, relying on the same `api_key`-as-password fallback
  in `/api/auth/login`.
- **Wired up the missing `GOOGLE_WEB_CLIENT_ID` build config value in CI**: the app's Google Sign-In flow
  already read `BuildConfig.GOOGLE_WEB_CLIENT_ID` (intended to equal the web's `GOOGLE_CLIENT_ID`), but no CI
  job ever provided a real value, so every CI-built APK shipped with the `build.gradle` default
  `"placeholder-id"`, making Google Sign-In silently non-functional. `scripts/ci/ultrasonic-build-upload.sh`
  now extracts `GOOGLE_CLIENT_ID` from the existing `PROD_ENV_FILE` CI/CD variable and passes it through — no
  new secret or Android-specific OAuth client registration required, since the Android flow reuses the web
  client ID as its Credential Manager `serverClientId` by design.
- Updated `docs/designs/authentication/technical.md`'s Cross-App Impact section, which incorrectly stated
  Ultrasonic was unaffected by the Google/Subsonic-credential-forwarding requirement.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`233`/`6.5.3` -> `234`/`6.5.4`).

## [0.0.21] - 2026-07-28

> **Automated the Ultrasonic Android release APK build and publish flow, end to end.** This CI/CD automation already existed in the codebase from earlier work, but had never actually produced a real signed release: the original signing keystore could no longer be located anywhere, so official release APKs were never built by CI before.

### Added
- **Ultrasonic release APK now built and published entirely by CI**: generated a brand-new, dedicated signing keystore (the original could not be recovered) and configured it, together with the `apk-hoster` upload credentials, as GitLab CI/CD variables. `ultrasonic:build-release` now runs automatically on every `release/*` pipeline, builds a signed APK, and uploads it to `https://apk.example.com` alongside `muma:deploy` - no manual local build/upload is needed anymore.
- **Fixed `SIGNING_STORE_FILE` handling**: `scripts/ci/ultrasonic-build-upload.sh` now base64-decodes `SIGNING_STORE_FILE` before use, since GitLab CI/CD variables (even file-type ones) are transmitted as text and can't reliably carry raw binary `.jks` bytes; documented the required `base64 -w0` encoding in `docs/deployment.md`.
- **Clean slate on `apk-hoster`**: removed all previously, manually-published APKs (and their DB records) from `apk-hoster`, since none of them can be validly updated-from once we move to CI-built, newly-signed releases.
- Removed the stale, unusable `services/ultrasonic/ultrasonic-keystore.enc` (an encrypted backup with no known password/decryption method) from the repository.
- **Fixed `ultrasonic:build-release` always failing on `publish.sh`**: `services/ultrasonic/dist` was a machine-specific symlink (`-> /mnt/user/ultrasonic-builds`) that had accidentally been committed to the repository; `mkdir -p dist` fails with `File exists` when `dist` already exists as a (dangling, in CI) symlink, so every CI build of Ultrasonic was doomed to fail at the publish step regardless of signing. Removed the symlink from the repository (`dist/` is already gitignored for local use).
- Bumped Ultrasonic's own `versionCode`/`versionName` (`232`/`6.5.2` -> `233`/`6.5.3`) to mark this as the first official, CI-built and signed release.

### ⚠️ Breaking
- **The Android app's signing key changed.** Anyone who previously installed a manually-built signed release APK (e.g. `v6.5.2-214`) must uninstall it before installing this or any future release, since Android rejects updates signed with a different key and there is no way to keep the old key.

## [0.0.20] - 2026-07-28

> **Continued production log sweep uncovered the `importer_worker` logging the same ~15+ misleading "OS error: check disk space/filesystem" lines on every single import cycle**, for release folders that had actually already been imported successfully before.

### Fixed
- **Importer duplicate folders stuck in `__TODO` forever (`bug 008`)**: `Mover._move_folder()` already handled the "already imported" conflict via `except FileExistsError`, but `shutil.move()` raises `shutil.Error` (not `FileExistsError`) when the destination directory already contains an identically-named entry - this was silently swallowed by the generic `except OSError` branch, mislabeled as a disk/filesystem error, and never cleaned up the duplicate source folder. Now `shutil.Error` is treated identically to `FileExistsError`: the duplicate source is removed so it stops being retried and re-logged as an error on every cycle. Genuine `OSError`s (e.g. actual disk-full) are unaffected.

## [0.0.19] - 2026-07-28

> **Production log sweep uncovered the `telegram_worker` crashing on startup** while loading its `.session` file, and a second, deeper bug that had silently prevented this exact fix from ever reaching production despite a fully green release pipeline.

### Fixed
- **Telegram worker session schema mismatch (`bug 007`)**: `docker/Dockerfile.telegram` ran an unpinned `pip install telethon` in addition to the pinned version from `requirements.txt`, so different rebuilds could install different `telethon` releases. `telethon` changed its session SQLite schema (added a `tmp_auth_key` column) starting with `1.43.0`; an older rebuild could no longer read a `.session` file a newer rebuild had upgraded. Pinned `telethon~=1.44.0` in `requirements.txt` (matching the schema already on disk) and removed the redundant unpinned install so the image always uses a single, reproducible version.
- **`release:build-images` never covered background worker images (`bug 007`)**: `scripts/ci/build-and-push-images.sh` only ever built/pushed `music-manager` and `lms`; `muma-base`, `muma-downloader`, `muma-telegram`, `muma-importer`, and `muma-tools` were never rebuilt or pushed by CI, so `muma:deploy`'s `docker compose pull` kept re-pulling stale, manually-pushed images for every background worker — the telegram fix above went through a fully green `release/*` pipeline including `muma:deploy` without actually reaching production. Extended the script to build and push all five of these images on every `release/*` pipeline.

## [0.0.18] - 2026-07-28

> **The "Artist Images" manager tab was permanently stuck at "0 / 0 artiesten"** with a non-functional search and rescan, even though the artist/image data itself was correctly populated. Root cause: a reverse-proxy routing bug, not a data problem.

### Fixed
- **Artist Images tab always showing 0 / 0 artists (`bug 006`)**: LMS's reverse-proxy `MumaResource.cpp` intercepted every `/api/artists/*` request before it could reach the generic MuMa pass-through proxy, but only correctly implemented two shapes (`.../image` and a plain numeric artist ID for the player's own genre lookup); every other path used by the manager UI (`/images/stats`, `/search`, `/search-all`, `/fetch-progress`, `/{id}/fetch-image`) was rejected with `400 Invalid artist ID` before ever reaching `music-manager`. Narrowed the interception to only those two shapes; everything else now correctly falls through to the generic proxy.

## [0.0.17] - 2026-07-28

> **Fixed a production outage** where every login (username/password and delegated Google auth) crashed with `no such column: u.password_salt`. Root cause: a maintenance sync in `music-manager` dropped the player's real, persistent `user` table (based on an incorrect "it's volatile" assumption), racing with an incomplete fallback table-creation statement in the player itself.

### Fixed
- **`music-manager` LMS DB sync (`bug 005`)**: removed the destructive `DROP TABLE IF EXISTS user, auth_token, ui_state` from `sync_single_server_db()`; `user` is real, persistent state the player reads/writes directly (unlike `auth_token`/`ui_state`, which only ever exist in the player's private in-memory schema and were never actually reachable from this code path anyway).
- **Player schema fallback (`bug 005`)**: `Session::createIndexesIfNeeded()`'s raw-SQL `CREATE TABLE IF NOT EXISTS user` fallback was missing the `password_salt`/`password_hash` legacy columns the ORM mapping requires; added them so this fallback can no longer produce an incompatible schema.
- **Production**: repaired the live database directly (added the missing columns, restarted the player) ahead of this release to restore service immediately; documented in `docs/bug-reports/005-lms-user-table-corruption.md`.

## [0.0.16] - 2026-07-28

> **Fixed artist images not showing in the manager tab (and consequently in the player's Artists view).** Two independent bugs found and fixed: an unauthenticated image request in the manager UI, and a production deployment path mismatch that silently broke the LMS DB sync.

### Fixed
- **Manager tab artist images (`bug 004`)**: `ArtistImagesTab.svelte` requested artist images without any authentication, so every request was rejected with `401 Unauthorized`; the manager's API key is now passed along as an `apiKey` query parameter, matching how other authenticated image requests work.
- **LMS DB sync path mismatch (`bug 004`, production deployment)**: `docker/docker-compose.yml` mounted `music-manager`'s view of the `lms`/`alpha-lms` stacks' native databases (used to sync users/playlists and push artist image references) from a path under this stack's own `HOST_DATA_PATH` that never actually existed on production; it now defaults to the real `lms`/`alpha-lms` stacks' own data directories (`LMS_DATA_PATH`/`ALPHA_LMS_DATA_PATH`, overridable if needed).

## [0.0.15] - 2026-07-28

> **Configured home page "alles tonen" buttons to correctly redirect to their respective tabs with view mode switches.** Release Radar redirects to Release Radar, Songs redirects to songs (with songs view mode active), and Sets redirects to sets (with sets view mode active).

### Changed
- **Home page "alles tonen" buttons (`Dashboard.svelte`)**:
  - **Release Radar**: redirects to the Release Radar tab (`activeView = 'radar'`).
  - **Songs**: sets the view mode to songs and redirects to the songs tab (`viewMode.set('songs'); activeView = 'songs'`).
  - **Sets**: sets the view mode to sets and redirects to the sets tab (`viewMode.set('sets'); activeView = 'sets'`).

## [0.0.14] - 2026-07-28

> **Removed redundant "MuMa Beheer" button from the profile dropdown menu.** Streamlined navigation by relying solely on the persistent sidebar player/management toggle.

### Changed
- **Profile menu (`ProfileButton.svelte`)**: removed the "MuMa Beheer" menu item since system management is already fully accessible via the sidebar header toggle.

## [0.0.13] - 2026-07-28

> **Fixed popular genres statistics semicolon delimiter aggregation and artist image background fetching.** Resolved bug 002 (stats top_genres splitting compound semicolon-delimited genres correctly) and bug 003 (background artist image fetching selecting all missing primary images without image_status filtering bottlenecks).

### Fixed
- **Popular genres semicolon delimiter (`bug 002`)**: updated statistics top-genres aggregation (`stats.py`) to split compound genre strings separated by semicolons (`;` / `,`), trim whitespace, and count individual subgenres accurately.
- **Artist image fetching (`bug 003`)**: updated `run_fetch_missing()` (`artist_images.py`) to process all artists with missing primary images (`primary_image_id IS NULL`) regardless of previous `image_status`, ensuring reliable background and manual fetching of artist images.

## [0.0.12] - 2026-07-28

> **Implemented structured bug reporting workflow and resolved artist image fetch-progress reporting.** Established 2-step bug report markdown files under `docs/bug-reports/` and documented the workflow in `AGENTS.md`.

### Added / Changed
- **Structured Bug Reports (`docs/bug-reports/00#-<title>.md`)**: Added template format (`title`, `status`, `reported problem`, `Possible reason`, `solution`) and updated `AGENTS.md`.
- **Artist Image Fetch Progress**: Ensured progress endpoints handle background fetch statuses cleanly.

## [0.0.9] - 2026-07-28

> **Minor UI cleanups in the sidebar and profile menu.** Removed the legacy UI link, integrated all library sections directly into the main sidebar menu, and removed the redundant "Systeembeheer" item.

### Changed
- **Removed legacy UI button**: removed the "Oude UI (Legacy)" link from the profile dropdown menu in `ProfileButton.svelte`.
- **Consolidated library navigation**: moved all library items (playlists, artists, albums, genres, history, starred) directly into the main sidebar menu in `Sidebar.svelte` with appropriate icons, and removed the separate "JOUW BIBLIOTHEEK" section header.
- **Removed redundant "Systeembeheer" sidebar item**: removed the "Systeembeheer" entry from the sidebar since the play/management toggle in the header already provides this capability.

## [0.0.8] - 2026-07-28

> **Logging out after logging in with Google Auth (or MuMa session) no longer leaves session state behind.** Previously, `handleLogout` only reset `credentials` and cleared `lms_active_view`, leaving `mumaSessionActive`, `mumaApiKey`, `mumaRefreshToken`, `userPermissions`, and `mumaUser` (and their localStorage counterparts) intact. This caused unauthenticated users logging out to remain stuck as 'Gebruiker' with no music access.

### Fixed
- **Thorough logout session cleanup**: `handleLogout` (`ProfileButton.svelte`) now clears all session stores and localStorage entries (`mumaApiKey`, `mumaRefreshToken`, `mumaSessionActive`, `userPermissions`, `mumaUser`) alongside `credentials`, ensuring a clean slate upon logout.

## [0.0.7] - 2026-07-28

> **The login modal was detached into a dedicated full-screen login page, and unauthenticated users are now always redirected there.** Previously, unauthenticated users saw the main music app layout with a floating modal overlay on top; now, logging out or visiting the app without a valid session presents a clean, full-screen dedicated login page (`LoginPage.svelte`) at `/login` and redirects all non-authenticated navigation there.

### Added / Changed
- **Dedicated full-screen login page**: refactored `AuthOverlay.svelte` into `LoginPage.svelte` (`services/frontend/src/lib/LoginPage.svelte`), removing the floating modal overlay.
- **Mandatory login redirection**: `App.svelte` now strictly checks session state (`!$credentials.username && !$mumaSessionActive`), rendering the login page and enforcing URL redirection to `/login` whenever the user is not logged in.

## [0.0.6] - 2026-07-27

> **A Google-authenticated user was logged in as "Gebruiker" and could not see any music.** Google
> Sign-In correctly authenticated against `music-manager` (permissions, admin badge, etc.), but the
> frontend's `credentials` (username/password) store -- which every Subsonic call (`getGenres`,
> albums, streaming, ...) and the profile display name are derived from -- was never populated after
> a Google login, since a Google sign-in never learns the account's real password.

### Fixed
- **Google-signed-in users saw "Gebruiker" and no music at all (`getGenres` failing with "Required
  parameter 'c' is missing")**: `AuthOverlay.svelte`'s `handleGoogleResponse` only ever set
  `mumaUser`/`userPermissions`/`mumaApiKey`, never the `credentials` store that `authParams`
  (and therefore every Subsonic/LMS REST call across the app) and `ProfileButton`'s displayed
  username are derived from -- so a Google-authenticated session had no way to actually talk to
  Subsonic at all. `POST /api/auth/login` now also accepts a user's own `api_key` as a valid
  `password` (in addition to the real, bcrypt-hashed password), and `handleGoogleResponse` uses
  that to populate `credentials` with `{username: user.username, password: api_key}` right after a
  successful Google login -- restoring the user's real username in the UI and making all Subsonic
  calls (and, through LMS's `MusicManagementPasswordService`, Subsonic streaming itself) work
  exactly the same regardless of which login method was used, per the linked-account requirement
  from 0.0.3/0.0.5.

## [0.0.5] - 2026-07-27

> **The "Sign in with Google" button disappeared from production again, and the server would have
> silently accepted a Google ID token from ANY Google OAuth client, not just ours.** Root cause: the
> `GOOGLE_CLIENT_ID` (backend) and `VITE_GOOGLE_CLIENT_ID` (frontend build-arg) CI/CD variables were never
> actually populated in `PROD_ENV_FILE`/`PROD_ENV_FILE_LMS` -- they were only ever set directly on the
> production host, outside of the CI/CD pipeline, so the first CI-driven rebuild after 0.0.2 wiped them out.

### Fixed
- **Google Sign-In button missing in production, username/password-only login shown**: `VITE_GOOGLE_CLIENT_ID`
  was empty when the `lms` image's frontend bundle was built by `release:build-images`, so Vite's dead-code
  elimination stripped the entire `if (GOOGLE_CLIENT_ID) { ... }` branch in `AuthOverlay.svelte` (including
  the Google Identity Services script load and the `#googleBtn` render call) out of the production bundle.
  The `PROD_ENV_FILE_LMS` CI/CD variable now includes `VITE_GOOGLE_CLIENT_ID`, matching the value already
  configured directly on Google Cloud Console for this app.
- **Google login would have silently accepted a token issued for a *different* Google OAuth client**:
  `GOOGLE_CLIENT_ID` was empty for the same reason, and `google.oauth2.id_token.verify_oauth2_token()`
  silently skips its `aud` (audience) check entirely when `audience=None` -- so the backend was verifying
  only the token's signature and issuer, not that it was actually issued for *our* app.
  `_verify_google_id_token()` (`services/music_manager/routers/user_requests.py`) now raises a `500` with a
  clear message instead of degrading into that unauthenticated-by-omission state, and `PROD_ENV_FILE` now
  includes `GOOGLE_CLIENT_ID` too.
- Both username/password (Subsonic) login and Google Sign-In already resolved to the exact same underlying
  `User` row (see 0.0.3's "Merge duplicate user accounts" / "Link a Google access request to an existing
  account"); this fix restores that both methods are actually *available* on the login screen again, with
  identical resulting permissions/session regardless of which one was used.
- **The LMS `/api/...` proxy (`MumaResource`) collapsed every non-`200` response from MuMa into a generic
  `502 Bad Gateway`**, discarding the real status code and error body MuMa returned (e.g. `401 Invalid
  username or password`, `404 Track not found`). Root cause: `core::http::SendQueue` only ever invoked
  `onSuccessFunc` for a `200` response and routed everything else through `onFailureFunc` (which every proxy
  call in `MumaResource` hard-codes to `502`) — appropriate for the client's other, non-proxy callers (which
  only care "worked" vs. "didn't"), but wrong for a reverse proxy, where the exact upstream status/body must
  reach the original caller. Added an opt-in `ClientRequestParameters::treatAnyStatusAsSuccess` flag (default
  `false`, so every existing caller is unaffected) and set it on all of `MumaResource`'s raw pass-through
  proxy calls (generic `/api/*` GET/POST/PUT/DELETE, artist image, track refresh, per-app user settings).
- **Added a `release:check-secrets` CI job** (`scripts/ci/check-required-secrets.sh`) that fails a
  `release/*` pipeline immediately, before any image is built, if `GOOGLE_CLIENT_ID`
  (`PROD_ENV_FILE`) or `VITE_GOOGLE_CLIENT_ID` (`PROD_ENV_FILE_LMS`) is missing or empty — the actual root
  cause of the button disappearing again was an unrelated edit to one of those CI/CD variables silently
  dropping this key, with nothing in the pipeline noticing. See `docs/deployment.md` and `AGENTS.md`
  ("Testing & Stability") for the policy: this job's pass/fail result is a hard requirement for a release,
  the same as any other check in this list, even though GitLab itself has no way to enforce it structurally.

## [0.0.4] - 2026-07-27

### Fixed
- **A successful Google login could still show "Kon geen verbinding maken met de Google login API"**:
  `POST /api/auth/google` (and `/api/auth/login`, `/api/auth/refresh`) returned the account fields spread
  directly onto the top-level response object instead of nested under a `user` key, while
  `AuthOverlay.svelte` (and every other frontend caller) reads `data.user.permissions`/`data.user` — matching
  what `/api/auth/verify` already returns. That mismatch made `data.user` `undefined`, throwing inside the
  `try` block right after a `200 OK` response and landing in the generic connection-error `catch`, even
  though the login itself had actually succeeded server-side (the user was left stuck on the login screen
  despite the account being valid and linked). `login`, `refresh_access_token`
  (`services/music_manager/routers/users.py`) and `google_login`
  (`services/music_manager/routers/user_requests.py`) now all return `{status: "ok", user: {...}, api_key,
  access_token, refresh_token}`, matching the documented contract in
  `docs/designs/authentication/technical.md`.
- **Google Sign-In popup could silently fail with "Cross-Origin-Opener-Policy policy would block the
  window.postMessage call."**: no response served by the LMS reverse proxy set a `Cross-Origin-Opener-Policy`
  header at all, which some browsers treat as reason to sever the window reference to Google's Sign-In
  popup, breaking the postMessage-based token hand-off back to `AuthOverlay.svelte` before the ID token
  ever reaches `/api/auth/google`. `services/music-management-server/nginx/reverse-proxy.conf` now sends
  `Cross-Origin-Opener-Policy: same-origin-allow-popups`, which keeps same-origin window isolation while
  explicitly allowing the trusted Google popup to keep talking back to the page.

## [0.0.3] - 2026-07-26

> **Google Sign-In is now fully wired up end-to-end: the button actually renders, the login it produces
> actually works, and duplicate accounts can be cleaned up.** The frontend/backend code for "Sign in with
> Google" already existed, but the `VITE_GOOGLE_CLIENT_ID` build-arg was never passed to any of the three
> places that build the `lms` image (so the button never rendered), the LMS proxy layer blocked the
> Google auth endpoints and swapped every caller's identity for a generic one (so logins that did render
> failed with `401` and admins lost their management buttons), and there was no way to merge an account
> created via a Google access request into an already-existing local/Subsonic account for the same person.

### Added
- **Google Sign-In build wiring**: `build.sh`, `services/music-management-server/scripts/build.sh`, and
  `scripts/ci/build-and-push-images.sh` now all pass `--build-arg VITE_GOOGLE_CLIENT_ID=...` when building
  the `lms` image, sourced from a new `VITE_GOOGLE_CLIENT_ID` entry in
  `services/music-management-server/.env` (mirroring the backend's existing `GOOGLE_CLIENT_ID`). Documented
  in a new "Google Sign-In setup" subsection of `docs/deployment.md`.
- **Merge duplicate user accounts**: new `POST /api/users/{id}/merge` endpoint (permission `users.merge`)
  moves everything owned by a secondary account (login identities, sessions, dynamic playlists, per-app
  settings, ListenBrainz link, ratings and scrobble history) onto the primary account and then deletes the
  secondary account. Conflicts on a shared unique key are resolved by keeping the primary account's
  existing data. Exposed in the "Beheer" tab as an "Accounts samenvoegen" panel.
- **Link a Google access request to an existing account**: approving a pending access request
  (`POST /api/user-requests/{id}/approve`) now accepts an optional `link_user_id`, which links the Google
  identity to that account instead of always creating a brand-new one — preventing this kind of duplicate
  from happening again.

### Fixed
- **`/api/auth/google` / `/api/auth/access-request` / `/api/auth/setup*` were never reachable**: the LMS
  proxy (`MumaResource::handleRequest`) required an already-authenticated caller for every endpoint, which
  made it impossible for a brand-new Google identity (which by definition has no credentials yet) to ever
  call the very endpoints meant to grant it access. These are now explicitly treated as public,
  unauthenticated pass-throughs, exactly like the existing `/api/auth/login`.
- **Caller identity was discarded on every proxied request**: `MumaResource` always forwarded the
  server-wide `MUSIC_MANAGEMENT_API_KEY` to MuMa instead of the caller's own `X-API-Key`, so MuMa saw every
  request (Subsonic or Google-authenticated) as a generic, permission-less "system" caller rather than the
  actual logged-in user. The caller's own key is now forwarded first, falling back to the system key only
  when the caller didn't send one.
- **Frontend never recognized the "system" identity as an admin**: because Subsonic admins authenticate via
  the shared system key (which MuMa itself always grants full access to), the "Beheer" tab's
  `hasPermission()` checks (gating "add user", "delete user", role changes, ...) always evaluated to
  `false` for them, hiding those actions even for a real admin. The frontend now mirrors MuMa's own "system
  key = full access" rule.
- **`isAdmin` never accounted for a Google-authenticated admin's RBAC role**, and was never refreshed from
  a persisted session after a page reload — both are now covered so the "Beheer" nav entry and page gating
  work the same regardless of login method.
- **Deleting a user could fail with a generic, unhelpful error**: `DELETE /api/users/{id}` now explicitly
  cleans up dependent rows (login identities, sessions, dynamic playlists, per-app settings, ListenBrainz
  link) before deleting the account, protects the last remaining admin account from being deleted, and
  returns a clear `Verwijderen mislukt: ...` message instead of a bare `500` on failure.
- **Delete-user button visibility check used the wrong permission**: the "Beheer" tab's delete button was
  gated on `users.create` instead of `users.update`, which no longer matched what the backend actually
  requires.

### Notes
- A separate, lower-severity issue was found but intentionally **not** fixed here: the shared HTTP client
  used by `MumaResource` (`core::http::SendQueue`) treats any non-2xx response from MuMa as a transport
  failure, collapsing it into a generic `502 Bad Gateway` instead of relaying the real status code/body.
  This doesn't block real logins (a valid Google token returns `200`), but it does hide legitimate error
  details (e.g. an actually-invalid token, or a `403`) behind a generic gateway error. Fixing it would
  touch a shared component used by every other `IClient` consumer in the codebase, so it's flagged here as
  a follow-up rather than changed as part of this fix.

## [0.0.2] - 2026-07-26

> **Fix: production was deploying stale images.** After cutting `0.0.1`, `music.example.com`
> kept showing old behavior post-deploy. Root cause: `muma:deploy` only ever ran
> `docker compose pull`, but nothing in the pipeline actually *built and pushed* fresh
> `music-manager`/`lms` images first — it silently kept re-pulling whatever image had last been
> pushed **manually**, so a release could "deploy successfully" while production kept running old
> code.

### Fixed
- **Missing image build/publish step in the release pipeline**: added a new `release:build-images`
  CI job (stage `release`, before `deploy`) that builds and pushes fresh `music-manager` and `lms`
  (`music-management-server`) Docker images to Docker Hub on every `release/*` branch, via the new
  `scripts/ci/build-and-push-images.sh`. `muma:deploy` now always pulls an image that was just built
  from the code actually being released, instead of a possibly-stale, manually-pushed one.
- `release:build-images` is gated on the new `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` CI/CD variables
  and runs in the same `release` stage as `release:version-check`, so `muma:deploy` (stage `deploy`)
  cannot start until both have succeeded — a failed or skipped image build blocks the deploy.

## [0.0.1] - 2026-07-26

> **Version reset.** This release intentionally restarts the overarching monorepo version number at
> `0.0.1`, replacing the previous `2.x` line. It marks the first official release produced under the
> new `develop` → `release/*` → `master` branching/release-management flow described in
> `docs/release-management.md`, and the first release of this project as a single, unified monorepo
> (backend services + Music Management Server + frontend + Ultrasonic client, one shared history). The
> root `VERSION` is the *overarching* version for this monorepo release line; individual components
> (e.g. Ultrasonic's own `versionName`/`versionCode`) keep their own, independent version numbers, as
> documented in the versioning policy.

### Added
- **Unified release process**: introduced the `develop` (integration) → `release/x.y.z` (stabilization +
  production deploy) → `master` (tagged, append-only production record) branch model. Production deploys
  now only happen from `release/*` branches, gated by an automated `release:version-check` that fails the
  pipeline if `VERSION`, `CHANGELOG.md`, or `RELEASE_NOTES.md` weren't updated. See
  `docs/release-management.md` for the full design and rationale.
- **CI-driven git tagging**: merges into `master` now automatically create an immutable `release-vX.Y.Z`
  tag (and `ultrasonic-vX.Y.Z` when an Ultrasonic release is included), so "what's actually live" can
  always be answered from `master`'s tag history, with no manual `git tag` step.
- **Automated Ultrasonic APK distribution**: CI now automatically builds and uploads a debug Ultrasonic
  APK to `apk-hoster` on every `develop` merge, and the official, signed APK on every `release/*` branch
  (previously both were fully manual, local-only steps).

### Changed
- **Repository**: merged the previously split-out `music-management-server` (LMS) and `ultrasonic`
  Android app repositories directly into this repository as a single monorepo, with their full commit
  history preserved (via `git subtree`). The `frontend` (which never had its own separate history) is
  now tracked here too. There are no more submodules or separate gitlab remotes for these projects —
  see `AGENTS.md` for the rationale (solo developer, tightly-coupled apps, one shared history).
- **Production deployment**: the `muma:deploy` pipeline job was fixed to use dedicated, CI-managed SSH
  key authentication and now reliably deploys both production stacks (`music-management` and `lms`)
  idempotently from a `release/*` branch, instead of the previously broken/manual `main`/`develop` flow.

## [2.6.0] - 2026-07-20

### Added
- **Mobile Integration (Ultrasonic)**: Formalized the integration of the Ultrasonic Android app into the ecosystem documentation.
- **Client Settings Sync**: Enabled server-side backup and synchronization for mobile application settings via the Music Manager API.
- **Subsonic API Support**: Standardized Subsonic API responses in the Music Management Server for seamless compatibility with mobile clients.
- **APK Distribution**: Integrated `apk-hoster` for independent distribution of mobile updates.

## [2.5.0] - 2026-07-11

### Changed
- **Path Migration**: Migrated the entire application from `/music` to `/mnt/music` across Docker configurations, environment variables, and application logic.
- **API Architecture**: Centralized `common/api` into `music-manager`. Workers now push updates to the `music-manager` hub instead of running their own API servers, simplifying the architecture.
- **Project Structure**: Removed the intermediate `music-management/` folder and moved `services/` to the root, resulting in a cleaner layout and simplified `PYTHONPATH`.
- **Worker Integration**: Fully integrated YouTube and SoundCloud downloaders with the centralized `job_manager` for real-time progress tracking.

### Added
- **Test Isolation**: Introduced `services/conftest.py` for aggressive mocking of heavy dependencies (`pymysql`, `mutagen`, `yt-dlp`), enabling tests to run without a live database.

### Fixed
- **API Routing**: Fixed path mismatches in tests and standardized all API routes under the `/api` prefix in `music-manager`.
- **Code Quality**: Removed over 80 redundant proxy methods in `management.py` and improved robustness of `Tag.to_string` and path resolution logic.

## [2.4.1] - 2026-07-10

### Added
- **Redownload Feature**: Added a "Redownload" button to the Library UI for SoundCloud and YouTube tracks.
- **Archive Integration**: The system now automatically finds the original source URL from the download archives to facilitate redownloads.
- **Downloader Enhancements**: Added `redownload_mode` to SoundCloud and YouTube downloaders to allow bypassing existing archive entries when explicitly requested.

## [2.4.0] - 2026-07-10

### Changed
- **Architecture**: Integrated the `tagger` and `scanner` services directly into the `music-manager` service.
- **Workflow**: Tagger and Scanner now run as background threads within the music manager process, reducing inter-service communication overhead and simplifying Docker deployment.
- **API**: Moved `/tag/*` and `/scan/*` endpoints to `/api/tagger/*` and `/api/scanner/*` respectively within the music manager API.
- **Performance**: Track rescan in the library now uses direct function calls for tagging and scanning instead of internal HTTP requests.

## [2.3.4] - 2026-07-10

### Fixed
- **Rescan Workflow**: Fixed a race condition where the scanner would run before the tagger finished by making single-file API calls synchronous.
- **Tagger Metadata**: Fixed an issue where manual rescans wouldn't clear the `needs_rescan` flag in the database.
- **Docker Networking**: Corrected internal service URLs in `docker-compose.yml` to use internal container ports instead of host-mapped ports.

## [2.3.3] - 2026-07-10

### Added
- **Scanner Service API**: Integrated a FastAPI-based REST API on port 8002 for the scanner service.
- **Immediate DB Sync**: Library track rescan now triggers both the tagger and the scanner for instant database updates.

## [2.3.2] - 2026-07-10

### Added
- **Tagger Service API**: Integrated a FastAPI-based REST API on port 8001 for the tagger service.
- **On-Startup Full Scan**: Service now explicitly performs a full tagging scan immediately upon startup.
- **Tagging Control Endpoints**: New `/tag/all` and `/tag/file` endpoints to trigger metadata enforcement via API.

## [2.3.1] - 2026-07-10

### Added
- **Tagger Auto-Detection**: New `TagSingleFile(path)` utility function that automatically determines the song source (SoundCloud, YouTube, Label, etc.) based on its file location and applies the appropriate tagging rules.

## [2.3.0] - 2026-07-05

### Added
- **MuMa Cloud Sync**: New server-side backup system for application settings (User App Settings API).
- **Settings API**: Endpoints for saving and retrieving JSON-based application configurations per user and app ID.
- **Enhanced Scrobble Imports**: Implemented robust pagination for ListenBrainz imports, allowing retrieval of up to 10,000 tracks.
- **Artist Image Synchronization**: Centralized artwork management for multi-LMS environments (Stable and Alpha).
- **Consolidated Versioning**: Unified version reporting for all internal worker services in the dashboard.

### Changed
- **Authentication**: Streamlined API key flow; keys returned at login are now universally valid for user-specific actions.
- **Security**: Removed sensitive API key displays from the frontend, relying on session-based auth.
- **Database Architecture**: Added `user_app_settings` and `scrobble_imports` tables to core initialization.
- **Stats Engine**: Refactored statistics queries to provide more accurate match rates and genre distributions.

## [2.2.0] - 2026-07-05

### Added
- **Dynamic Playlists**: Support for storing and managing dynamic playlist definitions (modifiers) in the database.
- **Management API**: New endpoints to create, update, and retrieve dynamic playlists.
- **User Service**: Added dynamic playlist management to the user-centric API.
- **LMS Integration**: Added a feedback hook to receive and process real-time playlist updates from LMS.

## [2.1.35] - 2026-07-05
### Fixed
- **User Management**: Fixed an issue where deleting or creating users in MuMa did not reflect in LMS due to a read-only database mount.
- **Service Integration**: Changed the `lms.db` mount in `user-service` to read-write by mounting the parent directory, allowing SQLite to handle journal files.
- **Logging**: Added enhanced logging and permission checks in the User Service to monitor LMS database connectivity.

## [2.1.34] - 2026-07-05
### Added
- **User Management**: Added ability to delete users and set default passwords in the Control Center.
- **LMS Synchronization**: Implemented immediate bidirectional synchronization with the Lightweight Music Server (LMS) database.

## [2.1.33] - 2026-07-05
### Fixed
- **Stats Service**: Resolved build and deployment issues for the new stats microservice.
- **Database**: Cleaned up redundant indices on the `rules_genres` table.

## [2.1.32] - 2026-07-05
### Added
- **Stats Microservice**: Decoupled library statistics into a dedicated microservice (`stats-service`).
- **Improved Management API**: Integrated statistics module directly into the Control Center via proxy to the new microservice.
- **Library Stats CLI**: Added a `stats` command to `install.sh` to quickly view library statistics from the terminal.

## [2.1.31] - 2026-07-05
### Added
- **Health & Activity Dashboard**: New tab in the Control Center for real-time monitoring of Docker containers.
- **Docker Logs Viewer**: View the logs of all Muma-related containers directly from the UI.
- **Recent Activity**: Overview of recently added and tagged tracks, categorized by source (YouTube, SoundCloud, etc.).

## [2.1.30] - 2026-07-05
### Added
- **LMS Subsonic API Key**: The Subsonic API key in LMS can now be configured via the environment variable `LMS_SUBSONIC_API_KEY`, facilitating integration with external apps.

## [2.1.29] - 2026-07-05
### Added
- **Centralized Authentication**: Introduced a centralized `/auth/verify` endpoint in the User Service to validate both system-wide and user-specific API keys.
- **Enhanced Security**: Repurposed the `user-service` as an Identity Provider, allowing services to offload credential verification.

### Fixed
- **Network Hardening**: Minimized the attack surface by removing public port exposures for internal services (Rating, Scrobble, User) in Docker Compose.
- **Internal Communication**: Optimized service-to-service communication by using the shared `music-management_db` Docker network and internal DNS.

## [2.1.28] - 2026-07-04
### Fixed
- **Infrastructure**: Added `LMS_SUBSONIC_API_KEY` to the main `docker-compose.yml` for correct propagation to the User Service.

## [2.1.27] - 2026-07-04
### Fixed
- **LMS Sync**: Resolved mismatch in API keys. Now uses a specific `LMS_SUBSONIC_API_KEY` for LMS, while the Muma services retain their own key.
- **Service Stability**: Improved error handling in the User Service for LMS sync responses.

## [2.1.26] - 2026-07-04
### Fixed
- **LMS Sync**: Resolved authentication issue with the LMS Subsonic API by explicitly adding the `apiKey` parameter to the sync URL.

## [2.1.25] - 2026-07-04
### Fixed
- **API Security**: Resolved inconsistencies in API keys between microservices and the Control Center in Docker Compose configurations.
- **LMS Sync**: Confirmed that the `user-service` sends the correct `X-API-Key` to LMS during user synchronization.

## [2.1.24] - 2026-07-04
### Added
- **YouTube Management**: YouTube accounts can now be managed via the Control Center.
- **Cookie Support**: Added support for Firefox cookies from a shared Docker volume for both YouTube and SoundCloud downloaders.

### Fixed
- **UI Consistency**: SoundCloud and YouTube management pages are now consistent and support removing accounts.

## [2.1.23] - 2026-07-04
### Fixed
- **User Service**: Fixed syntax and logic errors in LMS synchronization (`run_lms_sync`).
- **Configuration**: Added `LMS_HOSTS` support for multiple LMS instances and fixed `LMS_HOST` typo in `.env`.

## [2.1.22] - 2026-07-04
### Added
- **API Security**: Implemented system-wide API key validation (`X-API-Key`) for all microservices.
- **Control Center**: Added ability to set and save the API key in the dashboard.
- **User Service**: Added `user-service` to the `full` Docker Compose configuration.

### Fixed
- **API Consistency**: The `API_KEY` is now synchronized across all modules in the `music-manager`.
- **LMS Configuration**: Corrected default LMS host to `lms.example.com`.

## [2.1.20] - 2026-07-04
### Fixed
- **LMS Configuration**: Corrected default LMS host to `lms.example.com` and updated CORS origins to the correct production IP (192.0.2.27).

## [2.1.19] - 2026-07-04
### Added
- **User Password Management**: Set passwords via Control Center with automatic synchronization to LMS.
- **Security**: Implemented Bcrypt hashing for secure storage of user passwords.

## [2.1.18] - 2026-07-04
### Added
- **User Migration**: Imported users from `lms.db` to the User Service.
- **LMS Integration**: Added support for direct SQLite database synchronization from LMS.
- **UI Enhancements**: Added new synchronization options to the Users dashboard.

## [2.1.17] - 2026-07-04
### Added
- **User Service**: New microservice for centralized user management and external account links (ListenBrainz).
- **Control Center**: New "Users" dashboard for managing users and their API keys.
- **LMS Sync**: Ability to synchronize users/players directly from Logitech Media Server.
- **Scrobble Integration**: Integrated ListenBrainz imports based on saved user profiles.

## [2.1.16] - 2026-07-04
### Fixed
- **Scrobble Service**: Fixed ListenBrainz import crash caused by missing `json` import and improper data serialization.
- **Scrobble Service**: Added required `User-Agent` header to ListenBrainz API requests to prevent blocking.
- **Scrobble Service**: Improved database error handling during background import tasks.

## [2.1.15] - 2026-07-04
### Added
- **Control Center**: New Scrobble Service dashboard with ListenBrainz import monitoring.
- **Scrobble Service**: Added `scrobble_imports` table for tracking background task progress.
- **Scrobble Service**: New endpoints for polling import status and fetching recent history.
- **Frontend**: Real-time polling for active imports and visual progress bars.

## [2.1.14] - 2026-07-04
### Added
- **Scrobble Service**: New microservice for tracking listens and importing history from ListenBrainz.
- **ListenBrainz Integration**: Support for importing user listening history and automatic track matching.
- **Smart Matching**: Fallback logic for matching tracks via Artist/Title when MBIDs are unavailable.
- **Infrastructure**: Added Scrobble Service to the build pipeline and Control Center dashboard.

## [2.1.13] - 2026-07-04
### Changed
- **Rating System**: Renamed database table from `track_ratings` to `rating_tracks` for better consistency.
- **UI Refinement**: Global override of focus rings to eliminate blue browser defaults in favor of Spotify Green.
- **Styling**: Further alignment with `styleguide.md` for a consistent dark theme experience.

## [2.1.12] - 2026-07-04
### Added
- **Debug Support**: Added `--debug` flag to `build.sh` and `publish.sh` for detailed execution logging.
- **Design System**: Created `styleguide.md` to formalize the Spotify-inspired dark theme (Green/Black/Gray).
- **UI Refinement**: Standardized all UI accent colors to Spotify Green (`#1DB954`) and improved focus/selection states.

## [2.1.11] - 2026-07-04
### Added
- **Centralized Release Notes**: The Control Center now aggregates and displays release notes and changelogs from all modular services.
- **Service API Expansion**: Added versioning and release notes endpoints to the Rating System service.

## [2.1.11] - 2026-07-05
### Added
- **Library Stats CLI**: Added a `stats` command to `install.sh` to quickly view library statistics from the terminal.
- **Improved Management API**: Integrated statistics module directly into the Control Center.

## [2.1.10] - 2026-07-04
### Added
- **Modular Containerization**: Split the monolithic application into 10 specialized, lightweight services (`muma-scanner`, `muma-tagger`, `muma-downloader`, etc.).
- **Smart Build System**: Introduced `scripts/affected.sh` and optimized `install.sh` to skip builds for unedited modules.
- **Unified Base Image**: Created `muma-base` to share core music logic and dependencies, reducing image size and ensuring consistency.
- **Parallel Builds**: Optimized `build.sh` and `publish.sh` to execute Docker operations in parallel.

### Fixed
- Fixed missing `pymysql` and other dependencies in `ml-analyzer` worker.
- Silenced database permission warnings in workers when tables/views are already managed by migrations.
- Improved Telegram worker stability with dedicated `asyncio` loop management.
- Resolved circular dependencies by consolidating core logic in the base image.

## [2.1.9] - 2026-07-04
### Fixed
- Fixed `ml-analyzer` being offline by setting up a repeat loop and proper Docker command.
- Resolved `RuntimeError` in Telegram worker by improving `asyncio` loop management and explicitly passing it to Telethon.
- Removed redundant `yt-dlp` updates on service startup to speed up container initialization.

## [2.1.8] - 2026-07-04
### Fixed
- Improved Telegram worker stability by using a dedicated event loop and modern `asyncio` patterns.

## [2.1.7] - 2026-07-04
### Fixed
- Fixed `KeyError` in YouTube downloader by aligning configuration keys with `ConfigStore`.
- Added missing `muma-rating-system` to build and deployment scripts.

## [2.1.6] - 2026-07-04
### Fixed
- Consolidated all service code into the base image to resolve circular and cross-service dependencies.
- Added all common dependencies (`yt-dlp`, `telethon`, `patool`, etc.) to the base image to ensure all workers can share the same entry points.

## [2.1.5] - 2026-07-04
### Fixed
- Fixed API server crash due to missing dependencies (`markdown`, `pydantic`) in worker images.
- Fixed `UnboundLocalError` in API initialization.
- Fixed package recognition for `services.tagger` in modular workers by including `__init__.py` in the base image.

## [2.1.4] - 2026-07-04
### Fixed
- Fixed missing `requests` dependency in Management API.
- Fixed `ModuleNotFoundError` in modular worker images by moving core music logic (`BaseSong`, etc.) to the base image.
- Improved Management API Dockerfile to inherit from the shared base image.

## [2.1.3] - 2026-07-04
### Changed
- **Consolidated Deployment**: Unified root `deploy.sh` and `scripts/deploy-stack.sh` into a single `scripts/deploy.sh`.
- **Streamlined Workflow**: Updated `install.sh` to use the new centralized deployment script.

## [2.1.2] - 2026-07-04
### Fixed
- Fixed SQL syntax errors in `migrate_v2.sql` for MariaDB compatibility.
- Unified artist and label genre rule tables into a normalized structure with backward-compatible views.
- Improved database initialization logic to handle table renames and view creation.

## [2.1.1] - 2026-07-04
### Added
- Formalized `scanner_service` in Docker Compose configurations for production deployment.
- Created `docker-compose.full.yml` as a consolidated configuration for Portainer and manual stack management.

## [2.1.0] - 2026-07-04

### Added
- **Artist-Genre Editor**: A new Spotify-inspired UI for mapping artists and labels to genres.
- **Library Scanner**: A new `muma-library-scanner` service that automatically indexes audio files into the database.
- **ReadonlySong**: A specialized song class for metadata extraction without file modification.
- **Database Schema v3**: Added tables for `rules_artist_genres`, `rules_label_genres`, `library_artists`, and `library_labels`.
- **API Endpoints**: New REST endpoints for artists, labels, and genre-mapping rules.

### Fixed
- Improved database connection reliability in the Management API.
- Standardized Docker worker configurations.

## [2.0.0] - 2026-07-04
### Added
- Created `scripts/deploy-stack.sh`, a generalized Docker stack deployment tool supporting Portainer discovery, SSH transfer, and intelligent fallbacks.
- Support for initial stack creation: the deployment script now automatically creates the stack if it does not exist yet using a local template.
- Modular build system with separate `build.sh`, `publish.sh`, and `deploy.sh` scripts.
- Versioned Docker tagging: images are now tagged with both `:latest` and the repository version (e.g., `:2.0.0`).
- Portainer Webhook support for automated Stack updates.
- Automatic Docker group permission handling via `sg docker` re-execution.
- Standardized `.env` configuration for all deployment targets.
- `install.sh` shortcut for the full build-publish-deploy pipeline.
- Proactive Docker registry authentication checks.
- Advanced audio feature extraction (MFCC, ZCR, Rolloff, Chroma) in ML analyzer.

### Changed
- **Deployment**: Refactored `deploy.sh` to use the new generalized `deploy-stack.sh` helper, simplifying per-project deployment scripts.
- **Deployment**: Enhanced stack discovery to support `PORTAINER_HOST` for pulling master templates.
- **Deployment**: Improved robustness with `base64` template transfer and automated tab-to-space conversion in compose files.
- Refactored core to use normalized database schema v2.
- Updated `install.sh` to automate environment setup and dependency installation.
- Optimized Docker builds by using system FFmpeg packages instead of source builds.
- Unified deployment variables across repositories.

### Fixed
- Fixed Docker Hub push denial by adding pre-flight authentication checks.
- Fixed path typos in configuration store and downloader modules.
- Improved database storage robustness for high-load analysis jobs.
