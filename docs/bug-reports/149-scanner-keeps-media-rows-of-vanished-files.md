# The Scanner Keeps The Media Row Of A File That Is Gone From Disk

# status: fixed

# reported problem
Nothing deleted a `library_media_files` row when its file disappeared from disk. A release folder
that moved or was deleted left its rows behind, with the right hash and no file. On production on
2026-10-03, 8,372 of 354,222 media rows had no file: 8,250 below `EPs/` (mostly old
`EPs/__TODO/` paths from before the import queue moved), 96 Youtube, 24 Soundcloud, 1 Telegram.
7,453 belonged to a track that still had another file. 919 left their track without a file or had
no track (GitLab issue #170). Track 9748566 is an example: one row at its old `__TODO` path (file
gone) and one at its B2S path (live).

# Possible reason
The scanner only adds and updates rows. `process_file` runs for each file the walk finds, and a
file that is not there is never visited, so its row is never looked at again. The scanner design
listed deleted and moved files as an open question.

# solution
After each full walk, `ScannerManager.run_full` calls `vanished_media.drop_vanished_media` with the
set of paths the walk saw. A row under the music root that the walk did not see is a candidate. A
listing of its folder decides if the file is gone. The guards come from
`services/common/vanished_files.py`, which `stale_media_rows.py --gone` now
imports instead of a copy:

- a library folder that is missing or empty (an unmounted share) stops the pass;
- a folder that cannot be listed stops the pass;
- more than 10% of the rows gone stops the pass.

Each gone row is locked, re-checked and deleted, one transaction per track. The track row is never
deleted: ratings key on `track_uid` and listens on the track id. A track that lost its last file
is relinked when the `relink-orphans` metadata key finds exactly one successor (a file moved and
retagged). Any other fileless track stays for `POST /api/scanner/relink-orphans` and
`purge-orphans`. A move with unchanged tags keeps its track, because the walk already gave the new
path a row on the same track.

Config `scanner_drop_vanished_media` is off by default, so the first deploy removes nothing. The
backlog goes through `merge-stale-media-rows.sh --gone` first, with its JSON
backup. Then a curator switches the pass on in Beheer > Config.

Tests: `services/music_manager/tests/test_vanished_media.py` (a normal vanish, an unmounted share,
a missing root, an unreadable folder, the 10% brake, a move, a move with a retag, a file that came
back, rows with a wrong hash or outside the root, the switch) and
`tests/integration/test_track_relink.py` (the same move, retag and delete against MariaDB).
Design: `docs/designs/scanner/technical.md`, section "Vanished files".
