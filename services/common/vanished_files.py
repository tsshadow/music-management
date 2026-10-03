"""Deciding which library files are gone from disk, without mistaking an unmounted share for that.

A `library_media_files` row outlives its file when a release folder moves or is deleted (GitLab
issue #170). Two callers decide which rows that is: the scanner after every full walk
(services/music_manager/vanished_media.py) and the operator script
scripts/prod/person/stale_media_rows.py (`--gone`). Both use the guards here, so a share that is
not mounted stops both the same way instead of making every row look gone:

* a library root (`/mnt/music/EPs`, the first three path components) that is missing or empty
  stops the pass;
* a folder that cannot be listed for any reason other than not existing stops the pass;
* more than MAX_GONE_SHARE of the rows looking gone stops the pass.

"Gone" is read from a listing of the folder, not from a stat per file: a folder that does not
exist, or a folder without the file.
"""

from __future__ import annotations

import errno
import os

#: A pass that finds more than this share of the rows gone stops: that is a share that is not
#: mounted, not a library that moved. On production 2026-10-03: 8,372 of 354,203 (2.4%).
MAX_GONE_SHARE = 0.10


class LibraryUnreadable(RuntimeError):
    """A library root is missing or empty, or a folder could not be listed: no row is called gone."""


def list_dir(folder: str) -> set[str] | None:
    """The names in `folder`; None when the folder does not exist. Any other error is raised."""
    try:
        return set(os.listdir(folder))
    except OSError as error:
        if error.errno in (errno.ENOENT, errno.ENOTDIR):
            return None
        raise LibraryUnreadable(f'cannot list {folder}: {error}') from error


def library_root(path: str, music_root: str | None = None) -> str:
    """The library folder a path belongs to: the first folder below `music_root`.

    A file directly in `music_root` belongs to `music_root` itself. Without `music_root`, the
    first three components (`/mnt/music/EPs`), which is that folder on production, where the
    music root is `/mnt/music`.
    """
    if music_root:
        base = music_root.rstrip('/')
        if path.startswith(base + '/'):
            first, slash, _rest = path[len(base) + 1 :].partition('/')
            return f'{base}/{first}' if slash else base
    return '/'.join(path.split('/')[:4])


def gone_paths(paths: list[str], music_root: str | None = None) -> set[str]:
    """The paths whose file is not in its folder, each folder listed once.

    Stops with LibraryUnreadable when a library root (see `library_root`) is missing or empty, or
    a folder cannot be listed: an unmounted share must not make every row look gone. A path that
    is not absolute (production has one row holding `--help`) names no file in the library and is
    gone.
    """
    absolute = [path for path in paths if path.startswith('/')]
    for root in sorted({library_root(path, music_root) for path in absolute}):
        if not list_dir(root):
            raise LibraryUnreadable(f'library root {root} is missing or empty, is the share mounted?')
    listings: dict[str, set[str] | None] = {}
    gone = {path for path in paths if not path.startswith('/')}
    for path in absolute:
        folder, name = os.path.split(path)
        if folder not in listings:
            listings[folder] = list_dir(folder)
        listing = listings[folder]
        if listing is None or name not in listing:
            gone.add(path)
    return gone


def check_gone_share(gone: int, total: int) -> None:
    """Raise LibraryUnreadable when more than MAX_GONE_SHARE of `total` rows look gone."""
    if total and gone > MAX_GONE_SHARE * total:
        raise LibraryUnreadable(f'{gone} of {total} rows look gone -- more than {MAX_GONE_SHARE:.0%}')


def path_exists(path: str) -> bool:
    """Whether anything is at `path` now, a dangling link included: the last check before a delete."""
    return os.path.lexists(path)
