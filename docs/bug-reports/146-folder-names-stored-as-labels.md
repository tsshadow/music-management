# Folder names stored as record labels: `__Free&None`, `__TODO` and release folders

# status: fixed

# reported problem
The owner: "I want to get rid of publisher/label Free&None and TODO; they are side effects of how
I used to label, but they pollute a lot."

Measured on production on 2026-10-02, read-only (`lms.db` opened with `?mode=ro`, the muma
database through the read-only account, tags read inside the music-manager container):

- LMS (`label` + `release_label`): 231 releases labelled `__Free&None`, 5 `___Free&None`, 29
  `__TODO`. 371 of the 2,225 labels are a whole release folder's name, one release each (552
  tracks), for example
  `STH685RMXBP - Bassjackers_-_I_Fink_U_Freeky_(Coone_Remix)-(STH685RMXBP)-SINGLE-WEB-2026-SRG`.
- muma database: 398 `library_labels` rows shaped like a release folder, linked to 733 tracks. No
  underscore label: the scanner already refused `__TODO` and `__Free&none` (bug reports 030, 087),
  but not `___Free&None` or a release folder's name.
- Real labels close to the line must stay: `DWX Copyright Free`, `Freestyle`, `Free For All`,
  `Musical Freedom`, `I AM HARDSTYLE - Amplify`, `24 - 7 Hardcore`.

# Possible reason
Every one of these values is a folder name that was taken for the label because the label is read
from the folder a release is filed in (`<eps root>/<label>/<release>/<file>`). Per value:

**`__Free&None` -- still being written.** Production's `rules_catid_label` maps the catalogue id
`FREE` to `__Free&None`. The importer's Mover moves such a release to
`<eps root>/__Free&None/<release>/` (`services/importer/mover.py:254`) and then tags it with
`LabelSong` directly (`mover.py:110`, `post_processing_songs`). `LabelSong` took the first folder
under the EPs root as the publisher without asking whether it is a label
(`services/tagger/Song/LabelPath.py:19-23` before this fix) -- the tagger's own walk and
`detect_song_type` ask `ImportQueue.is_label_folder` and treat the folder as GENERIC, the Mover
does not go through them. Nothing removed it afterwards: `GenericSong` leaves a publisher alone and
`DropQueuePlaceholderRule` only knew the queue's name.

**`__TODO` -- old.** Bug report 030 (the tagger ran `LabelSong` over the queue). The tracks LMS
still lists under it are 71 FLACs, most of them filed in real label folders since.

Where the 689 LMS tracks under the three underscore values keep it: all 559 mp3s (every one under
`__Free&None`) in `TXXX:publisher`, the tagger's key; of the 130 FLACs, 38 in `PUBLISHER` (the
tagger's key) and 92 in `LABEL`, a key no MuMa code writes -- the owner's earlier, manual labelling,
which the 087 repair could not see because it reads what the tagger reads.

**Release folder names -- old values in a key the tagger never corrects.** All 552 tracks are mp3s,
and for all 552 the label equals the name of the folder the track sits in today. Their
`TXXX:publisher` -- the tagger's key -- already holds the right label (`247 Hardcore`,
`ABSLT Records`): the label-from-EPs-root fix and its backfill (0.24.0) repaired it. The release
folder name sits in `TPUB` (544) or `TXXX:LABEL` (8). LMS reads `LABEL`, `PUBLISHER`,
`ORGANIZATION` and takes the first one present
(`services/music-management-server/src/libs/audio/impl/taglib/TagReader.cpp:148`, `visitTagValues`
at :412), and TagLib maps an ID3 `TPUB` frame to `LABEL` -- so the stale frame wins over the
corrected publisher. MuMa's tagger wrote `publisher` to `TPUB` only in its first version
(commit 894aac7478, 2024-09-13); since 2024-09-29 (e2c017917f) it writes `TXXX:publisher` and only
ever registered `publisher_old` -> `TPUB` for reading. No code in this repository writes `TPUB`
today, so these frames are not MuMa's; `TXXX:LABEL` is what Mp3tag writes for its "LABEL" field.

The owner's hypothesis -- releases that sat one level deeper (`<label>/<release>/<release>/`,
552 such folders existed until the cleanup of 2026-09-06) and had the parent folder taken for the
label -- holds for the values, with one caveat about who wrote them. Every value carries the
`<CAT> - ` prefix the importer's renamer adds, so it was written after the import, and the Mover's
nesting bug produced exactly `<label>/<CAT - release>/<CAT - release>/` (same name inside), for
which counting two parents up from a file in the inner copy returns the release folder. It
explains the muma side completely (`TXXX:publisher`, repaired by the 0.24.0 backfill;
the 398 muma rows are links from media rows of files since moved or flattened, never replaced
because those tracks were not rescanned after links became replace-not-add). For the LMS side the
writer of `TPUB`/`TXXX:LABEL` is outside this repository, and since today's parent folder *is*
that outer folder, the data cannot tell a "parent of the inner copy" rule from a "containing
folder" rule. Either way the value is a folder's name, and nothing in MuMa ever touches `TPUB`.

Two live paths could create a release-folder label again: `LabelPath.split` returned the first
component even for a release folder sitting directly in the EPs root, and outside the root counted
two parents up (a nested copy gives the outer release folder). And the importer's label proposals
(`services/importer/label_resolver.py`) read `TPUB`/`LABEL` from a release's tags and refused only
an exact list of names, so a stale `TPUB` holding a folder name could be proposed -- and, once
confirmed, become a label folder of its own.

# solution
One predicate for "this publisher is a folder's name": `ImportQueue.is_placeholder_publisher`
(`services/common/import_queue.py`) now also answers true for a value starting with `_` (the rule
`is_label_folder` applies to folders) and for a value shaped like a scene release folder
(`services/common/label_names.py`: `[<CAT> [- ]]<one word with an underscore>-<year>[-<suffix>...]`,
which matched all 371 polluted LMS labels and none of the 1,052 real muma labels). Its users:

- `LabelPath.split` returns no label for a non-label folder (queue, `_` folder) and for a release
  folder in the label's place, inside and outside the EPs root; a release in the root keeps its
  catalogue number. `LabelSong` passes the configured queue. So the Mover writes an empty
  publisher for a release it files into `__Free&None`.
- `DropQueuePlaceholderRule` (run by `GenericSong` and `LabelSong`) empties such a publisher and
  the copyright computed from it on the next retag.
- `channels.is_label` refuses it, so the scanner creates no `library_labels` row.
- `label_resolver._is_refused` refuses it in tags and in the `.nfo`.

Decision recorded for the owner: a release in `__Free&None` gets **no** label (empty), not a
marker such as `Free`.

The backlog is `clear-folder-labels.sh` (wrapping `clear_folder_labels.py`,
run in the music-manager container): it removes these values from every label key per format --
ID3 `TPUB`/`TXXX:publisher|label|organization`, Vorbis `LABEL`/`PUBLISHER`/`ORGANIZATION`, MP4
`PUBL`/freeform -- plus the copyright computed from them, deletes the muma links and unreferenced
label rows, writes a JSON backup first, supports `--rollback`, and asks LMS to rescan. Dry run on
production, 2026-10-02: see the counts below.

- 3,374 candidate files read (LMS tracks under a polluted label, muma tracks linked to one, every
  file under `EPs/__Free&None`), 2 unreadable (a truncated wav and mp3 in `__Free&None`).
- **1,297 files would change.** Per value (files): `__Free&None` 1,286, a release folder's name
  614, `__TODO` 71, `___Free&None` 21. Per key: `TCOP` 613, `TXXX:publisher` 582, `TPUB` 575,
  FLAC `LABEL` 92, FLAC `COPYRIGHT` 61, FLAC `PUBLISHER` 61, `TXXX:LABEL` 8.
- **muma database:** 733 `library_track_labels` links and 398 `library_labels` rows.
- LMS releases at the time: 373 under a release folder name, 231 `__Free&None`, 29 `__TODO`,
  5 `___Free&None`.

Tests: `services/common/label_namesTest.py`, `services/tagger/Song/LabelPathTest.py`,
`LabelSongTest.NoLabelFolderTest`, `DropQueuePlaceholderRuleTest.FolderNamePublisherTest`,
`import_queueTest.FolderNamePlaceholderTest`, `services/tests/test_channels.py`,
`services/importer/tests/test_importer_label_resolver.py`, `tests/unit/test_clear_folder_labels.py`
-- all with the production names. Design: `docs/designs/folder-name-labels/`.
