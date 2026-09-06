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


def is_same_release(src, dst):
    """Whether the two folders hold the same files. Unreadable means "different".

    Hashing a release is minutes of NAS I/O per folder on every import cycle, so the
    comparison is file names and sizes -- two scene rips that agree on every name and every
    byte count are the same release for the purpose of deciding whether a duplicate download
    can go. Being wrong in the lenient direction costs a duplicate; being slow costs the
    import.
    """
    try:
        return folder_entries(src) == folder_entries(dst)
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
