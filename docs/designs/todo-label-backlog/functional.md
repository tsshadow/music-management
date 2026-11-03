# `__TODO` Label Backlog — Functional Design

## Overview

Three leftovers of the import queue living inside the label tree (`/mnt/music/EPs/__TODO`), all
listed in the open-work list (now GitLab issues #50-#52) and bug report 030:

1. **Files still stamped `__TODO` as their record label.** Before 2026-07-28 the tagger wrote the
   import queue's own name into files as their publisher, and a copyright of `__TODO (<year>)`
   computed from it. The cause is fixed; the tags are not.
2. **The import queue sits in the tree that is scanned for labels.** Every component that walks
   `EPs/*` treating each folder as a label must know to skip it, and one forgot once.
3. **Import folders renamed with an empty catalogue-number prefix** (` - Artist_-_Title-WEB-2025`).
   The label-proposal flow routes them; the names themselves are never repaired.

This is for the library's curator: a label chart, catalogue pages and genre-by-label rules that are
not polluted by a placeholder, and an import queue that can be moved without a code change.

## User Stories

- As the curator, I want every file whose label reads `__TODO` repaired from the folder it lives in
  now, so the label pages and label-genre rules see the real label.
- As the curator, I want to see, before anything changes, how many files are affected per label and
  which ones cannot be decided, so I know what the repair will and will not do.
- As the operator, I want the import queue's location to be one setting, so moving it out of the
  label tree is a setting plus a folder move.
- As the curator, I want the crooked ` - ` folder names repaired where the rules already say which
  label a catalogue number belongs to, and listed where they do not, with a way back.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Dry run of the label repair | Per page: files scanned, files carrying `__TODO` (publisher and/or copyright), a count per derived label, and the undecidable files by path. Nothing is written. |
| Poisoned file in a label folder (`EPs/Scantraxx/...`) | Queued for the tagger; the retag writes `Scantraxx` as publisher and recomputes the copyright. |
| Poisoned file still in the import queue | The importer's resolver proposes a label (shown in the dry run). The retag only empties the placeholder: a label is written once a person confirms the proposal and the release is moved. |
| Poisoned file in `__Free&None` | Counted as "no label"; the retag empties the placeholder. |
| Repair run twice | The second run finds only what the first missed; repaired files no longer match. |
| Queue moved (`import_folder_path` changed, folder moved) | The tagger still tags the queue as generic songs; no label walk treats it as a label; the scanner never stores its name as a label. |
| Crooked folder whose catalogue number a rule knows | Dry run shows the new name `SCAN123 - <rest>`; apply renames it, moves its proposal row along, logs the rename; the next import cycle files it under the label. |
| Crooked folder with no usable catalogue number | Listed as undecidable with the reason; untouched. |
| Rollback of a rename log | Every logged rename still in the queue is put back; one the Mover already filed is reported. |

## Acceptance Criteria

1. The label repair never writes a tag itself; it only queues files with reason
   `todo_label_repair`, and the tagger round does the writing.
2. A retag never writes a label guessed from tags into a file.
3. The dry run lists undecidable files by path and counts every poisoned file per derived label.
4. Changing `import_folder_path` to a folder outside the EPs root requires no code change for the
   tagger, the scanner, the resolver or the label backfills to keep treating it as the queue.
5. No code outside the shared predicate spells out `__TODO` (enforced by a CI test).
6. The rename tool renames only folders whose resulting catalogue number routes to a label in
   `rules_catid_label`, logs each rename before the next, and has a rollback.
7. Nothing in this change runs on production by itself; every production step is a guided script
   that asks for `yes` and backs up first.

## Open Questions / Not Yet Decided

- **When to move the queue.** The operator script exists; the move is a decision for Teun
  (it needs a quiet import queue, a stack restart and a `PROD_ENV_FILE` update).
- **The crooked names the rules cannot place (the large majority).** Measured on 2026-09-25: of
  2.613 crooked proposal rows, at most ~27 carry a catalogue number whose prefix is a rule key. The
  rest need a label decision in the Label proposals tab, not a rename.
