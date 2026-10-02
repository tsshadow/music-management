"""Which existing label folder a label name means: `b2s Records` -> `EPs/B2S`.

The importer may only ever place a release in a folder that already exists -- a new label is a
curator's decision, made in Beheer > Labelvoorstellen. So the question here is narrow: does a
label name, as an .nfo or a store spells it, name exactly one of the label folders?

Names are compared folded: case, accents, punctuation and `&`/`and` do not count, and neither do
trailing words every label tacks on (`Records`, `Recordings`, `Music`, `Digital`, ...), so
`b2s Records`, `B2S` and `B2S Recordings` are one label. A name that folds onto two folders
(`Hard Music` and `HARD Music Records`) matches neither: ambiguity is a proposal, not a guess.

A curator's earlier decisions count as aliases: a confirmed label proposal whose proposed label
differs from the one decided (`Evolve Audio` -> `Evolve AU`) maps that spelling from then on.

Measured on production on 2026-10-02, over the .nfo files of the releases already in the label
tree that no catalogue rule routes: the .nfo label maps to the folder the release is in for
3.562 and to another folder for 188, almost all a parent label where the curator keeps a
sub-label folder (`Cloud 9 Music` for `Cloud 9 Dance`). That residue is why placement by name has
its own switch, `import_place_by_label_name`.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from collections.abc import Iterable

from services.common.import_queue import ImportQueue

#: Words a label name carries that say nothing about which label it is, dropped from the end.
GENERIC_SUFFIXES = frozenset(
    {
        'audio',
        'bv',
        'digital',
        'entertainment',
        'gmbh',
        'group',
        'inc',
        'label',
        'limited',
        'llc',
        'ltd',
        'media',
        'music',
        'musik',
        'production',
        'productions',
        'rec',
        'record',
        'recording',
        'recordings',
        'records',
    }
)

ALIASES_SQL = (
    "SELECT proposed_label, decided_label FROM rules_label_proposals WHERE status = 'confirmed' "
    'AND proposed_label IS NOT NULL AND decided_label IS NOT NULL'
)


def fold(name: str | None) -> str:
    """A label name reduced to what identifies it: `The B2S Records` -> `b2s`."""
    text = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    words = re.findall(r'[a-z0-9]+', text.replace('&', ' and '))
    while len(words) > 1 and words[-1] in GENERIC_SUFFIXES:
        words.pop()
    if len(words) > 1 and words[0] == 'the':
        words.pop(0)
    return ''.join(words)


class LabelIndex:
    """The label folders of the library, looked up by folded name."""

    def __init__(self, folders: Iterable[str], aliases: dict[str, str] | None = None):
        self._by_key: dict[str, set[str]] = {}
        for folder in folders:
            key = fold(folder)
            if key:
                self._by_key.setdefault(key, set()).add(folder)
        self._aliases = {fold(alias): target for alias, target in (aliases or {}).items() if fold(alias)}
        self.folders = {folder for names in self._by_key.values() for folder in names}

    @classmethod
    def from_library(cls, eps_root: str, queue: ImportQueue, connection_factory=None) -> LabelIndex:
        """The label folders under `eps_root` (never the import queue), with the confirmed aliases."""
        try:
            entries = os.listdir(eps_root)
        except OSError as exc:
            logging.warning('Could not list the label folders in %s: %s', eps_root, exc)
            entries = []
        folders = [
            name
            for name in entries
            if os.path.isdir(os.path.join(eps_root, name)) and queue.is_label_folder(os.path.join(eps_root, name))
        ]
        return cls(folders, load_aliases(connection_factory))

    def match(self, name: str | None) -> str | None:
        """The one label folder `name` means, or None when it means none or more than one."""
        key = fold(name)
        if not key:
            return None
        alias = self._aliases.get(key)
        if alias and alias in self.folders:
            return alias
        hits = self._by_key.get(key) or set()
        return next(iter(hits)) if len(hits) == 1 else None


def load_aliases(connection_factory=None) -> dict[str, str]:
    """`proposed -> decided` for every confirmed proposal; empty when the table cannot be read."""
    try:
        if connection_factory is None:
            from services.common.Helpers.DatabaseConnector import DatabaseConnector

            connection_factory = DatabaseConnector().connection
        with connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(ALIASES_SQL)
            return {str(proposed): str(decided) for proposed, decided in cursor.fetchall() if proposed != decided}
    except Exception as exc:  # noqa: BLE001 - no aliases is a smaller index, not a failure
        logging.debug('Label aliases not readable: %s', exc)
        return {}
