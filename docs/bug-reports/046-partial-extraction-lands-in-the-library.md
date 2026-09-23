# Partial Extraction Lands In The Library

# status: fixed

# reported problem
Found by reading the importer, not by a symptom report, but it explains a documented one: when
`unrar-free` gave up on `HC-2026-WEEK-34-MP3.rar` after 13 of its 44 releases, those 13 stayed in
`__TODO`. The fallback backend then extracted the whole archive on top of them, and the flattener,
renamer and mover of the same cycle placed whatever was there. Five related defects surfaced in the
same pass:

1. **Partial extraction reaches the import folder.** `Extractor._extract` handed patool
   `outdir=import_folder_path`. patool only extracts through a temporary folder when `outdir` is
   `None`, so every backend wrote straight into `__TODO`. A backend that failed halfway left its
   partial folders; the fallback extracted on top, and 7z's `-aou` turned every collision into a
   `name_1.mp3`. The same cycle could place a partial or duplicated release, and when a complete copy
   came in later the mover met a destination whose "contents differ" and asked for manual
   intervention for ever.
2. **Nothing waited for a folder to finish copying.** The in-flight suffix guard covered archives
   only. A release being copied into `__TODO` over SMB could be renamed under the copy, or moved to
   its label half-copied.
3. **The duplicate check compared against the tagged library copy.** `is_same_release` compared file
   names and byte sizes. The library copy is retagged by `LabelSong` right after the move, so a
   later download of the same release differs in size as soon as the new tags do not fit the old
   padding. The mover logged "contents differ ... manual intervention" about it every cycle (a
   variant of bug 008).
4. **Every cycle re-read the tags of every unplaceable folder over CIFS.** `Mover._propose` resolved
   the label of each folder it could not place from scratch, every 300 s -- about 2.266 folders on
   production.
5. **One phone push per imported file.** `post_processing_songs` called `notify` (push) per file, so
   a 44-release pack was well over a hundred pushes.
6. **Split RAR volumes failed every cycle.** After `name.part1.rar` was extracted and quarantined,
   `name.part2.rar`... stayed and were tried, and failed, on every cycle.

Separately, in the nightly database backup (`tools/db_backup.py`):

7. **A full disk never recovered.** Pruning ran only after a successful dump, and running out of
   space raises `OSError`, not `BackupError`, so the half-written `muma_db_*.sql.gz` was not removed.
   Every following night failed the same way on a disk nothing freed.
8. **The monthly copy read ~780 MB into memory**, was written in place and never verified;
   `latest.json` was written in place too, so a killed run could leave `/health/backup` reading
   half a file.
9. `scripts/restore_db.sh` and `tools/backup_db.sh` put the root password on a command line.

# Possible reason
1. patool's temporary-folder behaviour is tied to `outdir=None`; passing the import folder opted out
   of it.
2. The steps were written for archives, which the extractor guards; folders arrive by other routes
   (SMB copies, the browser container, manual moves) and nobody guarded those.
3. Byte size is a proxy for "same recording" that tagging invalidates, and the library copy is always
   tagged.
4. The proposal store already refuses to overwrite a decided row, but the tag read happens before
   the store is reached.
5. The per-file notification predates per-release packs.
6. The extractor lists every file as a candidate archive; nothing knew about volume sets.
7. and 8. The error path was written for `BackupError` only, and the prune was placed as the last
   step of a successful run.

# solution
1. Every extraction attempt writes into a fresh `.muma-extract-*` staging folder inside the import
   folder (same filesystem). A failed attempt deletes its staging folder, so the next backend starts
   from nothing; only a complete extraction is moved in, and a name already taken by something that
   is not the same release leaves the archive in place for a human. Leftover staging folders from a
   killed run are removed at the start of the step, and the other steps skip the prefix. The archive
   is still quarantined after a successful extraction, exactly as before.
2. `services/importer/settle.py`: a folder is settled once nothing in it -- files and directories --
   was modified within `import_settle_minutes` (ConfigStore, default 5). The flattener, renamer and
   mover skip unsettled folders and log that at DEBUG.
3. `is_same_release` compares the track list (audio files by relative path) and each track's length
   from mutagen (`info.length`) within 1 s. Non-audio files are ignored. Tested against real mutagen
   and a retagged MP3 in `tests/unit/test_release_compare_real_mutagen.py`.
4. The Mover keeps `{folder: newest mtime}` for the life of the process and resolves a folder again
   only when it changed. A decided proposal still moves: the catalogue rule it writes is looked up
   before any of this.
5. One `Import Complete` push per release (label, catalogue number, tracks); every file is still an
   `INFO` event, without a push.
6. Only the first volume of a set is opened; a set waits while a volume is still downloading, and all
   volumes are quarantined together after extraction. No `rar` binary is available in the test
   environment, so the tests stub patool and assert which volume is opened and what is parked.
7. The backup prunes before dumping (never the newest daily), checks there is room for the last
   dump's size plus 10% (plus a monthly copy on the 1st), writes under a `.partial` name and removes
   it on any exception.
8. The monthly copy is streamed to a `.partial` name, checked for size and verified like the dump,
   then renamed; `latest.json` is written through a temporary name and `os.replace`.
9. Both scripts pass the password as `MYSQL_PWD` (from inside the container for the restore).
