"""What the importer may conclude about a release folder from its .nfo and the store it links.

Two questions, both asked only when the folder name has not already answered them:

* **The catalogue number** (`catalogue_number`): the .nfo's `Catalog Nr`, when it passes the same
  test a name's catalogue number must pass and holds a letter. The Renamer puts it in front of
  the name, so the release is routed by `rules_catid_label` like any other.
* **The label folder** (`placement`): the .nfo's label (`Label`, `Company`, ...), else the label
  the linked Deezer album names, mapped onto an existing label folder by `LabelIndex`. Two sources
  that name two different existing folders place nothing.

The .nfo is read once per folder and kept in memory against its size and modification time: the
Mover meets every unplaceable folder on every cycle (7.186 proposal rows on production), and
re-reading thousands of .nfo files over CIFS every five minutes would buy nothing.

docs/designs/release-info-enrichment/.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from services.common import release_nfo
from services.common.release_nfo import NfoInfo, StoreLink
from services.common.store_lookup import Budget, StoreAlbum, StoreCache
from services.importer.label_match import LabelIndex

#: Folders kept in memory. The import queue held 6.583 on 2026-10-02.
MEMORY_SIZE = 20000


@dataclass(frozen=True)
class Placement:
    """Where a release goes without a catalogue rule, and on whose word."""

    label: str
    source: str
    stated: str


def _nfo_path(folder_path: str) -> str | None:
    try:
        names = sorted(name for name in os.listdir(folder_path) if name.lower().endswith('.nfo'))
    except OSError:
        return None
    return os.path.join(folder_path, names[0]) if names else None


class ReleaseInfo:
    """The .nfo facts per release folder, and the decisions built on them."""

    def __init__(self, store: StoreCache | None = None):
        self.store = store or StoreCache()
        self._facts: dict[str, tuple[tuple, NfoInfo | None]] = {}

    def nfo(self, folder_path: str) -> NfoInfo | None:
        """The facts of the folder's .nfo, read again only when the file changed."""
        path = _nfo_path(folder_path)
        if path is None:
            self._facts.pop(folder_path, None)
            return None
        try:
            info = os.stat(path)
        except OSError:
            return None
        key = (path, info.st_size, info.st_mtime)
        cached = self._facts.get(folder_path)
        if cached and cached[0] == key:
            return cached[1]
        facts = release_nfo.read(folder_path)
        if facts is not None:
            # The text is only needed while parsing; thousands of folders stay in memory.
            facts = NfoInfo(facts.label, facts.label_key, facts.catalogue_number, facts.links, '')
        if len(self._facts) >= MEMORY_SIZE:
            self._facts.clear()
        self._facts[folder_path] = (key, facts)
        return facts

    def catalogue_number(self, folder_path: str) -> str | None:
        """The catalogue number the .nfo states, when it is a real one."""
        facts = self.nfo(folder_path)
        return facts.catalogue_number if facts else None

    def deezer_link(self, folder_path: str) -> StoreLink | None:
        """The Deezer album the .nfo links, if any."""
        facts = self.nfo(folder_path)
        return facts.link('deezer') if facts else None

    def album(self, folder_path: str, budget: Budget | None) -> StoreAlbum | None:
        """The linked Deezer album's facts, fetched when `budget` allows and not yet known."""
        link = self.deezer_link(folder_path)
        return self.store.lookup(link, budget) if link else None

    def placement(self, folder_path: str, index: LabelIndex, budget: Budget | None) -> Placement | None:
        """The existing label folder the release belongs in, or None when that is not certain."""
        facts = self.nfo(folder_path)
        if facts is None:
            return None
        from_nfo = index.match(facts.label) if facts.label else None
        album = self.album(folder_path, budget) if facts.link('deezer') else None
        from_store = index.match(album.label) if album and album.found and album.label else None
        if from_nfo and from_store and from_nfo != from_store:
            logging.info(
                'Not placing %s: the .nfo says %s (%s), Deezer says %s (%s)',
                os.path.basename(folder_path),
                facts.label,
                from_nfo,
                album.label if album else None,
                from_store,
            )
            return None
        if from_nfo:
            return Placement(from_nfo, f'nfo:{facts.label_key}', str(facts.label))
        if from_store and album is not None:
            return Placement(from_store, 'deezer', str(album.label))
        return None
