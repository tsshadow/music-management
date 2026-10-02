"""What a release folder's name looks like, so it is never mistaken for a record label.

The label tree is `<eps root>/<label>/<release>/<file>`, and every component that derives a label
from a path takes a folder name for one. Whenever the depth was off by one, the release folder was
taken instead: a scene release that shipped a copy of itself one level deeper, or a release that
sat directly in the root. 371 of the 2,225 labels in production LMS on 2026-10-02 were such names,
each on about one release (bug report 146):

    STH685RMXBP - Bassjackers_-_I_Fink_U_Freeky_(Coone_Remix)-(STH685RMXBP)-SINGLE-WEB-2026-SRG
    ROTC23 DJ_Paul_-_The_Nightmare_Series-(ROTC23)-CD-1999

A scene release name is one word -- underscores instead of spaces -- ending in a year and,
optionally, dash-separated suffixes (`-WEB-2026-SRG`, `-WEB-FLAC-2026`), optionally preceded by the
catalogue number the importer's renamer puts in front of it (`<CAT> - `). A label name has spaces
(`I AM HARDSTYLE - Amplify`, `24 - 7 Hardcore`) or no year (`Rude_Records`), so the pattern below
matched none of the 1,052 real labels in the muma database on that day.
"""

from __future__ import annotations

import re

#: `[<catalogue number> [- ]]<one word with an underscore>-<year>[-<suffix>...]`.
_RELEASE_FOLDER = re.compile(r'^(?:\S+ (?:- )?)?\S*_\S*-(?:19|20)\d{2}(?:-[A-Za-z0-9_]+)*$')


def looks_like_release_folder(value: str | None) -> bool:
    """Whether `value` is shaped like a scene release folder's name rather than a label's."""
    if not isinstance(value, str):
        return False
    return bool(_RELEASE_FOLDER.match(value.strip()))
