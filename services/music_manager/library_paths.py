"""How one file is spelled on both sides of the LMS boundary.

The same file goes by two names depending on who is talking about it. LMS reports paths
under its own media-library root (prod: /music), muma stores them under the mount it
scans (/mnt/music). A lookup that knows only one of the two never matches.

Shared rather than duplicated: the rating webhook and the version sync both join on the
path, and two copies of this would drift.
"""

import os

LMS_MUSIC_ROOT = (os.getenv('LMS_MUSIC_ROOT') or '/music').rstrip('/')
MUMA_MUSIC_ROOT = (os.getenv('MUMA_MUSIC_ROOT') or '/mnt/music').rstrip('/')


def candidate_paths(path: str) -> list[str]:
    """Every spelling of `path` worth looking up, the one we were given first."""
    relative = path
    for root in (MUMA_MUSIC_ROOT, LMS_MUSIC_ROOT):
        if path.startswith(root + '/'):
            relative = path[len(root) + 1 :]
            break
    candidates = [path, f'{MUMA_MUSIC_ROOT}/{relative}', f'{LMS_MUSIC_ROOT}/{relative}', relative]
    return list(dict.fromkeys(candidates))


def server_candidate_paths(path: str) -> list[str]:
    """The same spellings as `candidate_paths`, but the server's own one first.

    Every spelling costs an indexed lookup, and a pass that reads a fact *out of* the servers
    does one per media file per server -- 352.977 files against two databases on production.
    Trying muma's own mount first, as `candidate_paths` does, misses every single time and
    doubles that. This is the same list, reordered; nothing is added or dropped, so a path that
    resolves under one order resolves under the other.
    """
    candidates = candidate_paths(path)
    relative = path
    for root in (MUMA_MUSIC_ROOT, LMS_MUSIC_ROOT):
        if path.startswith(root + '/'):
            relative = path[len(root) + 1 :]
            break
    server_first = f'{LMS_MUSIC_ROOT}/{relative}'
    return [server_first] + [c for c in candidates if c != server_first]


def relative_path(path: str | None) -> str | None:
    """`path` with whichever library root it carries stripped off.

    What a client is given when it has to name a file to LMS -- the feeds hand a path to
    `getSongsByPath`, which resolves it against its own media library roots. Sending muma's
    absolute path instead would name a file LMS does not have, and sending LMS's spelling
    would bake this deployment's mount into the client.

    A path under neither root is returned unchanged: it is still the best name anyone has
    for that file, and the server answers by finding nothing rather than by failing.
    """
    if not path:
        return path
    for root in (MUMA_MUSIC_ROOT, LMS_MUSIC_ROOT):
        if path.startswith(root + '/'):
            return path[len(root) + 1 :]
    return path


def server_path(path: str) -> str:
    """`path` as the server spells it, for a row muma writes into the server's own database.

    The reverse of reading: `candidate_paths` guesses because a path from LMS may come in any
    spelling, but a path muma *writes* into lms.db has to be the one LMS will look for -- the
    file seen through LMS's own mount. A portrait stored as /mnt/music/artists/... named a file
    LMS does not have, so every library scan removed it as missing and the hourly sync wrote it
    back: about 20,000 rows, 0.2 s each, every scan (bug report 138).

    A path under neither root is returned unchanged; one already under LMS's root is too.
    """
    if path.startswith(MUMA_MUSIC_ROOT + '/'):
        return f'{LMS_MUSIC_ROOT}/{path[len(MUMA_MUSIC_ROOT) + 1 :]}'
    return path


def local_path(path: str) -> str:
    """`path` as muma spells it, for a path a server sent: the reverse of `server_path`.

    LMS names a file through its own mount (/music/...). The tagger and the scanner open it
    through muma's (/mnt/music/...), and under LMS's spelling they find nothing.

    A path under neither root is returned unchanged; one already under muma's root is too.
    """
    if path.startswith(LMS_MUSIC_ROOT + '/'):
        return f'{MUMA_MUSIC_ROOT}/{path[len(LMS_MUSIC_ROOT) + 1 :]}'
    return path


class OutsideLibrary(ValueError):
    """A caller named a file that lies outside every library root muma manages."""


def library_roots(settings=None) -> list[str]:
    """The folders a caller may name a file in: the music root, the EPs root and the import queue.

    Resolved with realpath, so a symlink cannot make a root look like somewhere else. An
    empty setting is no root: with none configured at all, no path is inside.
    """
    from services.common.config_store import ConfigStore
    from services.common.import_queue import ImportQueue

    settings = settings or ConfigStore()
    candidates = [
        settings.music_folder_path,
        settings.eps_folder_path,
        ImportQueue.from_settings(settings).path,
    ]
    return list(dict.fromkeys(os.path.realpath(root) for root in candidates if root))


def resolve_in_library(path: str, settings=None) -> str:
    """`path` resolved (symlinks, `..`) and checked against `library_roots`.

    Raises OutsideLibrary when the resolved path is not a root or below one. The routes that
    tag or scan a named file call this first: the tagger writes tags into any audio file it
    can open, so a path from a request is only accepted inside the library.
    """
    resolved = os.path.realpath(path)
    for root in library_roots(settings):
        if resolved == root or resolved.startswith(root.rstrip(os.sep) + os.sep):
            return resolved
    raise OutsideLibrary(f'{path} is not inside the music library')


def require_library_file(path: str) -> str:
    """`resolve_in_library` for a route: muma's spelling of `path`, or HTTP 400 when it is outside.

    A path in LMS's spelling is translated first, so LMS can name a file the way it sees it.
    """
    from fastapi import HTTPException

    try:
        return resolve_in_library(local_path(path))
    except OutsideLibrary as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
