- **A folder conflict in the import queue is warned about once, not every five minutes.** When the
  importer's renamer or mover cannot use a name because a folder holding a different release already
  has it, both folders stay in place as before, but the pair is now remembered in a new
  `importer_conflicts` table (`migrate_v43`): one WARNING the first time, an unchanged pair is not
  compared again, and each cycle ends with one `Standing folder conflicts` INFO line. A pair whose
  folder was removed or renamed is forgotten. On production 49 pairs produced ~490 WARNING events an
  hour. `GET /api/import-conflicts` and a read-only section under Beheer → Label proposals list what
  stands. Bug report 091.

<!-- release notes -->

- **The importer no longer repeats the same folder-conflict warning every five minutes.** Each
  conflict is reported once and listed in Beheer under Label proposals, so it can be resolved by hand.
