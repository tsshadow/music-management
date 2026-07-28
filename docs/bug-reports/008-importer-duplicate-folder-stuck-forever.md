# Importer: Duplicate Release Folders Get Stuck in `__TODO` Forever, Logged as OS Errors Every Cycle

# status: fixed

# reported problem
While sweeping production logs after fixing the Telegram worker (`bug 007`), the `importer_worker`
container was found to be logging the same ~15+ `[ERROR] OS error when moving ... (check disk
space/filesystem)` lines on *every single* import cycle, for the same set of release folders, e.g.:

```
[ERROR] OS error when moving /mnt/music/EPs/__TODO/DQ056PRO - Angerfist_-_Gathering_Of_Gods-(DQ056PRO)-SINGLE-WEB-2026-SRG
    to /mnt/music/EPs/Defqon.1 Records/DQ056PRO - Angerfist_-_Gathering_Of_Gods-(DQ056PRO)-SINGLE-WEB-2026-SRG
    (check disk space/filesystem): Destination path
    '/mnt/music/EPs/Defqon.1 Records/DQ056PRO - Angerfist_-_Gathering_Of_Gods-(DQ056PRO)-SINGLE-WEB-2026-SRG/DQ056PRO - Angerfist_-_Gathering_Of_Gods-(DQ056PRO)-SINGLE-WEB-2026-SRG'
    already exists
```

There is no actual disk/filesystem problem (plenty of free space, no permission issues) - the
"already exists" message is the real cause, mislabeled.

# Possible reason
`Mover._move_folder()` (`services/importer/mover.py`) already had explicit handling for the
"this release was already imported before" conflict (`except FileExistsError`, which removes the
duplicate source folder), but `shutil.move(src, dst)` does **not** raise `FileExistsError` for the
actual conflict shape happening here: when `dst` already exists as a directory (from a previous,
successful import of the same release) *and* it already contains an identically-named entry for
`src`, `shutil.move()` instead raises `shutil.Error("Destination path '<dst>/<basename(src)>'
already exists")` - a different exception, which is a subclass of `OSError` on this Python version
and was therefore silently caught by the generic `except OSError` branch instead, which only logs a
(misleading) "check disk space/filesystem" error and does **not** clean up the source folder.

As a result, once a release folder was imported successfully once, any leftover/duplicate copy of
it landing in `__TODO` again (e.g. from a duplicate download) could never be resolved automatically
- it was retried, and re-logged as an "OS error", on every single import cycle indefinitely,
cluttering the logs and requiring manual intervention that was never actually needed.

# solution
Extended the exception handling in `Mover._move_folder()` to also catch `shutil.Error` alongside
`FileExistsError`, treating both identically as an "already imported" conflict: log a warning and
remove the duplicate source folder (`self.remove(folder)`), exactly like the existing
`FileExistsError` path already did. Genuine disk/filesystem errors (e.g. `OSError: No space left on
device`) are unaffected and still fall through to the generic `except OSError` branch, verified by
a dedicated regression test asserting the source folder is *not* removed in that case.

Added `TestMoverConflictHandling` in `services/importer/tests/test_importer_mover.py` covering all
three cases: `shutil.Error` (removes source), `FileExistsError` (removes source, existing
behavior), and a generic `OSError` (does not remove source).
