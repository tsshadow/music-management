# Scene Releases Show No Cover Because LMS Ignores `00-...` Cover Files

# status: fixed

# reported problem
GitLab issue #158 (verification: #159). Measured on production on 2026-10-01 (read-only, `lms.db`
opened with `?mode=ro`):

- 45,101 of LMS's 54,164 releases have no preferred artwork (`release.preferred_artwork_id IS NULL`).
- 34,200 of those have at least one image in a directory holding one of their tracks, and
  **33,590 have an image whose stem starts with `00`** (33,463 directories).
- Tracks without artwork of their own fall back on the release's, so these tracks show
  no cover anywhere -- web player, app, Subsonic clients -- unless the audio file embeds a picture.

# Possible reason
The release artwork search (`ScanStepAssociateReleaseImages`, `findImageInDirectory`) only takes
an image whose stem matches `cover-preferred-file-names`: `("cover", "front", "folder", "default")`,
both as the code default and in the `lms.conf` baked into the image (`conf/lms.conf`, copied to
`/etc/lms.conf` by `Dockerfile-release`; production mounts no config of its own).

Scene releases do not use those names. They name the cover after the release:
`00-a-rize_-_hold_me_close-(ety014)-single-web-2022.jpg`, `00_the_purge_-_switch-(spoon137)-web-2018.jpg`,
`000-va-...-2cd-2023-cover.jpg`. A plain `00*` wildcard is not enough, because the same prefix is
used for everything else the release ships. Sampled on production (all images of 25 random
single-image and 25 random multi-image folders, then the whole set by script):

- 33,079 of the 33,463 folders hold exactly one `00*` image: the cover.
- The other 384 hold several: `...-front`, `...-back`, `...-proof` (a photo of the CD, 4000x3000),
  `...-inlay`, `...-inside`, `...-booklet1`, `...-cd1`, `...-cover_disc`, `...-side_a` (vinyl
  label), `...-cd_scan`, `...-total`, `...log.jpg` (a rendered rip log).
- 115 folders hold a single `00*` image that is a proof or a scan (`...-2021-srg-proof`,
  `...-2008-(proof)-homely`, `...-2008-scan`).
- Words in the title collide with those markers: `come_back`, `voices_inside`, `the_inner_wealth`,
  `front_to_back` -- 613 lone covers have one. Matching the markers anywhere in the stem would drop
  them.

Separately, 191 artless releases sit in a folder whose only image has some other name
(`R-918954-1175427116.jpg`, a Discogs download).

# solution
LMS (`services/music-management-server`):

- **Fallback after the preferred names** (`scanner/impl/steps/ReleaseArtworkRules.*`). A release's
  artwork is now, in order: an image named after its MBID or one of `cover-preferred-file-names`;
  an embedded front cover; the fallback image of its directories; an embedded disc image; an
  embedded image of another type. The fallback sits after the embedded front cover so that the
  8,689 releases whose artwork is already an embedded picture keep it (7,341 of them also have a
  `00*` image).
- **The fallback rule.** Candidates are the images whose stem starts with a
  `cover-fallback-file-stem-prefixes` entry (`00`). Each is judged on its distinguishing part only:
  with several, what remains once the start and end they all share are cut away (on word
  boundaries, so `proof` and `proper` stay whole); with one, the words after its last year. A
  candidate with a word starting with a `cover-fallback-excluded-words` entry (`back`, `proof`,
  `inlay`, `inside`, `booklet`, `cd`, `disc`, `scan`, `log`, `nfo`, ...; leading digits ignored,
  so `2back`, `proof1`, `cd1` count) is dropped. Of the rest, one with a
  `cover-fallback-front-words` entry (`front`, `cover`, `folder`, in that order) wins, then the
  first by stem. With no candidate left and exactly one image in the folder, that image is taken
  (`cover-single-image-fallback`), unless it is itself marked `back`, `disc`, etc.

  Picked: `00-a-rize_-_hold_me_close-(ety014)-single-web-2022`, `00-proto_bytez_-_come_back-(ssl171)-single-web-2020-srg`
  (title word), `...-cd-flac-2024-front` over `-back` and `-proof`, `...-cover_front-bc` over
  `-cover_back-bc` and `-cover_disc-bc`, `00_neilio_-_nothing-(dwx322s)-web-2016` over its `-proof`,
  `...-(offrage117)-proper-web-2021-ind` over `-proof-web-2021-ind`, `R-918954-1175427116` (only
  image). Rejected: `...-2021-srg-proof`, `...-2008-(proof)-homely`, `...-2008-scan`,
  `...-cd-2008-back` + `...-cd-2008-cd`, `proof1`/`proof2` pairs, a lone `Back.jpg`.

  Run over every image of every artless release's folders on production, the rule gives 33,445
  of the 33,590 releases a cover and leaves 145, all of them folders that hold only proofs, scans,
  back covers or disc images. The single-image fallback adds about 170 more.
- **Configurable, code and conf in step.** The four new keys have code defaults and are written out
  with the same values in `conf/lms.conf`, which is what production runs. An empty prefix list
  turns the stem rule off.
- **Existing releases get it on the next library-wide scan, even without changes.** A scan only
  ran the artwork steps when it had read a changed file, and since bug report 141 a scoped scan
  only recomputes its own releases. The last scan's settings row now records a fingerprint of the
  release artwork rules (`scan_settings.release_artwork_rules`, LMS database step 126, version
  127; no scan version bump, so no file is re-read). A library-wide scan that finds the current
  fingerprint different runs AssociateReleaseImages, AssociateArtistImages (artists fall back on
  release artwork) and AssociateTrackImages over the whole library, even with zero changes. A
  scoped scan never does, and does not record the new fingerprint, so it cannot use the change up.
  The fingerprint also covers the preferred names, so editing `cover-preferred-file-names` now
  takes effect the same way.

  On production the row is empty after the migration, so the first library-wide scan after the
  deploy applies the rule. music-manager requests one after every download, import and tagger run;
  the weekly scheduled one (Monday 01:00) is the backstop. A library-wide scan took 7 min 10 s on
  2026-10-01 (06:46:43-06:53:53 UTC, 887,218 files, 325 changes). The artwork steps are about 31 s
  of that (bug report 141: release 7.6 s, artist 5 s, track 18 s); the fallback adds one indexed
  image query per folder for the ~45,000 releases without a preferred name, which should stay in
  the same range.

Tests: `scanner/test/AssociateReleaseImages.cpp` (the rule on real stems, the step on a database:
a `00-` stem picked, a proof not, the single-image fallback, a preferred name still winning, and
a library-wide scan with no changes applying new rules while a scoped one does not);
`database/test/Migration.cpp` (step 126).
