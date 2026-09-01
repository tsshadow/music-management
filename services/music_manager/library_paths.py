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
    seen = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]
