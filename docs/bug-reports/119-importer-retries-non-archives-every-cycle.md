# Importer Retries Non-Archives Every Cycle

# status: fixed

# reported problem
GitLab issue #90. On 2026-09-27 the production events table held, for each of two `.mp4` video
files a browser download had left in the import folder (`/mnt/music/EPs/__TODO`), 218 WARNINGs and
109 ERRORs in twelve hours, all from the importer:

- `root: Extraction of <name>.mp4 failed (default: unknown archive mime format video/mp4 ...); retrying with unar`
- `root: Extraction of <name>.mp4 failed (unar: unknown archive mime format video/mp4 ...); retrying with 7z`
- `root: Extraction failed for <name>.mp4 with every backend (...)`

Two WARNINGs and one ERROR per file per cycle, each of them a candidate for the alerts topic. The
files are neither archives nor music.

# Possible reason
`Extractor.run` (`services/importer/extractor.py`) listed every regular file at the root of the
import folder, dropped only in-flight downloads (`.crdownload`, `.part`, ...) and later RAR volumes,
and handed each of the rest to `patoolib.extract_archive`. There was no check that a file is an
archive at all -- no extension filter, no content check; the only "settled" rule for files is the
in-flight suffix. patool then answered `unknown archive mime format video/mp4`, the step retried with
the `unar` and `7z` fallbacks (a WARNING each), and logged the ERROR.

Nothing remembered the outcome. A file the step cannot extract stays where it is, by design -- it is
never moved or deleted -- so the next cycle met it again and repeated all three lines, forever. The
same loop applied to a genuine archive no backend can read, to an archive that extracts to nothing,
and to one whose release folder name is already taken in the import folder. Nothing else in the
pipeline handles a loose file either: the flattener, renamer and mover only look at folders.

A latent variant of the same gap: patool treats some audio formats (FLAC, APE, Shorten) as
"archives" it can convert, so a loose `.flac` at the root would have been decoded to WAV and the
original quarantined as an extracted archive.

# solution
- **Only real archives are opened.** `classify()` in `extractor.py` requires an archive extension
  (`.zip`, `.rar`, `.7z`, `.tar`, `.tar.gz`/`.tgz`, `.tar.bz2`/`.tbz2`/`.tbz`, `.tar.xz`/`.txz`)
  *and* the matching signature in the file's first bytes (`PK\x03\x04`, `Rar!\x1a\x07`, the 7z,
  gzip, bzip2 and xz magics, `ustar` at offset 257). Anything else is named by kind: video, image,
  document, loose audio, "named like an archive but is not one", or other. Dotfiles, `Thumbs.db` and
  `desktop.ini` are passed over silently.
- **A file the step will not import is recorded once and left alone.** `FileProblemTracker` in
  `services/importer/conflict_store.py` files it in `importer_conflicts` (the table bug report 091
  introduced for folder conflicts) with `step = 'extractor'`, `source` = the file, `target` = a
  detail or empty, and a new `reason` column holding the code. The first sighting is one WARNING
  (`Left in the import folder, not music: video file: <path>. Not retried until the file changes;
  listed in Beheer for manual intervention`). On later cycles -- also after a restart -- a file whose
  size and mtime are unchanged is skipped without being opened. A changed file is looked at again
  (INFO, not a second WARNING); a removed or renamed one is forgotten at the end of the cycle.
- **An archive that fails to extract is parked the same way**: the fallback retries now log at
  INFO, and the final failure is the one WARNING, recorded as `extraction-failed` with the per-backend
  errors as detail. It stays in the import folder -- the existing policy, the quarantine is only for
  archives that did extract -- and is tried again once it changes on disk, e.g. when a complete
  download replaces a truncated one. `extraction-empty` and `extraction-name-taken` are recorded the
  same way; a taken name is looked at again as soon as the import folder itself changes, because the
  fix for that one happens beside the archive, not in it.
- **Schema**: `migrate_v46_importer_file_problems.sql` widens `importer_conflicts.step` with
  `'extractor'` and adds `reason VARCHAR(32) NULL`; `services/common/db_init.py` matches.
- **Beheer**: `GET /api/import-conflicts` also returns `reason`. The section in Beheer ->
  Labelvoorstellen is now "Openstaande importproblemen": per row the problem (a translated reason,
  or "Naam al bezet door <folder>" for a folder pair), the folder or file, the step and since when.
- Nothing is moved or deleted. Tests in `services/importer/tests/test_importer_extractor.py`
  (`NonArchiveTest`, `ClassifyTest`), `tests/integration/test_schema.py` and
  `services/frontend/tests/unit/labelProposals.test.js`.
