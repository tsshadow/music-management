"""Replaces a CATALOGNUMBER that holds the whole release folder name (issue #172).

Before bug report 145, `LabelPath.catalog_number` returned a release folder name without a space
as it was, so the tagger wrote a whole scene name as the catalogue number:
`D-Teq_-_Dark_Energy-(BIR030)-WEB-2011-HB`. Since then it returns '' for such a name and LabelSong
writes nothing, so nothing took the old value out either. On production 348 releases still held
one on 2026-10-03.
"""

from __future__ import annotations

import os

from services.common import release_nfo
from services.common.catalogue_number import comparable, from_folder_name
from services.tagger.constants import CATALOG_NUMBER
from services.tagger.Song import LabelPath
from services.tagger.Song.rules.TagRule import TagRule


def stale_values(release_folder: str) -> set[str]:
    """The values a stale tag can hold: the folder name, and the name after its `<number> - ` prefix."""
    values = {release_folder.strip()}
    if ' - ' in release_folder:
        values.add(release_folder.split(' - ', 1)[1].strip())
    return {value for value in values if value}


def release_directory(path: str, release_folder: str) -> str:
    """The release folder above `path`, its outermost copy: a scene release may hold a second copy of itself."""
    found = ''
    directory = os.path.dirname(path)
    while directory and os.path.dirname(directory) != directory:
        if os.path.basename(directory) == release_folder:
            found = directory
        directory = os.path.dirname(directory)
    return found or os.path.dirname(path)


def confirmed_bracketed_number(release_folder: str, directory: str) -> str:
    """The number in the folder name's brackets (`-(BIR030)-`) when the release's .nfo states the same one, else ''.

    The .nfo is the confirmation. Whether a bracketed number without an .nfo is good enough is
    still open in issue #172; until it is decided, such a release gets its stale tag cleared.
    """
    bracketed = from_folder_name(release_folder)
    if not bracketed:
        return ''
    info = release_nfo.read(directory)
    stated = release_nfo.stated_catalogue_number(info.text) if info else None
    if stated and comparable(stated) == comparable(bracketed):
        return bracketed
    return ''


class HealStaleCatalogueNumberRule(TagRule):
    """Swaps a stale whole-folder-name CATALOGNUMBER for the number derived now, or clears it.

    Only a tag equal to the release folder name, or to that name without its `<number> - `
    prefix, counts as stale. Any other value is a number a person or the label wrote, and stays.
    The number derived now is the folder's prefix (`LabelPath.catalog_number`), else the bracketed
    number the release's .nfo confirms. Without either the tag is emptied, which makes
    `BaseSong.save_file` drop it from the file.

    LabelSong runs it before it writes the folder's number, with the release folder name.
    """

    def __init__(self, release_folder: str):
        self._release_folder = release_folder or ''

    def apply(self, song) -> None:
        collection = song.tag_collection
        if not self._release_folder or not collection.has_item(CATALOG_NUMBER):
            return
        current = (collection.get_item_as_string(CATALOG_NUMBER) or '').strip()
        if current not in stale_values(self._release_folder):
            return
        derived = LabelPath.catalog_number(self._release_folder)
        if not derived:
            directory = release_directory(song.path(), self._release_folder)
            derived = confirmed_bracketed_number(self._release_folder, directory)
        if derived == current:
            # A folder named only for its number (`FUSION001`): the tag is right.
            return
        collection.set_item(CATALOG_NUMBER, derived)
