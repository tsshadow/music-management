# `__TODO` Stamped As The Record Label

# status: fixed

# reported problem
Files in the library carry `TXXX:publisher = __TODO` — the name of the import queue — instead of a
record label. Five of 25 files sampled on production on 2026-08-19 had it. The label-proposal work
blacklisted the value so it could not poison new proposals, but the note left behind said the root
cause was never found.

# Possible reason
It was found on 2026-08-21, by reading the paths rather than the tagger.

**The import folder lives inside the folder that gets scanned for labels.** From `.env.example`:

```
music_folder_path=/mnt/music
eps_folder_path=/mnt/music/EPs
import_folder_path=/mnt/music/EPs/__TODO
```

`Tagger._parse_label_folders()` iterates every directory under `eps_folder_path` and treats each one
as a record label. `__TODO` is one of those directories.

**`LabelSong` takes the publisher from the grandparent folder name** (`LabelSong.py:22-23`):

```python
paths = path.rsplit(s.delimiter, 2)
self._publisher = str(paths[0].split(s.delimiter)[-1])
```

For a file at `/mnt/music/EPs/__TODO/<release>/<track>.mp3` that is literally `__TODO`.

So every file waiting in the import queue that a label scan reached had the queue's own name written
into it as its record label. Nothing had to go wrong for this to happen; it was the normal path.

**It was already fixed, by accident of a different change.** The condition

```python
song_type = SongTypeEnum.LABEL if not label.name.startswith('_') else SongTypeEnum.GENERIC
```

landed on 2026-07-28 (release 0.0.7) and stops it, as does the matching check in `TagSingleFile`.
The files sampled three weeks later are residue from before that, not evidence of an ongoing leak.

# solution
The cause needed no code change — but it was protected by one condition in one expression, in two
places, with nothing saying why. Remove either and the poisoning resumes silently, and the symptom
would take another three weeks and a production sample to notice.

`ImportFolderTest` in `services/tagger/TaggerTest.py` pins it: an underscore folder is scanned as
GENERIC, an ordinary label folder still as LABEL, and `TagSingleFile` agrees with the folder scan —
two independent decisions implementing one rule, which have drifted apart once already.

Verified by removing the guard and watching the test fail, then restoring it.

**Still open, and it is data rather than code:** the files already carrying `__TODO` as their
publisher. Repairing them means re-deriving the label from the folder they now live in and
rewriting the tag, which needs access to the library. The resolver's blacklist keeps them from
poisoning label proposals in the meantime.

**Worth considering separately:** the import queue sits inside the tree that gets scanned for
labels. Every scanner that walks `EPs/*` has to know to skip it, and each one is a place to forget.
Moving the queue outside `eps_folder_path` would remove the class of bug rather than this instance
of it.
