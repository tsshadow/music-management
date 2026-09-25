- **Files stamped `__TODO` as their record label can now be repaired, and the fixed tagger stops
  creating new ones.** GenericSong fell back to the publisher for a copyright, so a release waiting
  in the import queue still got `copyright = __TODO`; LabelSong kept an old `__TODO (2021)` copyright
  after filing. Both now empty the placeholder first. `GET|POST /api/tagger/todo-label-repair` pages
  the label tree (primary-key ranges, no join), counts poisoned files per label derived from their
  folder -- the importer's resolver for files still in the queue -- lists the undecidable ones, and
  queues the rest for the tagger under reason `todo_label_repair`. Bug report 087.
- **The import queue's location is one setting.** Every walker of the label tree asks one predicate
  (`ImportQueue`) instead of checking for `__TODO` or a leading underscore itself, and a CI test
  refuses a new hard-coded `__TODO`. Moving the queue out of `EPs/` is now `import_folder_path` plus
  a folder move; the tagger keeps tagging it as generic songs wherever it lives.
- **Crooked ` - ` import folder names get a rename tool.** `python -m
  services.importer.catid_prefix_repair` plans a catalogue-number prefix only where the number routes
  to a label in `rules_catid_label`, with a rename log and rollback. On production that is at most ~27
  of 2.613; the rest need a label decision.

<!-- release notes -->

- **Files that still said `__TODO` as their label can be repaired**, and new ones are no longer
  created. The import queue's location is now a single setting, and crooked import folder names
  whose catalogue number is known can be renamed (with rollback).
