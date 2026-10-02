# Folder Names Are Never a Label — Functional Design

## Overview

The label of a release is read from the folder it is filed in: `EPs/<label>/<release>/`. Three
kinds of folder sit in that position and are not a label: `__Free&None` (releases that have none),
the import queue (`__TODO`), and a release folder that ended up one level too high or too deep.
Each was written into files as their publisher, and LMS shows it as a label. On 2026-10-02 that
was 236 releases under `__Free&None`/`___Free&None`, 29 under `__TODO` and 371 "labels" that are
a release folder's name. The owner wants them gone and not coming back (bug report 146).

## User Stories

- As the owner, I want the label list in the player to hold only record labels, so that browsing
  by label is not drowned in folder names.
- As the owner, I want a release filed in `__Free&None` to have no label, so that "free" releases
  do not pretend to share one.
- As the owner, I want new imports never to produce such a label again.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The importer files a `FREE ...` release into `EPs/__Free&None/` | Its tracks have no label. |
| The tagger retags a track in `EPs/__Free&None/` that still says `__Free&None` | The label is removed. |
| A release folder sits directly in `EPs/`, or a release copy sits inside itself | The release folder's name is not used as a label; a real label folder above it still is. |
| A release in the import queue carries a folder name in its label tag | The label proposal ignores it and uses the next source. |
| The scanner reads a file whose publisher is such a name | No label is linked in MuMa. |
| A real label with "Free" in its name (`DWX Copyright Free`, `Freestyle`, `Free For All`, `Musical Freedom`) | Unchanged. |
| The owner runs `scripts/prod/person/clear-folder-labels.sh` | Dry run first; on `yes` the values are removed from the files and MuMa, LMS rescans; `--rollback` undoes it. |

## Acceptance Criteria

1. After the release and the script run, LMS shows no release labelled `__Free&None`,
   `___Free&None` or `__TODO`, and no label shaped like a release folder.
2. A release imported afterwards into `__Free&None` shows no label.
3. The labels named in the last row of the table above still exist and keep their releases.

## Open Questions / Not Yet Decided

- **Marker instead of empty.** `__Free&None` releases now get no label at all. The alternative is a
  visible marker such as `Free`. Defaulted to empty; the MR asks the owner. A marker would be a
  one-line change in `LabelPath.split` plus a different action in the script.
