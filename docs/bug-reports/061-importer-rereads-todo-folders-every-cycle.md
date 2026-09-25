# Importer Re-Reads Unplaceable __TODO Folders Every Cycle

# status: fixed

# reported problem
Audit item B9 (2026-09-23, from reading the code): every importer cycle, roughly every 300 s,
re-read the audio tags of every release folder in the import folder (`__TODO`) that the mover
could not place, over CIFS. Production holds ~2,266 such folders -- releases whose catalogue
number has no `rules_catid_label` row -- so each cycle was thousands of tag reads for folders
whose answer could not change until the folder itself, a label rule or a proposal decision did.

# Possible reason
`Mover._move_folder` and `Mover.run` hand every unplaceable folder to `Mover._propose`, which
calls `label_resolver.resolve` -- a `mutagen.File` per track -- and writes the result to
`rules_label_proposals`.

MR !928 (0.73.0) added an in-memory `{folder: newest mtime}` map so a folder is resolved once
per process. Three gaps remained:

- The map lives only as long as the process. Every deploy or container restart started the
  whole backlog over, and deploys here are frequent.
- Nothing invalidated it on a rule or decision change. That was harmless for the move itself
  (the `rules_catid_label` lookup runs before the cache), but a proposal that was reset or
  deleted was not written back until the next restart.
- The per-folder `WARNING` (`CAT ID ... not found in database` / `No valid CAT ID found`) was
  still logged before the cache was consulted, so every cycle wrote ~2,266 `WARNING` rows to
  the event log for folders nothing had happened to.

# solution
The proposal row now carries `resolved_fingerprint` (CHAR(64), migrate_v38, also in
`db_init`): a SHA-256 over

- the folder's signature from `settle.folder_signature` -- entry count, total file size and
  newest mtime, from one `stat` walk that opens no file;
- the version of `rules_catid_label` -- `COUNT(*)` plus `SUM(CRC32(catid TAB label))`, because
  the table has no timestamp and an edited label keeps the count;
- the row's own `status` and `decided_at`, so a decision on this folder's proposal resolves it
  once more.

At the start of a cycle `LabelProposalStore.snapshot()` reads the rules version and every
proposal row in two queries. `_propose` computes the fingerprint and, when the stored one
matches, skips the folder: no tag read, no record, no warning. Otherwise it logs the warning,
resolves exactly as before and records the proposal together with the new fingerprint (always
written, whatever the status, since it is the importer's bookkeeping and not the proposal). A
folder whose signature cannot be read is always resolved. When the table cannot be read the
mover falls back to the in-process signature map of !928.

One `INFO` line per cycle replaces the per-folder noise:
`Unplaceable folders: N checked, N skipped as unchanged, N re-read`.

There is no importer rescan endpoint; `UPDATE rules_label_proposals SET resolved_fingerprint =
NULL` forces one full re-read. Every existing row starts NULL, so the first cycle after the
deploy reads the backlog once more and fills the column.

Tests: `services/importer/tests/test_importer_mover_cycle.py` (unchanged folder skipped on the
second cycle and after a restart, changed folder and rules-version bump and decision re-read,
counts logged, warnings only on a re-read) and `test_importer_label_proposal_store.py`.
