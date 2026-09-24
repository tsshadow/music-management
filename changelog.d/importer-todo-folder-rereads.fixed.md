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

<!-- release notes -->

- **The importer no longer re-reads thousands of unplaceable folders after every restart.** A
  folder it could not place is read again only when it, a catalogue rule, or its proposal changes,
  and the per-folder warnings every five minutes are replaced by one summary line.
