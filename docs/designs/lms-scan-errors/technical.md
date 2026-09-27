# LMS Scan Errors — Technical Design

> Implements [functional.md](functional.md). Code: `services/music-management-server/src/libs/services/scanner/`.

## Data Model

No database change. `ScanStats` (public header `services/scanner/ScannerStats.hpp`) gains:

- `enum class ScanErrorKind` -- one value per concrete `ScanError` type, plus `Count`;
- `ScanErrorCounts errorCountsByKind` -- `std::array<std::size_t, Count>`, incremented next to
  `errorsCount` in `ScanStepBase::addError`, so the two always agree.

`ScanStats::errors` (the first 5,000 errors, rendered by the admin scan report) is unchanged.

## API Contract

No HTTP or Subsonic change. The only external surface is the `[DB UPDATER] Scan complete/aborted`
log line, whose `(errors = N)` part becomes `(errors = N: <count> <label>, ...)` when N > 0.
Labels come from `toString(ScanErrorKind)` and are stable: `io`, `audio-unreadable`,
`embedded-image`, `no-audio-track`, `zero-duration`, `artist-info`, `artist-info-no-name`,
`image-unreadable`, `lyrics`, `playlist`, `playlist-entry-missing`,
`playlist-all-entries-missing`.

## Behaviour

New `impl/ScanErrorPolicy.{hpp,cpp}`, pure functions, unit-tested in `test/ScanErrorPolicy.cpp`:

- `getScanErrorKind(const ScanError&)` -- visitor.
- `formatErrorBreakdown(const ScanErrorCounts&)` -- the summary suffix.
- `decidePlayListErrorReporting(playListPath, ScanOptions)` -- `SkipImportQueue` when any path
  component is `__TODO` (`importQueueDirName`); `SkipOutOfScope` when the scan is scoped and the
  playlist is under none of `scanDirectories` (component-wise, via
  `core::pathUtils::isPathInRootPath`); otherwise `Report`.
- `isMissingFileError(std::error_code)` -- `ENOENT`/`ENOTDIR`.

`ScanStepAssociatePlayListTracks` keeps computing associations for every playlist (a moved track
can be named by a playlist anywhere) and passes `context.scanOptions` to its jobs; a job drops a
playlist's pending errors unless the decision is `Report`, with a DEBUG line saying why.

`ScanStepCheckForRemovedFiles::checkFile` logs a `directory_entry` failure at DEBUG ("Removing ...:
missing") when `isMissingFileError`, at ERROR otherwise; the file is removed from the index in both
cases, as before.

## Cross-App Impact

None. MuMa does not parse the summary line. The import-queue name `__TODO` is MuMa's importer
convention; it is a constant next to `excludeDirFileName` in the scanner, like the scoped-scan
feature it complements.

## Technical Acceptance Criteria

- `test-scanner` covers classification of every error type, unique labels, breakdown ordering and
  the empty case, scope inclusion/exclusion including a sibling folder with a common prefix
  (`Scantraxx` vs `Scantraxx Silver`), `__TODO` in library and scoped scans, `__TODO_old` not
  matching, and missing vs other `error_code`s.
- `muma-server-tidy.sh` and `muma-server-format.sh` pass.

## Related Docs

- [bug report 121](../../bug-reports/121-lms-scan-errors-and-queue-playlists.md)
- [LMS scan trigger design](../lms-scan-trigger/technical.md) (scoped scans, bug 120; priority
  passes inside a library-wide scan, bug 126 -- a pass is a scoped scan, so `SkipOutOfScope`
  applies to it and its errors stay out of the published library-wide stats)
