# Folder Names Are Never a Label — Technical Design

Implements [functional.md](functional.md). Root cause and measurements: bug report 146.

## Data Model

No schema change. The backlog script deletes rows only:

- `library_track_labels` links to a label whose name is a folder name;
- `library_labels` rows with such a name that no `channels.label_id`, `label_external_ids.label_id`
  or `library_labels.parent_label_id` refers to.

Both are written to the script's JSON backup first and restored by `--rollback`.

## One predicate

`ImportQueue.is_placeholder_publisher(value)` (`services/common/import_queue.py`) is the one answer
to "is this publisher a folder's name". True for:

1. the queue's name, legacy and current (unchanged);
2. any value starting with `_` -- the same rule `is_label_folder` applies to folders;
3. `label_names.looks_like_release_folder(value)`: `[<CAT> [- ]]<one word with an underscore>-<year>[-<suffix>...]`.
   Matched all 371 polluted LMS labels and none of the 1,052 real labels in the muma DB.

Every path that derives, keeps or stores a label asks it:

| Path | Change |
|---|---|
| `LabelPath.split` (used by `LabelSong`, so by the tagger and the importer's Mover) | Returns no label when the first folder under the EPs root is not a label folder (`is_label_folder`) or is a placeholder; a release folder directly in the root keeps its catalogue number. The fallback outside the root does the same for the parent-of-parent. |
| `DropQueuePlaceholderRule` (`GenericSong`, `LabelSong`) | Empties such a publisher and the copyright computed from it on the next retag. |
| `channels.is_label` (scanner `_resolve_label_id`) | Refuses it, so no `library_labels` row is created. |
| `label_resolver._is_refused` (importer label proposals) | Refuses it in tags and in the `.nfo`. |

## Backlog script

`clear_folder_labels.py`, wrapped by `clear-folder-labels.sh`, runs in the
music-manager container (stdin). Candidates: LMS tracks under a polluted label, muma tracks linked
to one, every file under an underscore folder of the label tree (`--include-queue` adds the queue).
Keys per format: ID3 `TPUB`, `TXXX:publisher|label|organization`, `TCOP`; Vorbis `LABEL`,
`PUBLISHER`, `ORGANIZATION`, `COPYRIGHT`; MP4 `PUBL`, freeform `LABEL`/`PUBLISHER`, `cprt`. Only
polluted values are removed. The tagger alone cannot do this: it writes one publisher key per
format, and LMS prefers `LABEL` (= ID3 `TPUB`).

## API Contract

No endpoint changes.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| — | — | — | — |

## Cross-App Impact

None in code. LMS shows the result after the script's rescan request.

## Technical Acceptance Criteria

1. `LabelPathTest`, `LabelSongTest.NoLabelFolderTest`, `DropQueuePlaceholderRuleTest`,
   `import_queueTest`, `test_channels`, `test_importer_label_resolver` cover each path with the
   production names, and the real labels near the line stay labels.
2. `tests/unit/test_clear_folder_labels.py`: per format on real files; dry run writes nothing;
   apply writes the backup first; a second apply changes nothing; rollback restores tags and rows.

## Related Docs

- [Bug report 146](../../bug-reports/146-folder-names-stored-as-labels.md)
- [Bug report 087](../../bug-reports/087-todo-label-backlog.md), [030](../../bug-reports/030-todo-stamped-as-the-record-label.md)
