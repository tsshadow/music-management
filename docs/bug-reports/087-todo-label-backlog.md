# The `__TODO` Label Backlog: Poisoned Tags, A Queue Inside The Label Tree, Crooked Folder Names

# status: fixed

# reported problem
Three items bug report 030 left open, carried in the GitLab issues:

1. Files tagged before 2026-07-28 still carry `publisher = __TODO` -- the import queue's name -- and
   often `copyright = __TODO (<year>)`.
2. The import queue lives at `EPs/__TODO`, inside the tree every label walker iterates, so each walker
   has to know to skip it.
3. 2.266 import folders (2.613 proposal rows on 2026-09-25) were renamed by the Renamer with an empty
   catalogue-number prefix (` - Artist_-_Title-WEB-2025`) and are never repaired.

# Possible reason
**1. Nothing ever takes the value out again.** Measured read-only on production on 2026-09-25:

- The database cannot see the damage: `channels.is_label` refuses `__TODO`, so no `library_labels`
  row names it (0 rows), and `tagger_processed_files.last_processed` was reset when the table was
  rebuilt on 2026-09-02 (oldest row that day), so "last tagged before the fix" cannot be read either.
  Only the files know. Candidate population by `library_media_files` (single-table scan, no join):
  label folders 110.013 files (58.902 not rewritten since 2026-07-28), queue 15.694 (5.576),
  underscore folders 1.544 (1.307).
- `GenericSong` -- what a file in the queue is tagged as since the fix -- never touches the
  publisher, and its copyright fallback *is* the publisher: a queued file with an album artist but no
  date got `copyright = __TODO` written by the fixed code.
- `LabelSong` overwrites the publisher once a release is filed, but computes a copyright only when
  there is none, so a filed release kept `__TODO (2021)` for good.

**2. Every walker had its own copy of the rule.** `Tagger._parse_label_folders` and
`detect_song_type` (a leading underscore), `channels.NON_LABEL_ROOTS` (a hard-coded `import` root for
after the restructure), `label_resolver._blacklist` (the literal), `backfill_label_from_path.py`
(underscore, twice), and `tools/fix_nested_ep_dirs.py` (nothing: it walked the queue as a label).

**3. The Renamer prefixes the separator whether or not it found a number** (`find_cat_id`), and the
Mover reads '' from before the first space. Stripping the prefix would not help -- the Renamer renames
any folder without `- ` again. Only a real catalogue number in front helps, and only one whose prefix
is a key of `rules_catid_label`. Measured: of the 93 crooked rows whose proposal carries a catalogue
number, most are UPCs, distributor ids (`CAT1424691`, `BP...`) or the literal `none`; at most 24 have
a prefix the rules know, and about 3 more carry one in the name. The rest need a label decision.

# solution
- **One predicate.** `services/common/import_queue.py` (`ImportQueue`) is the only code that knows
  where the queue is: `import_folder_path`, falling back to `<eps_folder_path>/__TODO` (default
  unchanged). All walkers above ask it. When the queue is moved out of the EPs root the tagger walks it
  as GENERIC itself and treats it as a root for new files, so nothing goes untagged.
  `tests/ci/test_import_queue_predicate.py` fails on any new `'__TODO'` literal.
- **Tagger.** `DropQueuePlaceholderRule` empties a placeholder publisher/copyright, first thing in
  `GenericSong.parse` and `LabelSong.parse`, so the copyright is recomputed from the real publisher.
- **Repair.** `services/tagger/todo_label_repair.py` + `GET|POST /api/tagger/todo-label-repair`: pages
  the known files under the label tree by primary key, reads publisher/copyright, derives the label
  from the folder (label folder → that label; queue → the importer's resolver; underscore → none), and
  in apply mode queues the poisoned files with reason `todo_label_repair`. Never retags inline.
- **Rename tool.** `python -m services.importer.catid_prefix_repair --dry-run|--apply|--rollback`,
  renaming only where the new catalogue number routes to a rule label, with a JSON-lines rename log.
- **Operator scripts** in `/tmp/muma-person/`: `repair-todo-label-backlog.sh`,
  `move-import-queue.sh` (writes the steps; moves nothing unless run and confirmed),
  `repair-empty-catid-names.sh`. None has run on production.

Design: [docs/designs/todo-label-backlog/](../designs/todo-label-backlog/).
