"""Whether a release folder in the import queue has stopped changing.

The extractor has always skipped an archive a browser is still writing (its in-flight
suffixes), but nothing did the same for a *folder*. A release copied into `__TODO` over
SMB arrives one file at a time, and the flattener, renamer and mover all acted on
whatever was there when they looked: a folder renamed under the copy that was still
filling it, or moved to its label with half its tracks, the rest arriving afterwards in
a fresh `__TODO` folder that the mover then called a conflict.

The rule is age, not completeness, because nothing on disk says "complete": a folder
counts as settled once nothing inside it -- no file and no sub-directory -- has been
modified for `settle_seconds()`. Directories count as well as files because a copy tool
that restores each file's original modification time when it closes it (Windows
Explorer does, over SMB) leaves the finished files looking old; the directory a new
entry was just created in cannot be backdated that way until the very end.

Modification time and not change time: the archive backends restore the timestamps
stored in the archive, so a release just extracted from a complete archive is usually
placed in the same cycle. Its change time would be "now" and would delay every
extraction by a full cycle. A backend that does not restore a folder's time costs that
one cycle, which is the price of the guard, not a failure -- the extraction itself is
already complete by then (see the extractor's staging folder).
"""

import logging
import os
import time
from os.path import join
from typing import Final

from services.common.config_store import ConfigStore as Settings

#: How long a release folder must sit untouched before the importer acts on it.
DEFAULT_SETTLE_MINUTES = 5

SYNOLOGY_FOLDER = '@eaDir'

# The extractor unpacks every archive into a fresh folder of this name *inside* the
# import folder -- the same filesystem, so moving the result in is a rename and not a
# copy -- and only a complete extraction is moved out of it. It used to extract into the
# import folder itself: when unrar-free gave up after 13 of 44 releases the 13 stayed,
# the fallback backend extracted the whole archive on top of them (7z's `-aou` turning
# every collision into a `name_1.mp3`), and the flattener, renamer and mover of the same
# cycle placed whatever lay there. Those three skip this prefix.
STAGING_PREFIX: Final = '.muma-extract-'


def is_staging(name: str) -> bool:
    """Whether an import-folder entry is the extractor's work in progress, never a release."""
    return name.startswith(STAGING_PREFIX)


def settle_seconds() -> int:
    """The configured settle window in seconds, `import_settle_minutes` in ConfigStore.

    Falls back to the default for anything that is not a non-negative whole number,
    including the stubbed settings object the unit suite hands out. Zero switches the
    guard off, which is what a test stack that drops finished folders wants.
    """
    try:
        minutes = int(getattr(Settings(), 'import_settle_minutes', DEFAULT_SETTLE_MINUTES))
    except (TypeError, ValueError):
        return DEFAULT_SETTLE_MINUTES * 60
    if minutes < 0:
        return DEFAULT_SETTLE_MINUTES * 60
    return minutes * 60


def newest_mtime(path: str) -> float:
    """The most recent modification time of `path` itself or anything below it.

    Synology's thumbnail folders are skipped: the NAS writes them on its own schedule and
    they say nothing about whether the release is still arriving. Raises OSError when
    `path` itself cannot be read.
    """
    newest = os.stat(path).st_mtime
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != SYNOLOGY_FOLDER]
        for name in dirs + files:
            try:
                newest = max(newest, os.lstat(join(root, name)).st_mtime)
            except OSError:
                # Vanished between the listing and the stat: something is still
                # working in here, which is itself a reason to wait.
                return time.time()
    return newest


def folder_signature(path: str) -> str | None:
    """What a release folder looks like from the outside: entries, total size, newest mtime.

    One walk of `stat` calls -- the walk `newest_mtime` makes -- and no file is opened.
    The mover compares it before deciding whether an unplaceable folder's tags need to be
    read again: a file added, removed, replaced or rewritten changes at least one of the
    three. Returns None when anything under `path` cannot be read, which the caller
    treats as "changed" -- the safe direction, it only costs a re-read.
    """
    try:
        newest = os.stat(path).st_mtime
    except OSError:
        return None
    entries = 0
    total_size = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != SYNOLOGY_FOLDER]
        for name, is_file in [(d, False) for d in dirs] + [(f, True) for f in files]:
            try:
                info = os.lstat(join(root, name))
            except OSError:
                return None
            entries += 1
            newest = max(newest, info.st_mtime)
            if is_file:
                total_size += info.st_size
    return f'{entries}:{total_size}:{newest!r}'


def is_settled(path: str, min_age_seconds: int | None = None, now: float | None = None) -> bool:
    """Whether nothing under `path` changed within the last `min_age_seconds`.

    `min_age_seconds` defaults to `settle_seconds()`. A path that cannot be read counts as
    not settled: the caller skips it this cycle and looks again next time, which is the
    safe direction for every step that uses this. Logs the skip at DEBUG, because with a
    copy in progress it repeats every cycle and is not news.
    """
    window = settle_seconds() if min_age_seconds is None else min_age_seconds
    if window <= 0:
        return True
    try:
        newest = newest_mtime(path)
    except OSError as e:
        logging.debug('Not touching %s yet: it cannot be read (%s)', path, e)
        return False
    age = (time.time() if now is None else now) - newest
    if age < window:
        logging.debug('Not touching %s yet: it changed %.0fs ago, under the %ds settle window', path, age, window)
        return False
    return True
