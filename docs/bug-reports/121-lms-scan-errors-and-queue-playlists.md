# LMS Scoped Scans Report 967 Errors; Playlists in the Import Queue Fail to Parse

# status: fixed

# reported problem
GitLab issue #95. In `docker logs lms` on production every scoped scan ended with the same count:

    Scan complete. Changes = 2 (added = 0, removed = 0, updated = 2, failures = 0), Not changed = 1709, Scanned = 2 (errors = 967), ...

-- two files read, 967 errors. Between the summaries the log held hundreds of
`Failed to parse playlist "...": all entries are missing` lines, many of them for `.m3u` files
under `EPs/__TODO`, the importer's queue. Nothing said what the 967 were, so there was no telling
whether files in the library were unreadable (as in issues #69/#70 or bug 117) or this was noise.

# Possible reason
Measured read-only on 2026-09-27 from six hours of `docker logs lms` on 192.0.2.27, and by
looking at the playlists and their folders inside the container.

**Where the number comes from.** `ScanStats::errorsCount` is incremented by
`ScanStepBase::addError`. In the four scoped scans between 01:37 and 01:41 every error came from one
step, `ScanStepAssociatePlayListTracks`, and it was the same set each time:

| kind | count | logged at |
|---|---|---|
| `PlayListFileAllPathesMissingError` -- none of the playlist's entries is a known track | 637 | ERROR |
| `PlayListFilePathMissingError` -- one entry of an otherwise matching playlist is unknown | 330 | DEBUG |
| total | 967 | |

The 330 are invisible at the default log level yet counted, which is why the count and the ERROR
lines never matched.

**Why a two-file scan reports them.** The association step does not look at the scan's scope: it
runs whenever anything changed and walks every playlist in the library, re-reporting every broken
one on every scoped scan. The file scan, the removed-files check and the duplicate check are all
scoped; this step was not.

**What the 637 playlists are.** Each is a scene release's own `00-<release>.m3u`:

- 49 are in `EPs/__TODO` and no longer exist: the importer moved the release into the library, but
  the rows stay until a library-wide scan's removed-files check runs, and no library-wide scan has
  completed since before bug 120 (issue #94).
- The other 588 still exist (14 of them in `__TODO`, in a release that is being processed):
- 439 lie in a folder that does hold audio, but under other names: the tagger renames tracks, the
  scene playlist still lists the original names
  (`01_devin_wild_..._-_fifteen_(scantraxx_15_years_ost)_(original_mix).mp3` against
  `01_devin_wild_..._-_fifteen_(original_mix).mp3` on disk).
- 149 lie in a folder with no audio at all -- `.m3u`, `.nfo`, `.sfv` left behind, mostly
  `Livesets/Defqon.1`.

None of the 967 is an unreadable file. The real read failures on production -- 648 unreadable
images, 274 unparseable audio files, 175 with duration 0, 11 without an audio track -- come from the
file scan of the library-wide runs, and are unaffected by this change.

**A second source of noise.** `ScanStepCheckForRemovedFiles` logged every file that had simply
disappeared as `[error] Error while checking file "...": No such file or directory`: 92,135 lines
in six hours (replaced `artists/*/spotify-*.jpg` portraits, releases moved out of `__TODO`). They
were not counted, but they buried every real ERROR line. A missing file is what the step exists to
find; the `exists()` branch right below it already logged the same outcome at DEBUG.

# solution
- **Every error is counted by kind** (`ScanStats::errorCountsByKind`, `ScanErrorKind`), and the scan
  summary spells the kinds out: `errors = 967: 637 playlist-all-entries-missing, 330
  playlist-entry-missing`.
- **A scoped scan only reports playlist problems inside its own scope.** The association itself
  still covers every playlist -- a track that moved can be named by a playlist anywhere -- only the
  errors are filtered. The library-wide scan still reports all of them; it is the run whose stats
  are published on the admin page and in its downloadable scan report, which lists each error.
- **Playlists in the import queue (`__TODO`) never count.** A release there is half-processed: its
  playlist names files the tagger is about to rename, or the folder is already gone. Its tracks are
  still scanned and playable; the folder is not excluded.
- **A file that vanished is logged at DEBUG**, not ERROR, in the removed-files check. Other failures
  (permission denied, I/O error) stay ERROR.

The decision logic lives in `impl/ScanErrorPolicy.{hpp,cpp}` and is unit-tested in
`test/ScanErrorPolicy.cpp`.

Left open: the 574 scene playlists outside the queue are still reported by the library-wide scan,
now labelled. Whether to stop reporting single-release scene playlists altogether, or have the
importer drop the `.m3u` once the tagger has renamed the tracks, is a decision: issue #96.

Decided on #96: delete them. `scripts/prod/person/delete-stale-m3u-playlists.sh` reads LMS's own
`playlist_file` and `track` tables and applies the scan step's test, so it deletes exactly what
LMS reports: 574 all-entries-missing playlists outside the queue on 2026-10-02 (437 beside audio
under other names, 137 in a folder without audio), after a tar backup, then asks LMS to rescan.
The 113 partly-matching playlists stay unless `--include-partial` is given. A correction to the
analysis above: nothing in the importer or the tagger renames a track file, and 572 of the 574
playlist files date from before 2026, so the mismatches are the collection's history (case
changes, Windows `D:\Music\...` paths, entries the release never had) and no code change is needed
to stop new ones. One way a new one could still appear: the mover places a queue folder whose audio is
gone (12 such folders wait in the queue, each with only its `.m3u` and scene files) -- a decision,
issue #167.
