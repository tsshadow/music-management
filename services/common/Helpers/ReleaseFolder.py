"""Moving a release folder into the place it belongs, without eating it.

`shutil.move(src, dst)` does not fail when `dst` is an existing directory: it moves `src`
*into* it. A second copy of a release therefore lands at `dst/<same name>/`, one level
deeper, and stays there -- and because that is not an error, nothing said so. 552 release
folders on production contain themselves this way.

The importer's mover learned that on 2026-09-04. It was not the only caller: confirming a
label proposal moves a folder too, with the same call and no check, and lives in the
music-manager image where `services.importer` is not installed. So the rule moved down
here, where both can reach it, rather than being written a second time and fixed a second
time later.

Nothing here deletes. `move_release_folder` reports what it found and the caller decides,
because "this is a duplicate download, drop it" is a policy an import cycle may hold and
an API request answering a person should not.
"""

import logging
import os
import shutil
from os.path import join, relpath

import mutagen

#: `src` was moved to `dst`.
MOVED = 'moved'
#: `dst` exists and holds the same files: `src` is a duplicate download.
DUPLICATE = 'duplicate'
#: `dst` exists and holds something else. Both are left where they are.
CONFLICT = 'conflict'


def folder_entries(path):
    """Every file under `path` as relative name -> size, Synology thumbnails aside."""
    entries = {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != '@eaDir']
        for name in files:
            full = join(root, name)
            entries[relpath(full, path)] = os.path.getsize(full)
    return entries


#: What counts as a track when two release folders are compared. Everything else in a
#: release -- the .nfo, the .sfv, a cover, a Synology thumbnail -- is left out: the
#: library copy gains or loses those on its own (artwork backfill, LMS, a curator), and
#: none of them says whether the music is the same.
AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.wav', '.ogg', '.opus', '.aif', '.aiff')

#: How far two readings of one track's length may drift apart and still be the same
#: track. An MP3's length is an estimate from its frame header, and a tag rewrite can
#: move the first audio frame; a second is far below any real difference between two
#: rips or two edits of a track.
DURATION_TOLERANCE_SECONDS = 1.0


def audio_length(path) -> float | None:
    """The playing time of one audio file in seconds, or None when it cannot be read.

    Reached through `mutagen.File` rather than a from-import, like `label_resolver`
    does: the unit suite replaces mutagen with a stub that has no `File`, and this has to
    degrade to "unknown" there rather than fail at import time.
    """
    try:
        audio = mutagen.File(path)
    except Exception as e:  # noqa: BLE001 - an unreadable file is data, not a crash
        logging.debug('Could not read the length of %s: %s', path, e)
        return None
    length = getattr(getattr(audio, 'info', None), 'length', None)
    if isinstance(length, int | float) and not isinstance(length, bool) and length > 0:
        return float(length)
    return None


def track_list(path) -> list[str]:
    """Every audio file under `path` as a relative name, Synology thumbnails aside."""
    return sorted(name for name in folder_entries(path) if name.lower().endswith(AUDIO_EXTENSIONS))


def _same_track(src, dst) -> bool:
    """Whether two files with the same relative name hold the same recording.

    By length when both can be read. Byte size is useless here: the tagger rewrites the
    library copy right after the move, so the copy that was imported and a later download
    of the same release differ in size as soon as the new tags no longer fit the padding
    of the old ones. When neither length can be read the sizes are all there is; when only
    one can, they are not the same kind of file and count as different.
    """
    src_length, dst_length = audio_length(src), audio_length(dst)
    if src_length is not None and dst_length is not None:
        return abs(src_length - dst_length) <= DURATION_TOLERANCE_SECONDS
    if src_length is None and dst_length is None:
        return os.path.getsize(src) == os.path.getsize(dst)
    return False


def is_same_release(src, dst):
    """Whether the two folders hold the same release. Unreadable means "different".

    The same track list -- every audio file by relative name -- with every track the
    same length, give or take `DURATION_TOLERANCE_SECONDS`. Hashing a release is minutes
    of NAS I/O per folder, and comparing byte sizes, which this used to do, is wrong for
    the one comparison that matters most: the copy already in the library has been
    tagged since it arrived, so a second download of it never matched and was logged as
    a conflict needing manual intervention on every import cycle.

    Two different rips that agree on every name and every length count as the same
    release. Being wrong in that direction parks a folder in the quarantine, where it
    can be recovered; being slow costs the import. A folder without any audio is
    compared by its file names and sizes, as before.
    """
    try:
        src_tracks, dst_tracks = track_list(src), track_list(dst)
        if not src_tracks and not dst_tracks:
            return folder_entries(src) == folder_entries(dst)
        if src_tracks != dst_tracks:
            return False
        return all(_same_track(join(src, name), join(dst, name)) for name in src_tracks)
    except OSError as e:
        logging.warning('Could not compare %s with %s (%s); treating them as different', src, dst, e)
        return False


def move_release_folder(src, dst):
    """Moves `src` to `dst` unless something is already there. Returns what happened.

    The check is before the move rather than around it: `shutil.move` only raises once the
    nested copy exists too, which is the *third* import of the same release. The first two
    succeed quietly and leave a folder inside itself.
    """
    if os.path.exists(dst):
        if is_same_release(src, dst):
            return DUPLICATE
        return CONFLICT
    shutil.move(src, dst)
    return MOVED
