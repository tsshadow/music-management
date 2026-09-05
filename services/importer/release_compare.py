"""Whether two release folders hold the same release.

Both steps that move a folder need this and neither can afford to be slow about it: the renamer
when its target name is taken, the mover when the label folder already has that release. Hashing a
release is minutes of NAS I/O per folder on every import cycle, so the comparison is file names and
sizes -- two scene rips that agree on every name and every byte count are the same release for the
purpose of deciding whether a duplicate download can go. Being wrong in the lenient direction costs
a duplicate; being slow costs the import.
"""

import logging
import os
from os.path import join, relpath


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
    """Whether the two folders hold the same files. Unreadable means "different"."""
    try:
        return folder_entries(src) == folder_entries(dst)
    except OSError as e:
        logging.warning('Could not compare %s with %s (%s); treating them as different', src, dst, e)
        return False
