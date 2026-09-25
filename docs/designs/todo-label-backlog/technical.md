# `__TODO` Label Backlog — Technical Design

Implements [functional.md](functional.md). Bug report 087.

## Data Model

No schema change.

- `tagger_processed_files`: the repair pages it by primary key (`filepath`, `utf8mb4_bin`) with one
  range per root (`<root>/` ≤ filepath < `<root>0`) — `ProcessedFilesHelper.paths_under`. Never a
  join; never a full scan. Queued rows get `needs_rescan = TRUE, rescan_reason = 'todo_label_repair'`
  through the existing `mark_paths_for_rescan`.
- `rules_label_proposals.folder`: the rename tool moves a row to the new folder name (only when no
  row holds the new name yet).
- `rules_catid_label`: read only, keyed on the prefix `Mover.get_cat_id` extracts.

## The shared predicate

`services/common/import_queue.py`, `ImportQueue`:

| Member | Meaning |
|---|---|
| `from_settings(settings)` | `import_folder_path`, else `<eps_folder_path>/__TODO` (the default is unchanged). |
| `contains(path)` | path is the queue or below it. |
| `lies_within(root)` | the queue sits inside `root` (true today for the EPs root). |
| `is_label_folder(folder)` | not the queue, and not an underscore folder (`__Free&None`). |
| `is_placeholder_publisher/copyright(value)` | the legacy name or the queue's current name (and `"<that> (<year>)"`). |

Adopted by every walker that derives a label from the label tree: `Tagger._parse_label_folders`,
`detect_song_type`, `Tagger._queue_new_library_files` / `_parse_import_queue` (walk the queue as
GENERIC once it no longer lies inside the EPs root), `channels.is_label` and
`channels.path_can_carry_a_label` (the hard-coded `import` root is gone), `label_resolver.blacklist`,
`tools/fix_nested_ep_dirs.find_cases`, `scripts/backfill_label_from_path.py`.

Deliberately not adopted: `backfill_release_dates`, `seed_scene_group_date_formats`,
`backfill_original_artist_from_nfo` read release *content* (NFO dates, artist credits), which is as
valid for a queued release as for a filed one; `scripts/restructure_music_folders.py` is the
migration whose input *is* the legacy location; the deprecated ml-analyzer.

`tests/ci/test_import_queue_predicate.py` fails on any non-docstring string literal containing
`__todo` outside `import_queue.py` (and the allow-listed migration), and checks that each walker
above imports the module.

## Tagger change

`DropQueuePlaceholderRule` empties a placeholder publisher/copyright. It runs first in
`GenericSong.parse` (before the copyright fallback to the publisher) and `LabelSong.parse` (before
the "compute a copyright when absent" check). Emptying rather than deleting makes
`BaseSong.save_file` see the change and drop the frame.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/tagger/todo-label-repair` (admin) | `after` (cursor, default ''), `limit` 1–2000 (default 300) | `{mode: "dry-run", reason, roots, scanned, poisoned, by_area, by_field, by_label, poisoned_paths, undecidable_count, undecidable[≤200], queued: 0, next_after, done}` | 401 no key, 403 not admin, 422 bad limit, 500 database unreachable (never an empty "done" page) |
| `POST /api/tagger/todo-label-repair` (admin) | same | same, `mode: "apply"`, `queued` = files handed to the tagger queue | same |

Additive; no consumer changes. Both are plain `def` (tag reads over CIFS stay off the event loop).

Derivation per poisoned file: in a label folder → that folder (what LabelSong writes); in the queue
→ `label_resolver.resolve(<queue>/<release>, import_folder_name=<queue name>)`, cached per release,
undecidable when it proposes nothing; in an underscore folder → no label.

## Rename planner

`services/importer/catid_prefix_repair.py`, run in a container with `/mnt/music` and the database:
`python -m services.importer.catid_prefix_repair --dry-run|--apply --log F|--rollback F`.
`plan_one` tries the proposal's `catid`, then name tokens (parenthesised groups, letter+digit
words); a candidate counts only when `get_cat_id("<candidate> x")` is a key of `rules_catid_label`.
Two different rule labels → ambiguous; a `decided_label` that disagrees → refused; a target name
that exists → refused. Apply: `os.rename` inside the queue, JSON line appended and flushed, proposal
row moved, LMS notified — per folder, in that order.

## Cross-App Impact

None. Backend only.

## Technical Acceptance Criteria

1. `TodoLabelRepair.run_page(apply=False)` never calls `mark_paths_for_rescan`; `apply=True` calls
   it once per page with every poisoned path and `REASON`.
2. The resolver is called once per queued release per page, with the queue's current name.
3. `paths_under` issues one ranged SELECT with no JOIN, and raises on a database error.
4. With `import_folder_path` outside the EPs root, `detect_song_type` returns GENERIC for a queue
   file, the queue is a root for new library files and is walked as GENERIC.
5. The CI predicate check fails when a new module adds a `'__TODO'` literal.
6. The planner refuses junk/UPC catalogue numbers, ambiguous names, decided-label conflicts and
   existing targets; apply + rollback round-trip a folder name.

## Related Docs

- [Bug report 030](../../bug-reports/030-todo-stamped-as-the-record-label.md),
  [bug report 087](../../bug-reports/087-todo-label-backlog.md)
- Operator scripts (not in the repository): `/tmp/muma-person/repair-todo-label-backlog.sh`,
  `move-import-queue.sh`, `repair-empty-catid-names.sh`.
